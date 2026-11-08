"""Random group events: posting what the bot invents, the buttons people tap and the loop that drives it."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot, F, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..game.services.events import EventAction, EventView
from ..game.data.items import get_item
from ..shared.errors import GameError
from ..shared.text import bold, duration, fa, headline
from . import boss as boss_ui
from . import keyboards, views
from .callbacks import EventCb
from .services import Services

log = logging.getLogger("eternal_realm.events")
router = Router(name="events")


def text_for(view: EventView) -> str:
    return views.event_text(view)


async def announce(bot: Bot, services: Services, action: EventAction) -> None:
    view = action.view
    try:
        if view.boss is not None:
            sent = await bot.send_message(
                view.chat_id, boss_ui.text_for(services, view.boss), buttons=boss_ui.buttons_for(view.boss)
            )
            await services.bosses.attach_message(view.boss.id, sent.message_id)
            await alert_hunters(bot, services, view)
            return
        if action.what == "spawned":
            buttons = keyboards.event_buttons(view)
            if buttons:
                sent = await bot.send_message(view.chat_id, text_for(view), buttons=buttons)
            else:
                sent = await bot.send_message(view.chat_id, text_for(view))
            await services.events.attach_message(view.id, sent.message_id)
        elif view.message_id is not None:
            await bot.edit_message_text(view.chat_id, view.message_id, text_for(view))
    except BaleAPIError:
        log.warning("could not post event %s in chat %s", view.kind, view.chat_id)


async def _show(query: CallbackQuery, view: EventView) -> None:
    if query.message is None:
        return
    buttons = keyboards.event_buttons(view)
    with contextlib.suppress(BaleAPIError):
        if buttons:
            await query.message.edit_text(text_for(view), buttons=buttons)
        else:
            await query.message.edit_text(text_for(view))


@router.callback_query(EventCb.filter())
async def on_event_button(query: CallbackQuery, callback_data: EventCb, services: Services) -> None:
    player = await services.players.require(query.from_user.id)
    if callback_data.action == "open":
        view, success = await services.events.try_open(callback_data.id, player)
        await _show(query, view)
        await query.answer("🎉 صندوقچه را گشودید!" if success else "🔑 رمز درست نبود؛ کمی بعد دوباره تلاش کنید.")
    elif callback_data.action == "buy":
        view, label = await services.events.buy(callback_data.id, player, callback_data.arg)
        await _show(query, view)
        await query.answer(f"🛒 {label} خریداری شد!")
    elif callback_data.action == "search":
        before = await services.events.get(callback_data.id)
        if before is None or not 0 <= callback_data.arg < len(before.state.get("places", [])):
            raise GameError("⌛ این رویداد تمام شده است.")
        view, outcome = await services.events.search(callback_data.id, player, before.state["places"][callback_data.arg])
        await _show(query, view)
        await query.answer("🗝️ صندوقچه را پیدا کردید!" if outcome == "found" else "🍂 این‌جا چیزی نبود؛ جای دیگری را بگردید.")
    elif callback_data.action == "defend":
        view, damage, final = await services.events.defend(callback_data.id, player)
        await _show(query, view)
        await query.answer("🏆 ضربه‌ی آخر را شما زدید!" if final else f"⚔️ {fa(damage)} آسیب زدید!")
    elif callback_data.action == "collect":
        view, item = await services.events.collect(callback_data.id, player)
        await _show(query, view)
        await query.answer(f"☄️ {get_item(item).label} برداشتید!")
    else:
        await query.answer()


#: one «rare boss» alert per player at most this often (seconds)
ALERT_GAP = 3 * 3600
_alerted: dict[int, float] = {}


async def alert_hunters(bot: Bot, services: Services, view) -> int:  # noqa: ANN001 - EventView
    """Tell the group's eligible players, in private, that a rare boss walked in. Returns how many were told."""
    import time

    boss = view.boss
    chat = await services.groups.get(view.chat_id)
    where = (chat.title if chat and chat.title else "گروهتان")
    text = (
        f"🐉 {bold('اعلان شکار')}\n\n"
        f"{boss.type.emoji} {bold(boss.type.name)} در «{where}» ظاهر شد!\n"
        f"عنصر: {boss.type.element.emoji} {boss.type.element.noun}\n\n"
        f"⏳ تا {duration(boss.recruit_until - boss.now)} دیگر وقت پیوستن دارید؛ خودتان را به گروه برسانید و «پیوستن» را بزنید!"
    )
    now, told = time.monotonic(), 0
    for uid in await services.events.hunters(view.chat_id, boss.type.min_level):
        last = _alerted.get(uid)
        if last is not None and now - last < ALERT_GAP:
            continue
        _alerted[uid] = now
        with contextlib.suppress(BaleAPIError):
            await bot.send_message(uid, headline(text))
            told += 1
    return told


#: groups smaller than this get a friendly note when the bot is added
MIN_GROUP_MEMBERS = 25


async def _small_group_notice(message: Message) -> None:
    try:
        count = int(await message.bot.get_chat_members_count(message.chat.id))
    except (BaleAPIError, TypeError, ValueError):
        return  # unknown size: say nothing rather than something wrong
    if count >= MIN_GROUP_MEMBERS:
        return
    with contextlib.suppress(BaleAPIError):
        await message.answer(headline(
            f"👋 {bold('سلام! به قلمرو جاودان خوش آمدید')}\n\n"
            f"برای اینکه بازی در گروه جذاب و پررقابت باشد، گروه باید دست‌کم {fa(MIN_GROUP_MEMBERS)} عضو داشته باشد "
            f"(الان {fa(count)} نفر است).\n\n"
            "با دعوت دوستانتان گروه را بزرگ‌تر کنید؛ هر چه بازیکن بیشتر باشد، باس‌ها، تهاجم‌ها و رویدادها هیجان‌انگیزترند 🏰"
        ))


@router.message(F.new_chat_members)
async def on_join(message: Message, services: Services) -> None:
    """Greet newcomers: a known hero gets a fanfare, a stranger gets an invitation."""
    if str(getattr(message.chat.type, "value", message.chat.type)) == "private":
        return
    group = await services.groups.touch(message.chat.id, message.chat.title)
    if any(u.is_bot and u.username and u.username == services.bot_username for u in message.new_chat_members or []):
        await _small_group_notice(message)  # the bot itself was just added
    if not group.enabled:
        return
    for user in message.new_chat_members or []:
        if user.is_bot:
            continue
        player = await services.players.find(user.id)
        if player is not None:
            await message.answer(views.welcome_back(player))
        elif services.bot_username:
            await message.answer(
                f"🌅 {bold('درود بر ماجراجوی تازه‌وارد!')}\n\n"
                "این گروه قلمرویی پر از ماجراست. برای ساختن قهرمان خودتان دکمه‌ی زیر را بزنید 👇",
                buttons=[keyboards.start_button(services.bot_username)],
            )


async def processor(bot: Bot, services: Services, interval: float = 30.0) -> None:
    while True:
        try:
            for action in await services.events.tick():
                await announce(bot, services, action)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("event processor failed")
        await asyncio.sleep(interval)
