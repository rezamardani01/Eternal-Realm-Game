"""Group dungeon UI: the lobby message, join/start buttons and the result report."""

from __future__ import annotations

import contextlib

from baleropy import Button, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery

from ..game.services.group_dungeon import MAX_PLAYERS, MIN_PLAYERS, LobbyView, RunResult
from ..shared.text import bold, duration, fa, headline
from .callbacks import DgCb
from .services import Services

router = Router(name="group-dungeon")
MEDALS = ("🥇", "🥈", "🥉")


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
    for i, p in enumerate(r.payouts):
        medal = MEDALS[i] if i < 3 else "🔹"
        entry = f"{medal} {p.mention} — {fa(p.damage)} آسیب ({fa(round(p.share * 100))}٪)"
        if p.level_up:
            entry += f"\n🎉 رسید به سطح {fa(p.level_up)}"
        if p.chest:
            entry += "\n🎁 صندوقچه‌ی جادویی"
        ranking.append(entry)
    blocks.append(f"🏅 {bold('سهم هر جنگجو')}\n" + "\n".join(ranking))
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
        if message is not None:
            with contextlib.suppress(BaleAPIError):
                await message.edit_text(headline(f"🕳️ {bold('درها بسته شد...')}\n\nجنگجویان به قلب تاریکی می‌روند 👣"))
        result = await services.gdungeon.start(callback_data.id, player)
        if message is not None:
            with contextlib.suppress(BaleAPIError):
                await message.delete()
            await message.answer(result_text(result), buttons=result_buttons(result))
        await query.answer("🚀")
    else:
        await query.answer()
