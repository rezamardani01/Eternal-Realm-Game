"""The item catalogue. All prices are NPC prices in gold; players set their own on the market."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from ...shared.text import normalize
from .stats import Stats


class Kind(StrEnum):
    WEAPON = "weapon"
    SHIELD = "shield"
    HELMET = "helmet"
    ARMOR = "armor"
    BOOTS = "boots"
    RING = "ring"
    AMULET = "amulet"
    CONSUMABLE = "consumable"
    MATERIAL = "material"
    CHEST = "chest"


GEAR_KINDS = frozenset(
    {Kind.WEAPON, Kind.SHIELD, Kind.HELMET, Kind.ARMOR, Kind.BOOTS, Kind.RING, Kind.AMULET}
)

SLOT_LABELS: dict[str, str] = {
    "weapon": "⚔️ سلاح",
    "shield": "🛡️ سپر",
    "helmet": "🪖 کلاه‌خود",
    "armor": "🦺 زره",
    "boots": "👢 کفش",
    "ring": "💍 انگشتر",
    "amulet": "📿 گردنبند",
}

RARITIES: dict[int, tuple[str, str]] = {
    1: ("⚪", "معمولی"),
    2: ("🟢", "غیرمعمول"),
    3: ("🔵", "کمیاب"),
    4: ("🟣", "حماسی"),
    5: ("🟠", "افسانه‌ای"),
    6: ("🔴", "اسطوره‌ای"),
}

MAX_UPGRADE = 10


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    emoji: str
    kind: Kind
    rarity: int = 1
    stats: Stats = Stats()
    #: NPC shop price (0 = not sold by the shop)
    buy: int = 0
    #: gold the NPC pays when a player sells it (0 = cannot be sold to the NPC)
    sell: int = 0
    level_req: int = 1
    #: energy restored when used
    energy: int = 0
    tradable: bool = True

    @property
    def is_gear(self) -> bool:
        return self.kind in GEAR_KINDS

    @property
    def slot(self) -> str | None:
        return self.kind.value if self.is_gear else None

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"

    @property
    def rarity_label(self) -> str:
        icon, name = RARITIES[self.rarity]
        return f"{icon} {name}"


def _gear(id_, name, emoji, kind, rarity, buy, level_req=1, **stats) -> Item:  # noqa: ANN001, ANN003
    return Item(id_, name, emoji, kind, rarity, Stats(**stats), buy=buy, sell=buy // 3 if buy else 0,
                level_req=level_req)


def _mat(id_, name, emoji, sell, rarity=1, kind=Kind.MATERIAL, **kw) -> Item:  # noqa: ANN001, ANN003
    return Item(id_, name, emoji, kind, rarity, sell=sell, **kw)


_ITEMS: tuple[Item, ...] = (
    # --- weapons -----------------------------------------------------------------------------
    _gear("wooden_sword", "شمشیر چوبی", "🗡️", Kind.WEAPON, 1, 150, atk=3),
    _gear("iron_sword", "شمشیر آهنی", "⚔️", Kind.WEAPON, 2, 900, 5, atk=8),
    _gear("steel_sword", "شمشیر فولادی", "⚔️", Kind.WEAPON, 3, 3200, 12, atk=15, speed=1),
    _gear("fire_sword", "شمشیر آتشین", "🔥", Kind.WEAPON, 5, 0, 20, atk=26, magic=6),
    _gear("short_bow", "کمان کوتاه", "🏹", Kind.WEAPON, 1, 160, atk=3, speed=2),
    _gear("hunter_bow", "کمان شکارچی", "🏹", Kind.WEAPON, 3, 3000, 12, atk=13, speed=3, luck=2),
    _gear("dagger", "خنجر", "🔪", Kind.WEAPON, 1, 150, atk=2, speed=3, luck=1),
    _gear("shadow_dagger", "خنجر سایه", "🗡️", Kind.WEAPON, 4, 0, 15, atk=14, speed=6, luck=4),
    _gear("wooden_staff", "عصای چوبی", "🪄", Kind.WEAPON, 1, 160, magic=5),
    _gear("crystal_staff", "عصای کریستالی", "🔮", Kind.WEAPON, 4, 4500, 15, magic=20, luck=2),
    # --- shields / helmets / armor / boots -----------------------------------------------------
    _gear("wooden_shield", "سپر چوبی", "🛡️", Kind.SHIELD, 1, 140, defense=3),
    _gear("iron_shield", "سپر آهنی", "🛡️", Kind.SHIELD, 2, 850, 6, defense=8),
    _gear("leather_cap", "کلاه چرمی", "🧢", Kind.HELMET, 1, 120, defense=2, hp=5),
    _gear("iron_helm", "کلاه‌خود آهنی", "🪖", Kind.HELMET, 2, 800, 6, defense=5, hp=15),
    _gear("leather_armor", "زره چرمی", "🦺", Kind.ARMOR, 1, 260, defense=4, hp=15),
    _gear("chain_mail", "زره زنجیری", "🦺", Kind.ARMOR, 3, 2600, 10, defense=10, hp=30),
    _gear("dragon_armor", "زره اژدها", "🐲", Kind.ARMOR, 5, 0, 20, defense=24, hp=70),
    _gear("dragonbane_helm", "کلاه‌خود اژدهاکش", "🪖", Kind.HELMET, 5, 0, 18, defense=12, hp=40),
    _gear("dragonbane_boots", "چکمه اژدهاکش", "👢", Kind.BOOTS, 5, 0, 18, speed=9, defense=4, luck=2),
    _gear("leather_boots", "چکمه چرمی", "👢", Kind.BOOTS, 1, 120, speed=2),
    _gear("swift_boots", "چکمه تندرو", "👟", Kind.BOOTS, 3, 2200, 10, speed=6, luck=1),
    # --- jewellery -----------------------------------------------------------------------------
    _gear("strength_ring", "انگشتر قدرت", "💍", Kind.RING, 3, 2800, 8, atk=5),
    _gear("luck_ring", "انگشتر شانس", "💍", Kind.RING, 3, 2800, 8, luck=7),
    _gear("life_amulet", "گردنبند حیات", "📿", Kind.AMULET, 3, 3000, 8, hp=45),
    # --- consumables ---------------------------------------------------------------------------
    Item("energy_potion", "معجون انرژی", "⚡", Kind.CONSUMABLE, 1, buy=120, sell=40, energy=40),
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


def find_item(text: str) -> Item | None:
    """Look an item up by its Persian name (exact, then unique prefix)."""
    query = normalize(text)
    if not query:
        return None
    if query in _BY_NAME:
        return _BY_NAME[query]
    matches = [item for name, item in _BY_NAME.items() if name.startswith(query)]
    return matches[0] if len(matches) == 1 else None


def upgraded_stats(item: Item, upgrade: int) -> Stats:
    """Stats of a gear piece at ``+upgrade``: every level adds 12% of the base, at least +1."""
    if upgrade <= 0:
        return item.stats
    values = {}
    for name, base in item.stats.as_dict().items():
        values[name] = base + (max(upgrade, math.ceil(base * 0.12 * upgrade)) if base > 0 else 0)
    return Stats(**values)


# --- starter equipment per class ---------------------------------------------------------------
STARTER_WEAPON: dict[str, str] = {
    "warrior": "wooden_sword",
    "mage": "wooden_staff",
    "archer": "short_bow",
    "guardian": "wooden_shield",
    "rogue": "dagger",
}
