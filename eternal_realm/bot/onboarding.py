"""First start in private chat: display name -> race -> class -> character created."""

from __future__ import annotations

from baleropy import F, Router
from baleropy.filters import ChatTypeFilter, CommandStart
from baleropy.fsm import FSMContext, State, StatesGroup
from baleropy.types import CallbackQuery, Message

from ..game.data.classes import CLASSES
from ..game.data.races import RACES
from ..shared.errors import GameError
from . import keyboards, pages, views
from .callbacks import ClassCb, RaceCb
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
    player = await services.players.find(user.id, user.username)
    if player is not None:
        text, buttons = await pages.PAGES["home"](services, player)
        await message.answer(text, buttons=buttons)
        return
    await state.set_state(Onboarding.name)
    await message.answer(views.welcome())


@router.message(Onboarding.name, F.text)
async def got_name(message: Message, state: FSMContext, services: Services) -> None:
    name = await services.players.name_available(message.text or "")
    await state.update_data(name=name)
    await state.set_state(Onboarding.race)
    await message.answer(views.pick_race(name), buttons=keyboards.race_buttons())


@router.message(Onboarding.name)
async def name_needs_text(message: Message) -> None:
    raise GameError("لطفاً نام شخصیتت را به‌صورت متن بفرست.")


@router.callback_query(Onboarding.race, RaceCb.filter())
async def got_race(
    query: CallbackQuery, callback_data: RaceCb, state: FSMContext
) -> None:
    race = RACES.get(callback_data.id)
    data = await state.get_data()
    if race is None or "name" not in data or query.message is None:
        raise GameError("دوباره /start بزن.")
    await state.update_data(race=race.id)
    await state.set_state(Onboarding.char_class)
    await query.message.edit_text(
        views.pick_class(data["name"], race), buttons=keyboards.class_buttons()
    )
    await query.answer()


@router.callback_query(Onboarding.char_class, ClassCb.filter())
async def got_class(
    query: CallbackQuery, callback_data: ClassCb, state: FSMContext, services: Services
) -> None:
    char_class = CLASSES.get(callback_data.id)
    data = await state.get_data()
    if char_class is None or "race" not in data or query.message is None:
        raise GameError("دوباره /start بزن.")
    user = query.from_user
    player = await services.players.register(
        user.id, user.username, data["name"], data["race"], char_class.id
    )
    await state.clear()
    await query.message.edit_text(views.created(player, services.bot_username))
    text, buttons = await pages.PAGES["home"](services, player)
    await query.message.answer(text, buttons=buttons)
    await query.answer("شخصیتت ساخته شد 🎉")
