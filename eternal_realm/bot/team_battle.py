"""Team battles in groups: the lobby panel with seats, the battle panel and the janitor step."""

from __future__ import annotations

import contextlib

from baleropy import Button, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery

from ..game.engine import team_fight
from ..game.engine.combat import Action, Fighter
from ..game.services.team_battles import SEATS, Lobby, TeamUpdate
from ..shared.errors import GameError
from ..shared.text import bar, bold, duration, fa
from .callbacks import TeamCb
from .keyboards import Rows
from .services import Services

router = Router(name="team_battle")

TEAM_MARKS = ("🔵", "🔴")
TEAM_NAMES = ("تیم اول", "تیم دوم")
ACTIONS = {"attack": Action.ATTACK, "skill": Action.SKILL, "defend": Action.DEFEND, "surrender": Action.SURRENDER}


# --- texts --------------------------------------------------------------------------------------
def _team_title(team: int) -> str:
    return f"{TEAM_MARKS[team]} {bold(TEAM_NAMES[team])}"


def lobby_text(lobby: Lobby, seconds_left: int) -> str:
    creator = next((p for _t, _s, p in lobby.members if p.id == lobby.creator_id), None)
    out = [f"⚔️ {bold('مبارزه‌ی تیمی')}", ""]
    for team in (0, 1):
        out.append(_team_title(team))
        for seat in range(SEATS):
            player = lobby.at(team, seat)
            out.append(f"{player.char_class.emoji} {player.mention}" if player else f"▫️ جایگاه {fa(seat + 1)} خالی")
        out.append("")
    out += [
        "هر کس روی یک جایگاه بزند همان‌جا می‌نشیند؛ روی جایگاه خودش که بزند برمی‌خیزد.",
        "سازنده با زدن روی نام هر نفر او را بیرون می‌اندازد و او دیگر نمی‌تواند وارد شود.",
        "تیمی که آغاز می‌کند با قرعه مشخص می‌شود.",
        "هر تیم می‌تواند تعداد متفاوتی جنگجو داشته باشد.",
        "",
        f"👑 سازنده: {creator.mention if creator else '—'}",
        f"⏳ {duration(max(0, seconds_left))} تا بسته شدن ثبت‌نام",
    ]
    return "\n".join(out)


def _member_lines(f: Fighter, current: bool) -> list[str]:
    percent = team_fight.hp_percent(f)
    if f.hp <= 0:
        return [f"💀 {f.mention or f.name} — از پا افتاد"]
    head = f"{'👉' if current else f.emoji} {f.mention or bold(f.name)}"
    return [head, f"❤️ {bar(f.hp, f.max_hp, 8)} {fa(percent)}٪ · {team_fight.describe(f)}"]


def battle_text(update: TeamUpdate, turn_seconds: int) -> str:
    battle = update.battle
    out = [f"⚔️ {bold('نبرد تیمی')}", ""]
    for team in (0, 1):
        out.append(_team_title(team))
        for i in battle.members(team):
            out += _member_lines(battle.fighters[i], not battle.finished and i == battle.actor)
        out.append("")
    story = [f"• {line.strip()}" for line in update.lines if line.strip()][-6:]
    if story:
        out += [f"📜 {bold('آخرین حرکت‌ها')}", *story, ""]
    out += [
        f"🎯 نوبت {battle.current.mention or bold(battle.current.name)} ({TEAM_NAMES[battle.current_team]})",
        f"🔁 دور {fa(battle.round)} از {fa(battle.max_rounds)} · ⏳ {duration(turn_seconds)}",
    ]
    return "\n".join(out)


def result_text(update: TeamUpdate) -> str:
    battle = update.battle
    out = [f"🏁 {bold('پایان نبرد تیمی')}", ""]
    if battle.winner is None:
        out.append(f"🤝 {bold('مساوی شد؛ هر دو تیم دلاور بودند!')}")
    else:
        out.append(f"🏆 {bold(TEAM_NAMES[battle.winner] + ' پیروز شد!')}")
    out += [f"🔁 در دور {fa(battle.round)} از {fa(battle.max_rounds)}", ""]
    for team in (0, 1):
        verdict = "" if battle.winner is None else (" — برنده" if battle.winner == team else " — بازنده")
        out.append(f"{TEAM_MARKS[team]} {bold(TEAM_NAMES[team])}{verdict}")
        for i in battle.members(team):
            f = battle.fighters[i]
            if f.hp <= 0:
                out.append(f"💀 {f.mention or f.name} — از پا افتاد")
            else:
                out += [f"{f.emoji} {f.mention or f.name}", f"❤️ {bar(f.hp, f.max_hp, 8)} {fa(team_fight.hp_percent(f))}٪"]
            payout = update.payouts.get(f.player_id)
            if payout is not None and (payout.gold or payout.xp):
                gains = ([f"{fa(payout.gold)} سکه"] if payout.gold else []) + ([f"{fa(payout.xp)} تجربه"] if payout.xp else [])
                out.append(f"🎁 {' و '.join(gains)}")
        out.append("")
    story = [f"• {line.strip()}" for line in update.lines if line.strip()][-2:]
    if story:
        out += [f"📜 {bold('ضربه‌ی پایانی')}", *story]
    return chr(10).join(out).strip()


# --- buttons ------------------------------------------------------------------------------------
def lobby_buttons(lobby: Lobby) -> Rows:
    rows: Rows = [[Button.inline(f"{TEAM_MARKS[t]} {TEAM_NAMES[t]}", TeamCb(action="info", id=lobby.id)) for t in (0, 1)]]
    for seat in range(SEATS):
        row = []
        for team in (0, 1):
            player = lobby.at(team, seat)
            label = f"{player.char_class.emoji} {player.name}" if player else f"➕ جایگاه {fa(seat + 1)}"
            row.append(Button.inline(label, TeamCb(action="sit", id=lobby.id, arg=team * 10 + seat),
                                     style="primary" if player else None))
        rows.append(row)
    rows.append([
        Button.inline("⚔️ شروع مبارزه", TeamCb(action="start", id=lobby.id), style="success"),
        Button.inline("❌ لغو", TeamCb(action="cancel", id=lobby.id), style="danger"),
    ])
    return rows


def action_buttons(battle_id: int, fighter: Fighter) -> Rows:
    wait = fighter.skill_ready_in - 1
    skill = f"{fighter.skill_emoji} {fighter.skill_name}" + (f" ({fa(wait)})" if wait > 0 else "")
    return [
        [
            Button.inline("⚔️ حمله", TeamCb(action="attack", id=battle_id), style="primary"),
            Button.inline(skill, TeamCb(action="skill", id=battle_id), style="success" if wait <= 0 else None),
        ],
        [
            Button.inline("🛡️ دفاع", TeamCb(action="defend", id=battle_id)),
            Button.inline("🏳️ تسلیم", TeamCb(action="surrender", id=battle_id), style="danger"),
        ],
        [Button.inline("❌ لغو مبارزه (سازنده)", TeamCb(action="cancel", id=battle_id))],
    ]


def result_buttons(battle_id: int) -> Rows:
    return [[Button.inline("⚔️ مبارزه‌ی تیمی تازه", TeamCb(action="again", id=battle_id), style="primary")]]


def render(update: TeamUpdate, turn_seconds: int) -> tuple[str, Rows]:
    if update.finished:
        return result_text(update), result_buttons(update.lobby.id)
    return battle_text(update, turn_seconds), action_buttons(update.lobby.id, update.battle.current)


def _seconds_left(services: Services, lobby: Lobby) -> int:
    return lobby.expires_at - services.ctx.now()


# --- taps ---------------------------------------------------------------------------------------
@router.callback_query(TeamCb.filter())
async def on_team_button(query: CallbackQuery, callback_data: TeamCb, services: Services) -> None:
    message = query.message
    if message is None:
        await query.answer()
        return
    player = await services.players.require(query.from_user.id)
    service, action, battle_id = services.teams, callback_data.action, callback_data.id
    turn_seconds = services.ctx.balance.duel_turn_seconds

    if action == "info":
        await query.answer()
        return
    if action == "sit":
        lobby, note = await service.sit(battle_id, player, callback_data.arg // 10, callback_data.arg % 10)
        await message.edit_text(lobby_text(lobby, _seconds_left(services, lobby)), buttons=lobby_buttons(lobby))
        await query.answer(note)
        return
    if action == "start":
        update = await service.start(battle_id, player)
        text, buttons = render(update, turn_seconds)
        await message.edit_text(text, buttons=buttons)
    elif action == "cancel":
        await service.cancel(battle_id, player)
        await message.edit_text("🏳️ مبارزه‌ی تیمی را سازنده‌اش لغو کرد و پاداشی داده نشد. هر وقت خواستید دوباره بسازید!")
    elif action == "again":
        lobby = await service.create(message.chat.id, player)
        sent = await message.answer(lobby_text(lobby, _seconds_left(services, lobby)), buttons=lobby_buttons(lobby))
        await service.attach_message(lobby.id, sent.message_id)
        await query.answer("⚔️ مبارزه‌ی تازه ساخته شد!")
        return
    elif action in ACTIONS:
        update = await service.act(battle_id, player, ACTIONS[action])
        text, buttons = render(update, turn_seconds)
        await message.edit_text(text, buttons=buttons)
    else:
        raise GameError("این دکمه از کار افتاده است؛ فرمان تازه‌ای بدهید.")
    await query.answer()


# --- janitor ------------------------------------------------------------------------------------
async def announce(bot, services: Services) -> None:  # noqa: ANN001
    """Janitor step: close lobbies nobody started and play on for heroes whose turn ran out."""
    turn_seconds = services.ctx.balance.duel_turn_seconds
    for item in await services.teams.expire_stale():
        lobby = item.lobby if isinstance(item, TeamUpdate) else item
        if lobby.message_id is None:
            continue
        with contextlib.suppress(BaleAPIError):
            if isinstance(item, TeamUpdate):
                text, buttons = render(item, turn_seconds)
                await bot.edit_message_text(lobby.chat_id, lobby.message_id, text, buttons=buttons)
            else:
                await bot.edit_message_text(
                    lobby.chat_id, lobby.message_id, "⌛ مبارزه‌ی تیمی شروع نشد و ثبت‌نامش بسته شد. هر وقت خواستید دوباره بسازید!"
                )
