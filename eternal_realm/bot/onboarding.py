"""First start in private chat: display name -> race -> class -> character created."""

from __future__ import annotations

import contextlib

from baleropy import Button, F, Router
from baleropy.exceptions import BaleAPIError
from baleropy.filters import ChatTypeFilter, CommandStart
from baleropy.fsm import FSMContext, State, StatesGroup
from baleropy.types import CallbackQuery, Message

from ..game.data.classes import CLASSES
from ..game.data.races import RACES
from ..shared.errors import GameError
from ..shared.text import bold, fa, headline
from . import keyboards, panel, raid_ui, views
from .callbacks import ClassCb, PanelCb, RaceCb
from .services import Services

router = Router(name="onboarding")
router.message.filter(ChatTypeFilter("private"))


class Onboarding(StatesGroup):
    name = State()
    race = State()
    char_class = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, services: Services) -> None:
    user = message.from_user
    if user is None:
        return
    await state.clear()
    payload = (message.text or "").partition(" ")[2].strip()
    raid_id = int(payload[3:]) if payload.startswith("ev_") and payload[3:].isdigit() else 0
    player = await services.players.find(user.id, user.username)
    if player is not None:
        if raid_id:
            await raid_ui.join_from_start(message, services, raid_id)
            return
        await panel.send(message, services, player, "home")
        return
    await state.set_state(Onboarding.name)
    if raid_id:
        await state.update_data(raid=raid_id)  # joins the realm-wide event as soon as the hero is born
    inviter = services.invites.parse(payload)
    if inviter is not None:
        await state.update_data(ref=inviter)  # paid when this newcomer finishes creating the hero
        await services.invites.remember(user.id, inviter)  # ... and kept in the database in case the chat state is lost
    await message.answer(views.welcome())


@router.message(Onboarding.name, F.text)
async def got_name(message: Message, state: FSMContext, services: Services) -> None:
    name = await services.players.name_available(message.text or "")
    await state.update_data(name=name)
    await state.set_state(Onboarding.race)
    await message.answer(views.pick_race(), buttons=keyboards.race_buttons())


async def _pay_inviter(bot, services: Services, newcomer, inviter_id: int) -> None:  # noqa: ANN001
    """The friend who invited the newcomer gets small random prizes right away, with a message."""
    result = await services.invites.register(newcomer, inviter_id)
    if result is None:
        return
    total = await services.invites.count(result.inviter.id)
    if result.capped:
        body = "🎁 سقف جایزه‌ی دعوت امروز پر شده؛ فردا دوباره جایزه می‌گیرید."
    else:
        body = f"🎁 {bold('هدیه‌ی دعوت (همین حالا رسید)')}\n" + "\n".join(f"• {p}" for p in result.prizes)
    text = (
        f"🎉 {bold('دوستتان به قلمرو پیوست!')}\n\n"
        f"👤 {newcomer.name} با لینک دعوت شما قهرمانش را ساخت.\n\n{body}\n\n"
        f"👥 دعوت‌های موفق شما: {fa(total)}\n"
        "هر دوست تازه، هدیه‌ی تازه 🤝"
    )
    with contextlib.suppress(BaleAPIError):
        await bot.send_message(result.inviter.platform_user_id, headline(text))


@router.message(Onboarding.name)
async def name_needs_text(message: Message) -> None:
    raise GameError("نام قهرمان را باید با حرف بنویسید، فرمانده! یک نام برای خود بفرستید (۲ تا ۱۶ حرف).")


@router.callback_query(Onboarding.race, RaceCb.filter())
async def got_race(
    query: CallbackQuery, callback_data: RaceCb, state: FSMContext
) -> None:
    race = RACES.get(callback_data.id)
    data = await state.get_data()
    if race is None or "name" not in data or query.message is None:
        raise GameError("راه گم شد! دوباره /start را بزنید تا از اول، قهرمانتان را بسازیم.")
    await state.update_data(race=race.id)
    await state.set_state(Onboarding.char_class)
    await query.message.edit_text(views.pick_class(race), buttons=keyboards.class_buttons())
    await query.answer()


@router.callback_query(Onboarding.char_class, ClassCb.filter())
async def got_class(
    query: CallbackQuery, callback_data: ClassCb, state: FSMContext, services: Services
) -> None:
    char_class = CLASSES.get(callback_data.id)
    data = await state.get_data()
    if char_class is None or "race" not in data or query.message is None:
        raise GameError("راه گم شد! دوباره /start را بزنید تا از اول، قهرمانتان را بسازیم.")
    user = query.from_user
    player = await services.players.register(
        user.id, user.username, data["name"], data["race"], char_class.id
    )
    await state.clear()
    await services.players.grant_welcome_boost(player.id)
    inviter = int(data["ref"]) if data.get("ref") else await services.invites.pending(user.id)
    if inviter:  # the inviter is paid first, so nothing below can make it fail
        try:
            await _pay_inviter(query.message.bot, services, player, inviter)
        finally:
            await services.invites.forget(user.id)
    await query.message.edit_text(views.created(player) + "\n\n🚀 هدیه‌ی خوش‌آمد: ۳ روز بوست دو برابر برای شروع سریع‌تر!")
    await panel.send(query.message, services, player, "home")
    await services.academy.start(player.id)
    await query.message.answer(
        "🎓 قدم بعدی: آکادمی\n\nقهرمانت آماده است! برای یاد گرفتن بازی برو به «آکادمی»؛ آنجا قدم به قدم و با انجام دادن همه‌چیز را یاد می‌گیری و برای هر درس جایزه هم می‌گیری 🎁",
        buttons=[[Button.inline("🎓 شروع آکادمی", PanelCb(s="aclesson", a="hero", b=None, o=user.id), style="success")]],
    )
    if data.get("raid"):
        with contextlib.suppress(GameError):
            await raid_ui.join_from_start(query.message, services, int(data["raid"]), user)
    await query.answer("قهرمان شما به دنیا آمد 🎉")
