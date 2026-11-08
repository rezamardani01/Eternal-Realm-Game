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
    _gear("rusty_sword", "شمشیر زنگ‌زده", "🗡️", Kind.WEAPON, 1, 300, 2, atk=5),
    _gear("broad_sword", "شمشیر پهن", "⚔️", Kind.WEAPON, 2, 1800, 8, atk=11),
    _gear("knight_sword", "شمشیر شوالیه", "⚔️", Kind.WEAPON, 4, 7500, 18, atk=21, defense=2),
    _gear("battle_axe", "تبر جنگی", "🪓", Kind.WEAPON, 3, 3800, 13, atk=17),
    _gear("war_hammer", "پتک جنگ", "🔨", Kind.WEAPON, 4, 8200, 19, atk=25),
    _gear("long_bow", "کمان بلند", "🏹", Kind.WEAPON, 2, 1500, 7, atk=9, speed=2),
    _gear("elven_bow", "کمان الفی", "🏹", Kind.WEAPON, 4, 7800, 18, atk=19, speed=5, luck=3),
    _gear("twin_daggers", "خنجرهای دوقلو", "🔪", Kind.WEAPON, 3, 3400, 12, atk=11, speed=5, luck=2),
    _gear("assassin_blade", "تیغ آدم‌کش", "🗡️", Kind.WEAPON, 4, 7200, 17, atk=16, speed=7, luck=4),
    _gear("oak_staff", "عصای بلوط", "🪄", Kind.WEAPON, 2, 1600, 7, magic=10),
    _gear("sage_staff", "عصای خردمند", "🔮", Kind.WEAPON, 3, 3600, 12, magic=15, luck=1),
    _gear("storm_staff", "عصای طوفان", "⚡", Kind.WEAPON, 4, 8000, 19, magic=24, speed=2),
    # --- shields / helmets / armor / boots -----------------------------------------------------
    _gear("wooden_shield", "سپر چوبی", "🛡️", Kind.SHIELD, 1, 140, defense=3),
    _gear("iron_shield", "سپر آهنی", "🛡️", Kind.SHIELD, 2, 850, 6, defense=8),
    _gear("bronze_shield", "سپر برنزی", "🛡️", Kind.SHIELD, 2, 1300, 4, defense=6, hp=5),
    _gear("tower_shield", "سپر برجی", "🛡️", Kind.SHIELD, 3, 3300, 12, defense=13, hp=15),
    _gear("knight_shield", "سپر شوالیه", "🛡️", Kind.SHIELD, 4, 7000, 17, defense=18, hp=25),
    _gear("leather_cap", "کلاه چرمی", "🧢", Kind.HELMET, 1, 120, defense=2, hp=5),
    _gear("iron_helm", "کلاه‌خود آهنی", "🪖", Kind.HELMET, 2, 800, 6, defense=5, hp=15),
    _gear("bronze_helm", "کلاه‌خود برنزی", "🪖", Kind.HELMET, 2, 1100, 4, defense=4, hp=10),
    _gear("steel_helm", "کلاه‌خود فولادی", "🪖", Kind.HELMET, 3, 2900, 11, defense=8, hp=25),
    _gear("knight_helm", "کلاه‌خود شوالیه", "🪖", Kind.HELMET, 4, 6500, 17, defense=11, hp=35),
    _gear("leather_armor", "زره چرمی", "🦺", Kind.ARMOR, 1, 260, defense=4, hp=15),
    _gear("chain_mail", "زره زنجیری", "🦺", Kind.ARMOR, 3, 2600, 10, defense=10, hp=30),
    _gear("padded_armor", "زره پوشالی", "🦺", Kind.ARMOR, 1, 600, 3, defense=6, hp=20),
    _gear("bronze_armor", "زره برنزی", "🦺", Kind.ARMOR, 2, 1700, 6, defense=8, hp=25),
    _gear("steel_armor", "زره فولادی", "🦺", Kind.ARMOR, 3, 4200, 13, defense=14, hp=40),
    _gear("knight_armor", "زره شوالیه", "🦺", Kind.ARMOR, 4, 9000, 18, defense=19, hp=55),
    _gear("mage_robe", "ردای جادوگر", "👘", Kind.ARMOR, 3, 3800, 12, defense=6, hp=30, magic=8),
    _gear("dragon_armor", "زره اژدها", "🐲", Kind.ARMOR, 5, 0, 20, defense=24, hp=70),
    _gear("dragonbane_helm", "کلاه‌خود اژدهاکش", "🪖", Kind.HELMET, 5, 0, 18, defense=12, hp=40),
    _gear("dragonbane_boots", "چکمه اژدهاکش", "👢", Kind.BOOTS, 5, 0, 18, speed=9, defense=4, luck=2),
    _gear("leather_boots", "چکمه چرمی", "👢", Kind.BOOTS, 1, 120, speed=2),
    _gear("swift_boots", "چکمه تندرو", "👟", Kind.BOOTS, 3, 2200, 10, speed=6, luck=1),
    _gear("traveler_boots", "چکمه مسافر", "👢", Kind.BOOTS, 2, 900, 5, speed=4),
    _gear("iron_boots", "چکمه آهنی", "👢", Kind.BOOTS, 3, 2400, 10, speed=2, defense=6),
    _gear("wind_boots", "چکمه باد", "👟", Kind.BOOTS, 4, 6200, 16, speed=10, luck=2),
    # --- jewellery -----------------------------------------------------------------------------
    _gear("strength_ring", "انگشتر قدرت", "💍", Kind.RING, 3, 2800, 8, atk=5),
    _gear("luck_ring", "انگشتر شانس", "💍", Kind.RING, 3, 2800, 8, luck=7),
    _gear("life_amulet", "گردنبند حیات", "📿", Kind.AMULET, 3, 3000, 8, hp=45),
    _gear("guard_ring", "انگشتر نگهبان", "💍", Kind.RING, 3, 2800, 8, defense=5, hp=10),
    _gear("sage_ring", "انگشتر خردمند", "💍", Kind.RING, 3, 2800, 8, magic=6),
    _gear("swift_amulet", "گردنبند تیزپا", "📿", Kind.AMULET, 3, 3000, 8, speed=5, luck=1),
    _gear("ward_amulet", "گردنبند نگهبان", "📿", Kind.AMULET, 4, 6800, 16, defense=8, hp=40),
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


def item_value(item: Item, upgrade: int = 0) -> int:
    """What an item is roughly worth in coins: its shop price, else a multiple of what the shop pays for it."""
    base = item.buy if item.buy > 0 else (item.sell * 3 if item.sell > 0 else 50 * item.rarity)
    return max(1, round(base * (1 + 0.5 * upgrade)))


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
