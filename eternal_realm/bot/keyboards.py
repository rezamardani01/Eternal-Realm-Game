"""Inline keyboard builders."""

from __future__ import annotations

from baleropy import Button
from baleropy.types import InlineKeyboardButton

from ..game.data.classes import CLASSES
from ..game.data.races import RACES
from ..game.engine.combat import Fighter
from .callbacks import ClassCb, DuelCb, MenuCb, RaceCb, UpgradeCb

Rows = list[list[InlineKeyboardButton]]

#: (page id, label) of the private main menu. Feature modules append their own entries.
MENU_ENTRIES: list[tuple[str, str]] = [
    ("profile", "👤 شخصیت من"),
    ("inventory", "🎒 کوله‌پشتی"),
    ("equipment", "🧰 تجهیزات"),
    ("shop", "🛒 فروشگاه"),
    ("help", "❓ راهنما"),
]


def _grid(buttons: list[InlineKeyboardButton], per_row: int = 2) -> Rows:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def race_buttons() -> Rows:
    return _grid([Button.inline(f"{r.emoji} {r.name}", RaceCb(id=r.id)) for r in RACES.values()])


def class_buttons() -> Rows:
    return _grid([Button.inline(f"{c.emoji} {c.name}", ClassCb(id=c.id)) for c in CLASSES.values()])


def start_button(bot_username: str) -> list[InlineKeyboardButton]:
    return [Button.url("🎮 شروع بازی", f"https://ble.ir/{bot_username}?start=1")]


def main_menu() -> Rows:
    return _grid([Button.inline(label, MenuCb(page=page)) for page, label in MENU_ENTRIES])


def back_to_menu() -> Rows:
    return [[Button.inline("🔙 منوی اصلی", MenuCb(page="home"))]]


def upgrade_confirm(gear_id: int, level: int) -> Rows:
    return [[Button.inline(f"🔨 ارتقا به +{level}", UpgradeCb(id=gear_id, level=level), style="success")]]


def duel_invite(duel_id: int) -> Rows:
    return [
        [
            Button.inline("⚔️ قبول مبارزه", DuelCb(action="accept", id=duel_id), style="success"),
            Button.inline("❌ رد کردن", DuelCb(action="decline", id=duel_id), style="danger"),
        ]
    ]


def duel_actions(duel_id: int, fighter: Fighter) -> Rows:
    wait = fighter.skill_ready_in - 1
    skill = f"{fighter.skill_emoji} {fighter.skill_name}" + (f" ({wait})" if wait > 0 else "")
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
