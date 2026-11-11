"""Realm-wide events in the bot: the announcement in every group, the join from the private chat, the live countdown."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot, Button
from baleropy.exceptions import BaleAPIError, BaleNetworkError

from ..game.data import raids as data
from ..game.services.raids import RaidEvent, RaidView
from ..shared.errors import GameError
from ..shared.text import bold, fa, headline
from .services import Services

log = logging.getLogger("eternal_realm.raids")

NAMES_SHOWN = 10
DM_NAMES_SHOWN = 15
#: seconds between two refreshes of the messages that show the countdown, and the pause between two Bale calls
REFRESH_SECONDS = 30
CALL_GAP = 0.05


def clock(seconds: int) -> str:
    minutes, sec = divmod(max(0, seconds), 60)
    return fa(f"{minutes:02d}:{sec:02d}")


def _names(view: RaidView, shown: int) -> list[str]:
    lines = [f"🔹 {name}" for name in view.names[:shown]]
    if view.count > shown:
        lines.append(f"و {fa(view.count - shown)} قهرمان دیگر ...")
    return lines or ["هنوز کسی نپیوسته؛ اولین نفر باشید!"]


def join_link(services: Services, raid_id: int) -> str:
    return f"https://ble.ir/{services.bot_username}?start=ev_{raid_id}"


def group_text(view: RaidView) -> str:
    kind = view.kind
    if view.status == "lobby":
        return (
            f"{kind.emoji} {bold(kind.title)}\n\n{kind.blurb}\n\n"
            f"⏳ شروع تا: {bold(clock(view.seconds_left))}\n"
            f"👥 قهرمانان پیوسته: {bold(fa(view.count))}\n\n"
            + "\n".join(_names(view, NAMES_SHOWN))
            + "\n\n🎁 جایزه‌های بسیار بزرگ برای همه‌ی شرکت‌کننده‌ها!\n"
            "👇 دکمه را بزنید تا به ربات بیایید و بپیوندید؛ نبرد خودکار است."
        )
    return final_text(view)


def final_text(view: RaidView) -> str:
    kind, s = view.kind, view.summary
    if view.status == "cancelled":
        return f"🌫️ {bold(kind.title)}\n\nشرکت‌کننده‌ی کافی نبود و این رویداد برگزار نشد. دفعه‌ی بعد همه را خبر کنید!"
    top = s.get("top", [])
    line = "━━━━━━━━━━━━"
    medals = ["🥇", "🥈", "🥉", "🎖️", "🎖️"]
    count = s.get("count", view.count)
    lines = [f"{kind.emoji} {bold(kind.title)}", line]
    if kind.mode == "raid":
        win = s.get("victory")
        lines += [
            "🏆 " + bold("قلمرو پیروز شد!") if win else "💔 " + bold("این بار غول پیروز شد"),
            data.VICTORY[kind.id] if win else data.DEFEAT[kind.id],
            "", f"📊 {bold('گزارش نبرد')}",
            f"👥 قهرمانان: {fa(count)}",
            f"⚔️ قدرت یورش قهرمانان: {fa(round(100 * s.get('removed', 0) / max(0.01, s.get('need', 1))))}٪ هدف پیروزی",
            f"🗡️ غول را شکست دادند: {fa(s.get('slain', 0))} نفر",
        ]
        title = "برترین قهرمانان"
        board = [f"{medals[i]} {t['name']} — {fa(t['score'])} امتیاز" + (f" · 💎 {fa(t['crystal'])}" if t["crystal"] else "") for i, t in enumerate(top)]
    elif kind.mode == "cup":
        lines += ["🏆 " + bold("جام قهرمانان به پایان رسید!"), data.CUP_STORY, "", f"📊 {bold('گزارش جام')}", f"👥 شرکت‌کننده‌ها: {fa(count)}"]
        title = "سکوی افتخار"
        board = [f"{medals[i]} {t['name']} — {fa(t['score'])} امتیاز · 💎 {fa(t['crystal'])}" for i, t in enumerate(top)]
    else:
        lines += ["💰 " + bold("قرعه‌کشی انجام شد!"), data.LOTTERY_STORY, "", f"📊 {bold('گزارش قرعه')}", f"👥 شرکت‌کننده‌ها: {fa(count)}"]
        title = "برنده‌ی جایزه‌ی بزرگ"
        board = [f"🥇 {s['jackpot']} — {fa(top[0]['gold']) if top else ''} سکه و ۲۰ کریستال"] if s.get("jackpot") else []
    lines += ["", f"🏅 {bold(title)}", *board, "", line, f"🎁 در مجموع: 🪙 {fa(s.get('gold', 0))} · 💎 {fa(s.get('crystal', 0))} · 📦 {fa(s.get('chests', 0))} صندوقچه", "هر قهرمان نتیجه و جایزه‌ی خودش را در پیوی دریافت کرد ✉️"]
    return "\n".join(lines)


def dm_text(view: RaidView) -> str:
    kind = view.kind
    if view.status != "lobby":
        return f"{kind.emoji} {bold(kind.title)}\n\n⚔️ نبرد انجام شد؛ نتیجه و جایزه‌ات را در پیام بعدی ببین."
    return (
        f"✅ {bold('به ' + kind.title + ' پیوستید!')}\n\n"
        f"⏳ شروع تا: {bold(clock(view.seconds_left))}\n"
        f"👥 قهرمانان پیوسته: {bold(fa(view.count))}\n\n"
        + "\n".join(_names(view, DM_NAMES_SHOWN))
        + "\n\n⚔️ وقتی شمارش تمام شود نبرد خودکار شما شروع می‌شود و نتیجه و جایزه‌ها همین‌جا می‌آید.\n"
        "نیازی به کاری نیست؛ فقط ربات را باز بگذارید 🙂"
    )


def group_buttons(services: Services, view: RaidView):  # noqa: ANN201
    if view.status != "lobby" or not services.bot_username:
        return None
    return [[Button.url(f"⚔️ پیوستن به {view.kind.title}", join_link(services, view.id))]]


# --- announcing ---------------------------------------------------------------------------------------------------------
async def announce(bot: Bot, services: Services, view: RaidView) -> int:
    """Post the event in every group; returns in how many groups it landed."""
    sent = 0
    for chat_id in await services.raids.target_groups():
        buttons = group_buttons(services, view)
        try:
            message = await bot.send_message(chat_id, headline(group_text(view)), buttons=buttons)
        except (BaleAPIError, BaleNetworkError):
            await asyncio.sleep(CALL_GAP)
            continue
        await services.raids.add_post(view.id, chat_id, message.message_id)
        sent += 1
        await asyncio.sleep(CALL_GAP)
    return sent


async def join_from_start(message, services: Services, raid_id: int, user=None) -> None:  # noqa: ANN001 - Message
    """The hero tapped the button in a group and arrived with «ev_<id>»: join and show the live list."""
    user = user or message.from_user
    player = await services.players.find(user.id, user.username)
    if player is None:
        raise GameError("اول قهرمان بسازید.")
    view, fresh = await services.raids.join(player, raid_id)
    sent = await message.bot.send_message(player.platform_user_id, headline(dm_text(view)))
    await services.raids.set_dm(raid_id, player.id, sent.message_id)


async def _edit(bot: Bot, chat_id: int, message_id: int, text: str, buttons=None) -> None:  # noqa: ANN001
    with contextlib.suppress(BaleAPIError, BaleNetworkError):
        if buttons:
            await bot.edit_message_text(chat_id, message_id, headline(text), buttons=buttons)
        else:
            await bot.edit_message_text(chat_id, message_id, headline(text))
    await asyncio.sleep(CALL_GAP)


async def refresh(bot: Bot, services: Services, view: RaidView) -> None:
    for chat_id, message_id in await services.raids.posts(view.id):
        await _edit(bot, chat_id, message_id, group_text(view), group_buttons(services, view))
    for uid, message_id in await services.raids.dms(view.id):
        await _edit(bot, uid, message_id, dm_text(view))


async def conclude(bot: Bot, services: Services, event: RaidEvent) -> None:
    await refresh(bot, services, event.view)


async def start_event(bot: Bot, services: Services, kind_id: str, minutes: int = data.LOBBY_MINUTES) -> RaidView:
    view = await services.raids.create(kind_id, minutes)
    await announce(bot, services, view)
    return view


async def processor(bot: Bot, services: Services, interval: float = 10.0) -> None:
    last_edit, last_count, last_id = 0.0, -1, 0
    loop = asyncio.get_running_loop()
    while True:
        try:
            for event in await services.raids.tick():
                await conclude(bot, services, event)
            due = await services.raids.scheduled()
            if due is not None:
                await start_event(bot, services, *due)
            view = await services.raids.current()
            if view is not None:
                now = loop.time()
                changed = view.id != last_id or view.count != last_count
                if (changed and now - last_edit >= interval) or now - last_edit >= REFRESH_SECONDS:
                    await refresh(bot, services, view)
                    last_edit, last_count, last_id = loop.time(), view.count, view.id
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("raid processor failed")
        await asyncio.sleep(interval)
