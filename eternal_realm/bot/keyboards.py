"""Inline keyboard builders that are not part of the personal panel."""

from __future__ import annotations

from baleropy import Button
from baleropy.types import InlineKeyboardButton

from ..game.data.classes import CLASSES
from ..game.data.races import RACES
from ..game.engine.combat import Fighter
from ..shared.text import duration, fa
from .callbacks import BossCb, ClassCb, DuelCb, PanelCb, RaceCb

Rows = list[list[InlineKeyboardButton]]


def grid(buttons: list[InlineKeyboardButton], per_row: int = 2) -> Rows:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def race_buttons() -> Rows:
    return grid([Button.inline(f"{r.emoji} {r.name}", RaceCb(id=r.id)) for r in RACES.values()])


def class_buttons() -> Rows:
    return grid([Button.inline(f"{c.emoji} {c.name}", ClassCb(id=c.id)) for c in CLASSES.values()])


def start_button(bot_username: str) -> list[InlineKeyboardButton]:
    return [Button.url("🎮 شروع بازی", f"https://ble.ir/{bot_username}?start=1")]


def open_panel_button(bot_username: str) -> list[InlineKeyboardButton]:
    return [Button.url("📲 باز کردن پنل شخصی", f"https://ble.ir/{bot_username}?start=panel")]


def panel_button(label: str, screen: str, owner: int, a: str = "", b: str = "") -> InlineKeyboardButton:
    return Button.inline(label, PanelCb(s=screen, a=a or None, b=b or None, o=owner))


def result_rows(
    owner: int, *, gold: int = 0, crystal: int = 0, xp: int = 0, items=(), energy: int, again: str,  # noqa: ANN001
    hp: tuple[int, int] | None = None, wait: int = 0,
) -> Rows:
    """Glass buttons under an activity result: what you got, your energy, and what to do next."""
    chips = []
    if gold:
        chips.append(panel_button(f"🪙 {fa(gold)} سکه", "note", owner, "gold"))
    if xp:
        chips.append(panel_button(f"⭐ {fa(xp)} تجربه", "note", owner, "xp"))
    if crystal:
        chips.append(panel_button(f"💎 {fa(crystal)} کریستال", "note", owner, "crystal"))
    for label, qty, item_id in items:
        chips.append(panel_button(f"{label} ×{fa(qty)}", "note", owner, "item", item_id))
    rows = grid(chips, 2)
    status = [panel_button(f"⚡ انرژی شما: {fa(energy)}", "note", owner, "energy")]
    if hp is not None:
        status.insert(0, panel_button(f"❤️ جان: {fa(hp[0])}/{fa(hp[1])}", "note", owner, "hp"))
    rows.append(status)
    again_label = f"🔁 دوباره · {duration(wait)}" if wait else "🔁 دوباره"
    rows.append([panel_button(again_label, "act", owner, again), panel_button("🗺️ ماجراجویی", "adv", owner)])
    return rows


def boss_buttons(boss_id: int) -> Rows:
    return [
        [
            Button.inline("⚔️ پیوستن به نبرد", BossCb(action="join", id=boss_id), style="success"),
            Button.inline("🚀 شروع نبرد", BossCb(action="start", id=boss_id), style="danger"),
        ]
    ]


def duel_invite(duel_id: int) -> Rows:
    return [
        [
            Button.inline("⚔️ قبول مبارزه", DuelCb(action="accept", id=duel_id), style="success"),
            Button.inline("❌ رد کردن", DuelCb(action="decline", id=duel_id), style="danger"),
        ]
    ]


def duel_actions(duel_id: int, fighter: Fighter) -> Rows:
    wait = fighter.skill_ready_in - 1
    skill = f"{fighter.skill_emoji} {fighter.skill_name}" + (f" ({fa(wait)})" if wait > 0 else "")
    return [
        [
            Button.inline("⚔️ حمله", DuelCb(action="attack", id=duel_id), style="primary"),
            Button.inline(skill, DuelCb(action="skill", id=duel_id), style="success" if wait <= 0 else None),
        ],
        [
            Button.inline("🛡️ دفاع", DuelCb(action="defend", id=duel_id)),
            Button.inline("🏳️ تسلیم", DuelCb(action="surrender", id=duel_id), style="danger"),
        ],
    ]
