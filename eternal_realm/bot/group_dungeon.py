"""Group dungeon UI: the lobby message, join/start buttons and the result report."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Button, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery

from ..game.services.group_dungeon import MAX_PLAYERS, MIN_PLAYERS, LobbyView, RunResult
from ..shared.text import bold, duration, fa, headline
from .callbacks import DgCb
from .views import tidy_list
from .services import Services

router = Router(name="group-dungeon")
log = logging.getLogger(__name__)
MEDALS = ("🥇", "🥈", "🥉")
#: the runs in progress (a task nobody holds can be collected by the garbage collector halfway)
TASKS: set[asyncio.Task] = set()
#: what happens in each of the four rooms while the players wait for the result
ROOMS = (
    "🚪 درها بسته شد؛ جنگجویان وارد اولین اتاق می‌شوند...",
    "⚔️ اتاق دوم؛ صدای شمشیرها در تاریکی می‌پیچد...",
    "🔥 اتاق سوم؛ نبرد سخت‌تر می‌شود...",
    "👹 نگهبان سیاه‌چال بیدار شد؛ آخرین نبرد آغاز شد!",
)


def progress_text(members: list, room: str, seconds_left: int) -> str:
    roster = "\n".join(f"⚔️ {m.mention}" for m in members)
    return headline(
        f"🕳️ {bold('سیاه‌چال گروهی در جریان است')}\n\n{room}\n\n"
        f"👥 جنگجویان:\n{roster}\n\n"
        f"⏳ نتیجه تا {duration(seconds_left)} دیگر"
    )


async def _deliver(message, services: Services, result: RunResult) -> None:  # noqa: ANN001 - Message
    """Walk through the rooms with a countdown, then show the result (two minutes after «شروع»)."""
    ctx = services.ctx
    total = max(0, ctx.balance.gdungeon_run_seconds)
    step = total / len(ROOMS)
    members = result.lobby.members
    try:
        for index, room in enumerate(ROOMS[1:], start=1):
            await ctx.wait(step)
            with contextlib.suppress(BaleAPIError):
                await message.edit_text(progress_text(members, room, round(total - step * index)))
        await ctx.wait(step)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("group dungeon countdown failed")  # the result is shown all the same
    with contextlib.suppress(BaleAPIError):
        await message.delete()
    await message.answer(result_text(result), buttons=result_buttons(result))


def deliver_later(message, services: Services, result: RunResult) -> None:  # noqa: ANN001 - Message
    task = asyncio.create_task(_deliver(message, services, result), name="gdungeon-result")
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)


def lobby_text(v: LobbyView) -> str:
    roster = "\n".join(f"⚔️ {m.mention} · سطح {fa(m.level)}" for m in v.members)
    return headline(
        f"🕳️ {bold('سیاه‌چال گروهی باز شد!')}\n\n"
        "🚪 چهار اتاق دارد: سه اتاق هیولا و در آخر نگهبان سیاه‌چال.\n"
        "🤝 همه با هم می‌جنگید؛ دوستان بیشتر و قوی‌تر یعنی برد راحت‌تر.\n\n"
        f"👥 جنگجویان: {fa(len(v.members))} از {fa(MAX_PLAYERS)} (دست‌کم {fa(MIN_PLAYERS)})\n{roster}\n\n"
        f"⏳ ثبت‌نام: {duration(v.seconds_left)}\n\n"
        "👇 «پیوستن» را بزنید؛ بازکننده‌ی سیاه‌چال «شروع» را می‌زند."
    )


def lobby_buttons(dungeon_id: int):  # noqa: ANN201
    return [[
        Button.inline("⚔️ پیوستن", DgCb(action="join", id=dungeon_id), style="success"),
        Button.inline("🚀 شروع", DgCb(action="start", id=dungeon_id), style="danger"),
    ]]


def result_text(r: RunResult) -> str:
    blocks = [
        f"🏆 {bold('سیاه‌چال فتح شد!')}" if r.cleared else f"💀 {bold('سیاه‌چال شما را بلعید')}",
    ]
    wave_lines = []
    for w in r.waves:
        wave_lines.append(f"{w.emoji} {w.name} — {'شکست خورد' if w.won else 'پیروز شد'} ({fa(w.rounds)} دور)")
    blocks.append("\n".join(wave_lines))
    notable = [t for w in r.waves for t in w.highlights][-4:]
    if notable:
        blocks.append("\n".join(notable))
    ranking = []
    for p in r.payouts:
        gains = [f"⚔️ {fa(p.damage)} آسیب ({fa(round(p.share * 100))}٪)"]
        if p.level_up:
            gains.append(f"🎉 سطح {fa(p.level_up)}")
        if p.chest:
            gains.append("🎁 صندوقچه‌ی جادویی")
        ranking.append((p.mention, gains))
    blocks.append("\n".join([f"🏅 {bold('سهم هر جنگجو')}", "", *tidy_list(ranking, 10)]))
    blocks.append("🪙 پاداش هر نفر در دکمه‌های زیر 👇")
    return headline("\n\n".join(blocks))


def result_buttons(r: RunResult):  # noqa: ANN201
    info = DgCb(action="info", id=r.lobby.id)
    rows = [[Button.inline("🏆 پیروزی" if r.cleared else "💀 شکست", info, style="success" if r.cleared else None)]]
    for p in r.payouts[:5]:
        rows.append([Button.inline(p.name, info), Button.inline(f"🪙 {fa(p.gold)}", info), Button.inline(f"⭐ {fa(p.xp)}", info)])
    return rows


@router.callback_query(DgCb.filter())
async def on_button(query: CallbackQuery, callback_data: DgCb, services: Services) -> None:
    if callback_data.action == "info":
        await query.answer()
        return
    player = await services.players.require(query.from_user.id)
    message = query.message
    if callback_data.action == "join":
        view = await services.gdungeon.join(callback_data.id, player)
        if message is not None:
            with contextlib.suppress(BaleAPIError):
                await message.edit_text(lobby_text(view), buttons=lobby_buttons(view.id))
        await query.answer("⚔️ پیوستید!")
    elif callback_data.action == "start":
        result = await services.gdungeon.start(callback_data.id, player)  # refused (not the opener, too few): the lobby stays as it was
        if message is not None:
            with contextlib.suppress(BaleAPIError):
                await message.edit_text(progress_text(result.lobby.members, ROOMS[0], services.ctx.balance.gdungeon_run_seconds))
            deliver_later(message, services, result)
        await query.answer("🚀 سیاه‌چال شروع شد؛ نتیجه تا دو دقیقه‌ی دیگر")
    else:
        await query.answer()
