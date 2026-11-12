"""The item catalogue: materials, potions, chests and tickets. All prices are NPC prices in gold; players set their own
on the market. (War gear lives in arms.py.)"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ...shared.text import normalize


class Kind(StrEnum):
    CONSUMABLE = "consumable"
    MATERIAL = "material"
    CHEST = "chest"


RARITIES: dict[int, tuple[str, str]] = {
    1: ("⚪", "معمولی"),
    2: ("🟢", "غیرمعمول"),
    3: ("🔵", "کمیاب"),
    4: ("🟣", "حماسی"),
    5: ("🟠", "افسانه‌ای"),
    6: ("🔴", "اسطوره‌ای"),
}


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    emoji: str
    kind: Kind
    rarity: int = 1
    #: NPC shop price (0 = not sold by the shop)
    buy: int = 0
    #: gold the NPC pays when a player sells it (0 = cannot be sold to the NPC)
    sell: int = 0
    #: energy restored when used
    energy: int = 0
    tradable: bool = True

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"

    @property
    def rarity_label(self) -> str:
        icon, name = RARITIES[self.rarity]
        return f"{icon} {name}"


def _mat(id_, name, emoji, sell, rarity=1, kind=Kind.MATERIAL, **kw) -> Item:  # noqa: ANN001, ANN003
    return Item(id_, name, emoji, kind, rarity, sell=sell, **kw)


_ITEMS: tuple[Item, ...] = (
    # --- consumables ---------------------------------------------------------------------------
    Item("energy_potion", "معجون انرژی", "⚡", Kind.CONSUMABLE, 1, buy=120, sell=40, energy=40),
    Item("small_energy_potion", "معجون انرژی کوچک", "🧪", Kind.CONSUMABLE, 1, buy=60, sell=20, energy=20),
    Item("medium_energy_potion", "معجون انرژی متوسط", "⚗️", Kind.CONSUMABLE, 2, buy=250, sell=80, energy=70),
    Item("grand_energy_potion", "معجون انرژی بی‌کران", "🍶", Kind.CONSUMABLE, 4, buy=900, sell=300, energy=200),
    Item("big_energy_potion", "معجون انرژی بزرگ", "🔋", Kind.CONSUMABLE, 3, buy=400, sell=130, energy=100),
    # --- materials from activities --------------------------------------------------------------
    _mat("small_fish", "ماهی کوچک", "🐟", 12),
    _mat("trout", "قزل‌آلا", "🐠", 28, 2),
    _mat("golden_fish", "ماهی طلایی", "🐡", 160, 4),
    _mat("stone", "سنگ", "🪨", 8),
    _mat("iron_ore", "سنگ آهن", "⛓️", 30, 2),
    _mat("gold_ore", "سنگ طلا", "🥇", 90, 3),
    _mat("crystal_shard", "پاره‌کریستال", "💠", 220, 4),
    _mat("herb", "گیاه شفابخش", "🌿", 14),
    _mat("moon_herb", "گیاه ماه‌تاب", "🍀", 70, 3),
    _mat("old_scroll", "طومار کهنه", "📜", 45, 2),
    _mat("monster_fang", "دندان هیولا", "🦷", 35, 2),
    _mat("monster_hide", "پوست هیولا", "🧶", 25),
    _mat("dragon_scale", "فلس اژدها", "🐉", 300, 5),
    _mat("wood", "چوب درخت", "🪵", 10),
    _mat("wheat", "گندم", "🌾", 9),
    _mat("honey", "عسل طلایی", "🍯", 55, 3),
    _mat("ancient_coin", "سکه‌ی باستانی", "🏺", 120, 4),
    # --- service tickets (sold in the premium vault; they cannot be traded) -----------------------
    _mat("rename_ticket", "برگه‌ی تغییر نام", "🏷️", 0, 3, tradable=False),
    _mat("race_ticket", "برگه‌ی تغییر نژاد", "🧬", 0, 4, tradable=False),
    _mat("class_ticket", "برگه‌ی تغییر کلاس", "⚔️", 0, 4, tradable=False),
    # --- chests (loot tables live in data/chests.py) --------------------------------------------
    Item("wooden_chest", "صندوقچه چوبی", "📦", Kind.CHEST, 2, buy=600, sell=0),
    Item("magic_chest", "صندوقچه جادویی", "🎁", Kind.CHEST, 4, sell=0),
    Item("royal_chest", "صندوقچه سلطنتی", "👑", Kind.CHEST, 5, sell=0),
)

ITEMS: dict[str, Item] = {item.id: item for item in _ITEMS}
_BY_NAME = {normalize(item.name): item for item in _ITEMS}


def get_item(item_id: str) -> Item:
    return ITEMS[item_id]


def item_value(item: Item) -> int:
    """What an item is roughly worth in coins: its shop price, else a multiple of what the shop pays for it."""
    base = item.buy if item.buy > 0 else (item.sell * 3 if item.sell > 0 else 50 * item.rarity)
    return max(1, round(base))


def find_item(text: str) -> Item | None:
    """Look an item up by its Persian name (exact, then unique prefix)."""
    query = normalize(text)
    if not query:
        return None
    if query in _BY_NAME:
        return _BY_NAME[query]
    matches = [item for name, item in _BY_NAME.items() if name.startswith(query)]
    return matches[0] if len(matches) == 1 else None
