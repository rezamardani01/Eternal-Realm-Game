"""Gifting: reply «انتقال» to someone, pick what to give, set the amount with buttons, confirm."""

from __future__ import annotations

import contextlib

from baleropy.exceptions import BaleAPIError

from ..game.data.items import Kind, get_item
from ..game.services.economy import CRYSTAL_DAILY_LIMIT
from ..shared.errors import GameError
from ..shared.text import bold, fa
from .panel import Ctx, Screen, _int, _page, screen

# callback layout: a = "<receiver id>.<what>"   b = "<amount>"   (what: coin | crystal | g<id> | item id)
STEPS_GOLD = (1, 5, 100, 1000)


def _split(c: Ctx) -> tuple[int, str]:
    target, _, what = c.a.partition(".")
    return _int(target), what


async def _receiver(c: Ctx, target: int):  # noqa: ANN202
    other = await c.services.players.get(target)
    if other is None:
        raise GameError("گیرنده‌ی هدیه در قلمرو پیدا نشد.")
    return other


def _who(c: Ctx, player) -> str:  # noqa: ANN001
    return c.who(player)


@screen("xfer")
async def xfer(c: Ctx) -> Screen:
    other = await _receiver(c, _int(c.a))
    if other.id == c.player.id:
        raise GameError("به خودتان که نمی‌شود چیزی بخشید! روی پیام دوستتان ریپلای کنید.")
    text = (
        f"🎁 {bold('انتقال هدیه')}\n\n"
        f"گیرنده: {_who(c, other)}\n\n"
        "چه چیزی را می‌خواهید ببخشید؟ 👇"
    )
    t = str(other.id)
    rows = [
        [c.btn("🪙 سکه", "xamt", f"{t}.coin", "1"), c.btn("💎 کریستال", "xamt", f"{t}.crystal", "1")],
        [c.btn("🎒 آیتم", "xlist", t, "items"), c.btn("⛓️ منابع", "xlist", t, "mats")],
        [c.btn("❌ انصراف", "xcancel")],
    ]
    return Screen(text, rows)


@screen("xcancel")
async def xcancel(c: Ctx) -> Screen:
    return Screen(f"🎁 {bold('انتقال لغو شد')}\n\nچیزی جابه‌جا نشد.", [])


@screen("xlist")
async def xlist(c: Ctx) -> Screen:
    other = await _receiver(c, _int(c.a))
    kind, _, page_text = c.b.partition(".")
    page = _int(page_text or "0")
    view = await c.services.inventory.view(c.player.id)
    entries = []
    if kind == "items":
        entries += [(f"{p.label}", "xconf", f"{other.id}.g{p.id}", "1") for p in view.gear
                    if p.slot is None and p.item.tradable]
        entries += [(f"{i.label} ×{fa(q)}", "xamt", f"{other.id}.{i.id}", "1") for i, q in view.stacks
                    if i.tradable and i.kind is not Kind.MATERIAL]
    else:
        entries += [(f"{i.label} ×{fa(q)}", "xamt", f"{other.id}.{i.id}", "1") for i, q in view.stacks
                    if i.tradable and i.kind is Kind.MATERIAL]
    title = "🎒 آیتم‌ها" if kind == "items" else "⛓️ منابع"
    if not entries:
        return Screen(f"{title.split(' ')[0]} {bold(title.split(' ', 1)[1])}\n\nچیزی برای بخشیدن ندارید.", [c.back("xfer", "🔙 بازگشت", other.id)])
    chunk, prev, nxt = _page(entries, page)
    rows = [[c.btn(label, s, a, b)] for label, s, a, b in chunk]
    nav = ([c.btn("‹ قبلی", "xlist", c.a, f"{kind}.{page - 1}")] if prev else []) + (
        [c.btn("بعدی ›", "xlist", c.a, f"{kind}.{page + 1}")] if nxt else []
    )
    if nav:
        rows.append(nav)
    rows.append(c.back("xfer", "🔙 بازگشت", other.id))
    text = f"{title.split(' ')[0]} {bold(title.split(' ', 1)[1])}\n\nیکی را برای {_who(c, other)} انتخاب کنید 👇"
    return Screen(text, rows)


async def _limits(c: Ctx, what: str) -> tuple[int, str, str]:
    """(most the player may send now, icon+name, unit)"""
    me = await c.refresh()
    if what == "coin":
        return me.gold, "🪙 سکه", "سکه"
    if what == "crystal":
        return min(me.crystal, CRYSTAL_DAILY_LIMIT), "💎 کریستال", "کریستال"
    item = get_item(what)
    view = await c.services.inventory.view(me.id)
    have = next((q for i, q in view.stacks if i.id == item.id), 0)
    return have, item.label, "عدد"


@screen("xamt")
async def xamt(c: Ctx) -> Screen:
    target, what = _split(c)
    other = await _receiver(c, target)
    cap, label, unit = await _limits(c, what)
    if cap <= 0:
        raise GameError(f"{label} ندارید که ببخشید.")
    amount = max(1, min(_int(c.b or "1"), cap))
    b = c.services.ctx.balance
    if what == "coin" and amount < b.transfer_min:
        amount = min(cap, b.transfer_min)

    def step(delta: int):  # noqa: ANN202
        new = max(1, min(cap, amount + delta))
        sign = "+" if delta > 0 else "-"
        return c.btn(f"{sign}{fa(abs(delta))}", "xamt", c.a, new)

    rows = [[step(-5), step(-1), step(1), step(5)]]
    if what == "coin" and cap >= 100:
        rows.append([step(-1000), step(-100), step(100), step(1000)])
    rows.append([c.btn(f"✅ تأیید مقدار ({fa(amount)})", "xconf", c.a, amount, style="success")])
    rows.append([c.btn("🔙 بازگشت", "xfer", other.id), c.btn("❌ انصراف", "xcancel")])
    text = (
        f"🎁 {bold('مقدار هدیه')}\n\n"
        f"گیرنده: {_who(c, other)}\n\n"
        f"{label}\n\n"
        f"مقدار انتخابی: {bold(fa(amount))} {unit}\n\n"
        f"موجودی شما: {fa(cap)} {unit}\n\n"
        "با دکمه‌ها مقدار را کم و زیاد کنید، بعد دکمه‌ی سبز را بزنید 👇"
    )
    return Screen(text, rows)


@screen("xconf")
async def xconf(c: Ctx) -> Screen:
    target, what = _split(c)
    other = await _receiver(c, target)
    amount = _int(c.b or "1")
    if what.startswith("g") and what[1:].isdigit():
        piece = next((p for p in (await c.services.inventory.view(c.player.id)).gear if p.id == int(what[1:])), None)
        if piece is None:
            raise GameError("این تجهیزات دیگر در کوله‌پشتی شما نیست.")
        label = piece.label
    else:
        _, label_, unit = await _limits(c, what)
        label = f"{label_} — {fa(amount)} {unit}"
    text = (
        f"🎁 {bold('مطمئنید می‌خواهید ببخشید؟')}\n\n"
        f"گیرنده: {_who(c, other)}\n\n"
        f"هدیه: {label}\n\n"
        "این کار برگشت ندارد."
    )
    rows = [[c.btn("✅ تأیید و انتقال", "xdo", c.a, amount, style="success"), c.btn("❌ انصراف", "xcancel")]]
    return Screen(text, rows)


@screen("xdo")
async def xdo(c: Ctx) -> Screen:
    target, what = _split(c)
    other = await _receiver(c, target)
    receipt = await c.services.economy.send(c.player, other, what, _int(c.b or "1"))
    lines = [
        f"🎁 {bold('هدیه رسید!')}",
        "",
        f"از: {_who(c, c.player)}",
        f"به: {_who(c, other)}",
        f"هدیه: {receipt.what}",
    ]
    if receipt.left is not None:
        lines += ["", f"🏦 امروز می‌توانید {fa(receipt.left)} {receipt.unit}‌ی دیگر ببخشید."]
    if c.message is not None:
        dm = (
            f"🎁 {bold('هدیه‌ای برای شما رسید!')}\n\n"
            f"از: {c.player.name}\n"
            f"هدیه: {receipt.what}\n\n"
            "از کیف و کوله‌پشتی‌تان ببینیدش."
        )
        with contextlib.suppress(BaleAPIError):
            await c.message.bot.send_message(other.platform_user_id, dm)
    return Screen("\n".join(lines), [])
