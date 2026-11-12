"""Gifts from the treasury: in a group, reply to somebody with «گیفت», pick the pack and amount, pay in private."""

from __future__ import annotations

from baleropy.exceptions import BaleAPIError
from baleropy.types import LabeledPrice

from ..game.data.packs import PACKS, SECTIONS
from ..shared.errors import GameError
from ..shared.text import bold, fa
from . import keyboards, views
from .panel import Ctx, Screen, _int, screen

QTY_STEPS = (1, 2, 3, 5, 10)


def _section_name(section: str) -> str:
    return SECTIONS.get(section) or views.SECTION_NAMES.get(section, section)


async def _target(c: Ctx, raw: str):  # noqa: ANN202
    target = await c.services.players.get(_int(raw))
    if target is None or target.banned:
        raise GameError("این بازیکن پیدا نشد.")
    if target.id == c.player.id:
        raise GameError("هدیه برای دیگران است؛ برای خودتان از «خزانه قلمرو» در پیوی بخرید.")
    return target


def _pack(pack_id: str):  # noqa: ANN202
    pack = PACKS.get(pack_id)
    if pack is None:
        raise GameError("چنین بسته‌ای در خزانه نیست.")
    return pack


def _split(arg: str):  # noqa: ANN202
    pack_id, _, n = arg.rpartition(".")
    qty = _int(n)
    if not pack_id:
        raise GameError("درخواست نامعتبر است.")
    return _pack(pack_id), qty


def _enabled(c: Ctx) -> None:
    if not c.services.ctx.settings.payments_enabled:
        raise GameError("خرید با پول واقعی فعلاً بسته است.")


@screen("gfs")
async def gift_sections(c: Ctx) -> Screen:
    _enabled(c)
    target = await _target(c, c.a)
    who = target.mention if c.is_group else target.name
    text = (
        f"🎁 {bold('گیفت از خزانه قلمرو')}\n\n"
        f"برای {who} چه چیزی می‌خرید؟ هر چه از خزانه انتخاب کنید، بعد از پرداخت شما برای او فعال می‌شود "
        "و پیامش می‌رسد.\n\nیک بخش را بزنید 👇"
    )
    sections = list(dict.fromkeys(x.section for x in PACKS.values() if x.section not in ("path", "arms")))
    rows = keyboards.grid([c.btn(_section_name(s), "gfsec", target.id, s) for s in sections], 2)
    rows.append([c.btn("❌ انصراف", "gfx")])
    return Screen(text, rows)


@screen("gfsec")
async def gift_packs(c: Ctx) -> Screen:
    _enabled(c)
    target = await _target(c, c.a)
    packs = [x for x in PACKS.values() if x.section == c.b]
    if not packs:
        raise GameError("این بخش بسته‌ای ندارد.")
    rows = [[c.btn(f"{x.label} — {fa(x.price_toman)} تومان", "gfpk", target.id, x.id)] for x in packs]
    rows.append(c.back("gfs", "🔙 بازگشت", target.id))
    return Screen(f"{_section_name(c.b)}\n\nکدام را هدیه می‌دهید؟ 👇", rows)


@screen("gfpk")
async def gift_pack(c: Ctx) -> Screen:
    _enabled(c)
    target = await _target(c, c.a)
    pack = _pack(c.b)
    text = (
        f"{pack.emoji} {bold(pack.title)}\n\n{views.pack_description(pack, c.services.ctx.now())}\n\n"
        f"💵 قیمت هر عدد: {bold(fa(pack.price_toman))} تومان\n\nچند عدد؟ 👇"
    )
    rows = keyboards.grid([c.btn(f"×{fa(n)}", "gfq", target.id, f"{pack.id}.{n}") for n in QTY_STEPS], 5)
    rows.append(c.back("gfsec", "🔙 بازگشت", target.id, pack.section))
    return Screen(text, rows)


@screen("gfq")
async def gift_confirm(c: Ctx) -> Screen:
    _enabled(c)
    target = await _target(c, c.a)
    pack, qty = _split(c.b)
    total = pack.price_toman * qty
    who = target.mention if c.is_group else target.name
    text = "\n".join([
        f"🎁 {bold('تأیید هدیه')}",
        "",
        f"برای: {who}",
        f"هدیه: {pack.label} ×{fa(qty)}",
        views.pack_description(pack, c.services.ctx.now()),
        "",
        f"💵 مبلغ: {bold(fa(total))} تومان",
        "",
        "با «بله»، فاکتور پرداخت بله در پیوی خودتان می‌آید؛ بعد از پرداخت، هدیه برای او فعال می‌شود.",
    ])
    rows = [[c.btn("✅ بله، فاکتور را بفرست", "gfok", target.id, c.b, style="success"), c.btn("↩️ نه", "gfpk", target.id, pack.id)]]
    return Screen(text, rows)


@screen("gfok")
async def gift_pay(c: Ctx) -> Screen:
    _enabled(c)
    target = await _target(c, c.a)
    pack, qty = _split(c.b)
    order = await c.services.payments.create_gift_order(c.player, target.id, pack.id, qty)
    if c.message is None:
        raise GameError("درخواست نامعتبر است.")
    try:
        await c.message.bot.send_invoice(
            chat_id=c.player.platform_user_id,
            title=f"هدیه: {pack.title}"[:32],
            description=f"{views.pack_description(pack, c.services.ctx.now())} · ×{qty} · هدیه برای {target.name}"[:255],
            payload=order.payload,
            provider_token=c.services.ctx.settings.provider_token,
            prices=[LabeledPrice(label=pack.title[:32], amount=order.amount)],
        )
    except BaleAPIError:
        raise GameError("فاکتور به پیوی شما نرسید؛ ربات را در پیام خصوصی استارت کنید و دوباره امتحان کنید.") from None
    who = target.mention if c.is_group else target.name
    text = (
        f"🧾 {bold('فاکتور هدیه فرستاده شد')}\n\n"
        f"فاکتور {pack.label} ×{fa(qty)} برای {who} در پیوی شما آمد. "
        "پرداخت که کردید، هدیه برای او فعال می‌شود و پیامش می‌رسد."
    )
    rows = [keyboards.open_panel_button(c.services.bot_username)] if c.services.bot_username else []
    return Screen(text, rows)


@screen("gfx")
async def gift_cancel(c: Ctx) -> Screen:
    return Screen("❌ هدیه لغو شد. هر وقت خواستید دوباره روی پیام او «گیفت» بنویسید.", [])
