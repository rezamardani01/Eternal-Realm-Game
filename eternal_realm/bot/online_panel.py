"""Online duels in the private chat: the search, the match and the fight shown on both players' screens.

The fight itself is the ordinary duel engine. Every player has their own message: the one whose turn it is gets a *fresh*
message with the move buttons (so the phone rings), the other one sees the same fight with a «wait» note.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot
from baleropy.exceptions import BaleAPIError, BaleNetworkError

from ..game.data.leagues import league_of, next_league
from ..game.services.duels import DuelUpdate
from ..game.services.online import ANYONE_AFTER, QUEUE_TIMEOUT, OnlineMatch, Waiting
from ..shared.errors import GameError
from ..shared.text import bold, duration, fa, headline
from . import keyboards, views
from .panel import Ctx, Screen, screen
from .services import Services

log = logging.getLogger("eternal_realm.online")
LINE = "─" * 12


# --- texts ---------------------------------------------------------------------------------------------------------------------
def battle_text(viewer_id: int, update: DuelUpdate, turn_seconds: int) -> str:
    """The shared fight, with a line that tells this viewer what to do now."""
    battle = update.battle
    body = views.duel_status(battle, update.lines, turn_seconds).split("\n")
    body[0] = f"🌐 {bold('مبارزه‌ی آنلاین')}"
    mine = battle.current.player_id == viewer_id
    foe = next(f for f in battle.fighters if f.player_id != viewer_id)
    note = "✅ نوبت شماست؛ یک حرکت بزنید 👇" if mine else f"⏳ نوبت {foe.name} است؛ چند لحظه صبر کنید"
    return "\n".join([*body, "", note])


def result_text(update: DuelUpdate) -> str:
    return "🌐 " + views.duel_result(update)


def result_rows(owner: int) -> list:
    return [
        [keyboards.panel_button("🌐 جستجوی حریف تازه", "onsearch", owner)],
        [keyboards.panel_button("🏠 قلمرو من", "home", owner)],
    ]


def searching_text(level: int, rating: int, waiting: int) -> str:
    league = league_of(rating)
    return "\n".join([
        f"🌐 {bold('مبارزه‌ی آنلاین')}", LINE, "",
        "🔎 در حال جستجوی حریف هم‌تراز شما...", "",
        f"⭐ سطح شما: {fa(level)}",
        f"{league.emoji} لیگ {league.name} · {fa(rating)} امتیاز",
        f"👥 الان در صف: {fa(waiting)} نفر", "",
        "هر چه بیشتر صبر کنید، جستجو گسترده‌تر می‌شود و بالاخره یک حریف پیدا می‌شود. "
        f"اگر تا {duration(QUEUE_TIMEOUT)} کسی نیامد، خودتان خبر می‌گیرید.", "",
        "می‌توانید ربات را ببندید؛ به‌محض پیدا شدن حریف پیام می‌فرستم 🔔",
    ])


# --- pushing the fight to both players -----------------------------------------------------------------------------------------------
async def _send(bot: Bot, chat_id: int, text: str, rows: list | None) -> int | None:
    sent = await bot.send_message(chat_id, headline(text), buttons=rows or None)
    return getattr(sent, "message_id", None)


async def _drop(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id:
        with contextlib.suppress(BaleAPIError, BaleNetworkError):
            await bot.delete_message(chat_id, message_id)


async def push(bot: Bot, services: Services, match: OnlineMatch, update: DuelUpdate) -> None:
    """Show the new state of an online fight to both players (the fight ended, started or moved on one turn)."""
    turn_seconds = services.ctx.balance.duel_turn_seconds
    messages: dict[int, int | None] = {}
    for seat in match.seats:
        try:
            if update.finished:
                await _drop(bot, seat.chat_id, seat.message_id)
                await _send(bot, seat.chat_id, result_text(update), result_rows(seat.platform_user_id))
                messages[seat.player_id] = None
                continue
            text = battle_text(seat.player_id, update, turn_seconds)
            mine = update.battle.current.player_id == seat.player_id
            rows = keyboards.duel_actions(update.duel.id, update.battle.current) if mine else None
            if mine or not seat.message_id:
                await _drop(bot, seat.chat_id, seat.message_id)  # a fresh message: it is what makes the phone ring
                messages[seat.player_id] = await _send(bot, seat.chat_id, text, rows)
            else:
                try:
                    await bot.edit_message_text(seat.chat_id, seat.message_id, headline(text))
                except (BaleAPIError, BaleNetworkError):
                    messages[seat.player_id] = await _send(bot, seat.chat_id, text, None)
        except (BaleAPIError, BaleNetworkError):
            log.warning("could not show the online fight to player %s", seat.player_id)
    await services.online.set_messages(match.duel_id, messages)


async def push_no_one_came(bot: Bot, w: Waiting) -> None:
    text = (
        f"⌛ {bold('حریفی پیدا نشد')}\n\nدر این مدت قهرمان هم‌ترازی در صف نبود. چند دقیقه‌ی دیگر دوباره امتحان کنید، "
        "یا تا آن موقع در میدان بات‌ها تمرین کنید."
    )
    rows = [
        [keyboards.panel_button("🔁 دوباره جستجو", "onsearch", w.platform_user_id)],
        [keyboards.panel_button("🥊 میدان بات‌ها", "arena", w.platform_user_id)],
    ]
    try:
        await bot.edit_message_text(w.chat_id, w.message_id, headline(text), buttons=rows)
    except (BaleAPIError, BaleNetworkError):
        with contextlib.suppress(BaleAPIError, BaleNetworkError):
            await _send(bot, w.chat_id, text, rows)


async def processor(bot: Bot, services: Services, interval: float = 3.0) -> None:
    """Every few seconds: pair the players who fit now and close searches nobody answered."""
    while True:
        try:
            result = await services.online.sweep()
            for match in result.matches:
                assert match.update is not None
                await push(bot, services, match, match.update)
            for waiter in result.expired:
                await push_no_one_came(bot, waiter)
            for match, actor, left in await services.online.due_warnings():
                seat = match.seat_of(actor)
                with contextlib.suppress(BaleAPIError, BaleNetworkError):
                    await _send(bot, seat.chat_id, f"⏰ {bold('فقط ' + fa(left) + ' ثانیه مانده!')}\n\nیک حرکت بزنید، وگرنه نبرد را واگذار می‌کنید.", None)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("online matchmaker failed")
        await asyncio.sleep(interval)


# --- screens ----------------------------------------------------------------------------------------------------------------------
def _private(c: Ctx) -> None:
    if c.is_group:
        raise GameError("مبارزه‌ی آنلاین در پیام خصوصی ربات انجام می‌شود؛ آنجا بیایید و حریف پیدا کنید.")


@screen("online")
async def online_home(c: Ctx) -> Screen:
    if c.is_group:
        username = c.services.bot_username
        rows = [keyboards.start_button(username)] if username else []
        return Screen("🌐 مبارزه‌ی آنلاین فقط در پیام خصوصی ربات باز می‌شود؛ آنجا حریف پیدا می‌کنید.", rows)
    p = await c.refresh()
    services = c.services
    async with services.ctx.db.read() as tx:
        rating = int(await tx.scalar("SELECT rating FROM players WHERE id = ?", (p.id,), 1000))
    league, nxt = league_of(rating), next_league(rating)
    fights, wins = await services.online.record(p.id)
    waiting = await services.online.waiting()
    lines = [
        f"🌐 {bold('مبارزه‌ی آنلاین')}", LINE, "",
        "با قهرمانان واقعی که همین الان در ربات‌اند روبه‌رو شوید؛ مثل دوئل گروه، نوبتی و با مهارت‌ها و تجهیزاتتان.", "",
        f"{league.emoji} {bold('لیگ ' + league.name)} · {fa(rating)} امتیاز",
    ]
    if nxt:
        lines.append(f"🎯 {fa(nxt.min_rating - rating)} امتیاز تا لیگ {nxt.name}")
    lines += [
        f"⚔️ مبارزه‌های آنلاین شما: {fa(fights)} · 🏆 پیروزی: {fa(wins)}",
        f"👥 الان در صف: {fa(waiting)} نفر", "",
        f"{bold('چطور کار می‌کند؟')}",
        "• دکمه‌ی جستجو را بزنید؛ حریفی با سطح نزدیک به شما پیدا می‌شود.",
        "• هر دو نفر نوبتی حرکت می‌کنید؛ هر نوبت ۹۰ ثانیه وقت دارید.",
        "• قدرت برتر محدود می‌شود تا نبرد هم‌شأن بماند.",
        "• برنده امتیاز لیگ، سکه و تجربه می‌گیرد.",
    ]
    active = await services.online.match_of_player(p.id)
    searching = await services.online.searching(p.id)
    rows = []
    if active is not None:
        lines += ["", "⚔️ همین حالا در یک نبرد هستید؛ پیام نبردتان را در همین چت ببینید."]
    elif searching is not None:
        lines += ["", "🔎 در حال جستجو هستید..."]
        rows.append([c.btn("❌ لغو جستجو", "onleave", style="danger")])
    else:
        rows.append([c.btn("🔎 جستجوی حریف", "onsearch", style="success")])
    rows.append([c.btn("🏆 تالار بزرگان", "top"), c.btn("🥊 میدان بات‌ها", "arena")])
    rows.append(c.back("fight"))
    return Screen("\n".join(lines), rows)


@screen("onsearch")
async def online_search(c: Ctx) -> Screen:
    _private(c)
    if c.message is None:
        raise GameError("برای جستجو دکمه‌ی «جستجوی حریف» را بزنید.")
    result = await c.services.online.join(c.player, c.message.chat.id, c.message.message_id)
    if result.match is not None:
        assert result.match.update is not None
        await push(c.message.bot, c.services, result.match, result.match.update)
        return Screen(None, toast="⚔️ حریف پیدا شد!")
    p = await c.refresh()
    async with c.services.ctx.db.read() as tx:
        rating = int(await tx.scalar("SELECT rating FROM players WHERE id = ?", (p.id,), 1000))
    rows = [[c.btn("❌ لغو جستجو", "onleave", style="danger")]]
    note = "🔎 جستجو ادامه دارد" if result.already else "🔎 جستجو شروع شد"
    return Screen(searching_text(p.level, rating, result.waiting), rows, toast=note)


@screen("onleave")
async def online_leave(c: Ctx) -> Screen:
    await c.services.online.leave(c.player.id)
    shown = await online_home(c)
    shown.toast = "❌ جستجو لغو شد"
    return shown


__all__ = ["ANYONE_AFTER", "processor", "push"]
