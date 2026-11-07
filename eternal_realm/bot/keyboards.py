"""Inline keyboard builders."""

from __future__ import annotations

from baleropy import Button
from baleropy.types import InlineKeyboardButton

from ..game.data.classes import CLASSES
from ..game.data.races import RACES
from .callbacks import ClassCb, MenuCb, RaceCb

Rows = list[list[InlineKeyboardButton]]

#: (page id, label) of the private main menu. Feature modules append their own entries.
MENU_ENTRIES: list[tuple[str, str]] = [
    ("profile", "👤 شخصیت من"),
    ("help", "❓ راهنما"),
]


def _grid(buttons: list[InlineKeyboardButton], per_row: int = 2) -> Rows:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def race_buttons() -> Rows:
    return _grid([Button.inline(f"{r.emoji} {r.name}", RaceCb(id=r.id)) for r in RACES.values()])


def class_buttons() -> Rows:
    return _grid([Button.inline(f"{c.emoji} {c.name}", ClassCb(id=c.id)) for c in CLASSES.values()])


def main_menu() -> Rows:
    return _grid([Button.inline(label, MenuCb(page=page)) for page, label in MENU_ENTRIES])


def back_to_menu() -> Rows:
    return [[Button.inline("🔙 منوی اصلی", MenuCb(page="home"))]]
