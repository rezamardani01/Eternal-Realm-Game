"""The hero's own switches and keys: «🔔 اعلان‌ها» (which automatic messages to receive) and «🎁 کد هدیه» (claim a code)."""

from __future__ import annotations

from baleropy import F, Router
from baleropy.fsm import FSMContext, State, StatesGroup
from baleropy.types import Message

from ..game.data import notifs
from ..shared.errors import GameError
from ..shared.text import bold, headline
from . import keyboards
from .panel import Ctx, Screen, screen
from .services import Services

router = Router(name="settings")
LINE = "─" * 12


class CodeFlow(StatesGroup):
    code = State()


# --- notifications ----------------------------------------------------------------------------------------------------------
@screen("notifs")
async def notifications(c: Ctx) -> Screen:
    if c.is_group:
        raise GameError("اعلان‌ها را در پیام خصوصی ربات تنظیم کنید.")
    p = await c.refresh()
    muted = await c.services.alerts.muted(p.id)
    offers_on = await c.services.offers.enabled(p)
    lines = [f"🔔 {bold('اعلان‌ها')}", LINE, "هر دسته را جدا روشن یا خاموش کنید. پیام‌ها فقط در پیوی ربات می‌آیند.", ""]
    rows = []
    for cat in notifs.CATEGORIES:
        on = cat.id not in muted
        lines.append(f"{'✅' if on else '⛔'} {cat.emoji} {bold(cat.name)}\n    {cat.about}")
        rows.append([c.btn(f"{'✅' if on else '⛔'} {cat.emoji} {cat.name}", "notiftog", cat.id)])
    lines.append(f"{'✅' if offers_on else '⛔'} ✉️ {bold('پیشنهادهای شخصی')}\n    پیشنهاد مفید و جایزه‌ی بازگشت؛ حداکثر چند پیام در روز.")
    rows.append([c.btn(f"{'✅' if offers_on else '⛔'} ✉️ پیشنهادهای شخصی", "notiftog", "offers")])
    lines += ["", "هشدار حمله‌ی دشمن به دهکده و پیام‌های مربوط به پرداخت همیشه می‌آید."]
    all_on = not muted and offers_on
    rows.append([
        c.btn("🔕 خاموش کردن همه" if all_on else "🔔 روشن کردن همه", "notifall", "0" if all_on else "1", style="danger" if all_on else "success"),
    ])
    rows.append(c.back("profile"))
    return Screen("\n".join(lines), rows)


@screen("notiftog")
async def notification_toggle(c: Ctx) -> Screen:
    if c.a == "offers":
        on = not await c.services.offers.enabled(c.player)
        await c.services.offers.set_enabled(c.player, on)
        name = "پیشنهادهای شخصی"
    else:
        on = await c.services.alerts.toggle(c.player.id, c.a)
        name = notifs.BY_ID[c.a].name
    shown = await notifications(c)
    shown.toast = f"{'✅ روشن شد' if on else '⛔ خاموش شد'}: {name}"
    return shown


@screen("notifall")
async def notification_all(c: Ctx) -> Screen:
    on = c.a == "1"
    await c.services.alerts.set_muted(c.player.id, set() if on else {cat.id for cat in notifs.CATEGORIES})
    await c.services.offers.set_enabled(c.player, on)
    shown = await notifications(c)
    shown.toast = "🔔 همه‌ی اعلان‌ها روشن شد" if on else "🔕 همه‌ی اعلان‌ها خاموش شد"
    return shown


# --- gift codes -------------------------------------------------------------------------------------------------------------
def claimed_text(found) -> str:  # noqa: ANN001 - GiftCode
    return f"🎁 {bold('کد هدیه فعال شد!')}\n\n{found.worth()}\n\nبه کیف شما اضافه شد. ✨"


@screen("giftcode")
async def gift_code(c: Ctx) -> Screen:
    if c.is_group or c.state is None:
        raise GameError("کد هدیه را در پیام خصوصی ربات وارد کنید.")
    await c.state.set_state(CodeFlow.code)
    text = (
        f"🎁 {bold('کد هدیه')}\n\n"
        "کد هدیه‌ای که از مدیریت یا کانال بازی گرفته‌اید را همین‌جا بفرستید (حرف و عدد انگلیسی).\n"
        "هر کد را هر قهرمان فقط یک بار می‌تواند فعال کند و ظرفیتش محدود است."
    )
    return Screen(text, [c.back("profile", "❌ انصراف")])


@router.message(CodeFlow.code, F.text)
async def got_code(message: Message, state: FSMContext, services: Services) -> None:
    user = message.from_user
    assert user is not None
    player = await services.players.require(user.id)
    await state.clear()
    found = await services.giftcodes.redeem(player, message.text or "")
    await message.answer(headline(claimed_text(found)), buttons=[[keyboards.panel_button("🏰 قلمرو من", "home", user.id)]])
