"""Inline keyboard builders that are not part of the personal panel."""

from __future__ import annotations

from baleropy import Button
from baleropy.types import InlineKeyboardButton

from ..game.data.chests import CHESTS
from ..game.data.classes import CLASSES
from ..game.data.items import get_item
from ..game.data.packs import PACKS
from ..game.data.races import RACES
from ..game.engine.combat import Fighter
from ..shared.text import fa
from .callbacks import BuyCb, ClassCb, DuelCb, PanelCb, RaceCb

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


def premium_buttons(payments_enabled: bool, owner: int) -> Rows:
    rows: Rows = []
    if payments_enabled:
        for pack in PACKS.values():
            label = f"{pack.label} — {fa(pack.price_toman)} تومان"
            rows.append([Button.inline(label, BuyCb(kind="cash", id=pack.id), style="success")])
    for chest in CHESTS.values():
        if chest.price and chest.price[0] == "crystal":
            item = get_item(chest.item_id)
            rows.append([panel_button(f"{item.label} — {fa(chest.price[1])} 💎", "cbuyq", owner, item.id)])
    rows.append([panel_button("🔙 بازگشت", "home", owner)])
    return rows


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
