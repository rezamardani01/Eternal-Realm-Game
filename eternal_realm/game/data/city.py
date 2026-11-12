"""Realm rule (دهکده): every hero may found a city, raise buildings, train an army and march on other cities.

All numbers live here so they can be tuned without touching the logic.
"""

from __future__ import annotations

from dataclasses import dataclass

RES = ("gold", "food", "wood", "stone", "iron")
RES_INFO: dict[str, tuple[str, str]] = {
    "gold": ("🪙", "سکه"), "food": ("🌾", "غذا"), "wood": ("🪵", "چوب"), "stone": ("🪨", "سنگ"), "iron": ("⛏️", "آهن"),
}

FLAGS: tuple[tuple[str, str], ...] = (
    ("🦁", "شیر"), ("🐺", "گرگ"), ("🦅", "عقاب"), ("🐉", "اژدها"), ("🔥", "شعله"), ("⚔️", "شمشیر"),
    ("🌙", "ماه"), ("⭐", "ستاره"), ("🛡️", "سپر"), ("👑", "تاج"), ("🌹", "گل سرخ"), ("🦂", "عقرب"),
)
FLAG_EMOJIS = tuple(f for f, _ in FLAGS)

NAME_MIN, NAME_MAX = 3, 16
#: taking gold out of the city treasury costs this much, and only this much may leave per day
WITHDRAW_FEE_PERCENT = 20
WITHDRAW_DAILY_CAP = 30_000
WITHDRAW_STEPS = (1_000, 5_000, 10_000)
START_SHIELD = 3 * 24 * 3600
#: a city hit this many times in a day (with at least a star each) gets a rest period of this length
REPEAT_HITS = 3
REPEAT_SHIELD = 12 * 3600
START_RESOURCES = {"gold": 3_000, "food": 3_000, "wood": 1_500, "stone": 1_500, "iron": 500}
START_BUILDINGS = {"castle": 1, "farm": 1, "lumber": 1, "stone_mine": 1, "barracks": 1}
START_POPULATION = 300
MAX_CASTLE = 10
MAX_ELAPSED_HOURS = 48
DAILY_ATTACKS = 8
SAME_TARGET_PER_DAY = 2
SHIELD_OPTIONS = ((12, 15), (24, 25))  # (hours, crystals)
PEOPLE_PER_WORKPLACE_LEVEL = 25


@dataclass(frozen=True)
class Building:
    id: str
    emoji: str
    name: str
    #: castle level needed to build it for the first time
    needs: int
    cost: tuple[int, int, int, int]  # gold, wood, stone, iron for level 1
    growth: float
    about: str
    group: str  # econ | mil | def | core
    max_level: int = 10


BUILDINGS: tuple[Building, ...] = (
    Building("castle", "🏰", "قلعه مرکزی", 1, (1000, 600, 600, 150), 1.9, "سطح و جایگاه‌های ساختمان شهر را تعیین می‌کند و سقف ساختمان‌ها را بالا می‌برد.", "core"),
    Building("farm", "🌾", "مزرعه", 1, (300, 250, 100, 0), 1.5, "هر سطح ساعتی ۶۰ غذا می‌دهد.", "econ"),
    Building("lumber", "🪵", "چوب‌بری", 1, (300, 100, 150, 0), 1.5, "هر سطح ساعتی ۴۰ چوب می‌دهد.", "econ"),
    Building("stone_mine", "🪨", "معدن سنگ", 1, (350, 250, 50, 0), 1.5, "هر سطح ساعتی ۳۰ سنگ می‌دهد.", "econ"),
    Building("iron_mine", "⛏️", "معدن آهن", 2, (450, 300, 300, 0), 1.55, "هر سطح ساعتی ۲۰ آهن می‌دهد.", "econ"),
    Building("market", "🏪", "بازار", 2, (500, 350, 250, 0), 1.55, "هر سطح ساعتی ۱۵۰ سکه درآمد می‌آورد.", "econ"),
    Building("warehouse", "🏚️", "انبار", 1, (400, 300, 200, 0), 1.5, "هر سطح ۴٬۰۰۰ به ظرفیت ذخیره‌ی منابع می‌افزاید.", "econ"),
    Building("barracks", "🏕️", "سربازخانه", 1, (400, 300, 200, 50), 1.55, "شمشیرزن و نیزه‌دار تربیت می‌کند و ظرفیت ارتش را بالا می‌برد.", "mil"),
    Building("archery", "🏹", "میدان تیراندازی", 2, (450, 400, 150, 50), 1.55, "کماندار تربیت می‌کند و ظرفیت ارتش را بالا می‌برد.", "mil"),
    Building("stable", "🐎", "اصطبل", 3, (600, 450, 250, 100), 1.6, "سواره‌نظام سبک و شوالیه تربیت می‌کند.", "mil"),
    Building("siege", "🏗️", "کارگاه محاصره", 5, (900, 700, 500, 250), 1.65, "دژکوب، منجنیق و برج محاصره می‌سازد.", "mil"),
    Building("smithy", "🔨", "آهنگری", 3, (700, 400, 400, 250), 1.6, "هر سطح ۳٪ به قدرت حمله‌ی همه‌ی نیروها می‌افزاید.", "mil"),
    Building("wall", "🧱", "دیوار شهر", 2, (500, 300, 600, 100), 1.6, "نیروهای پیاده را در برابر دیوار ناتوان‌تر می‌کند و مقاومت شهر را بالا می‌برد.", "def"),
    Building("tower", "🗼", "برج نگهبانی", 3, (650, 400, 450, 150), 1.6, "در هر دور نبرد به مهاجمان تیر می‌زند.", "def"),
    Building("hospital", "🏥", "بیمارستان", 4, (800, 500, 400, 100), 1.6, "هر سطح ۵٪ از تلفات نیروهای شهر را درمان می‌کند.", "def"),
)
_BUILDING = {b.id: b for b in BUILDINGS}

PRODUCTION = {"farm": ("food", 60), "lumber": ("wood", 40), "stone_mine": ("stone", 30), "iron_mine": ("iron", 20), "market": ("gold", 150)}
ECON_IDS = tuple(b.id for b in BUILDINGS if b.group == "econ")
TAX_PER_PERSON = 0.3
FOOD_PER_PERSON = 0.1
FOOD_PER_SOLDIER = 0.2

#: the order buildings fall in a siege; the castle star needs everything before it destroyed
DESTRUCTION_ORDER = (
    "wall", "tower", "barracks", "archery", "stable", "siege", "smithy", "hospital", "castle",
    "warehouse", "market", "farm", "lumber", "stone_mine", "iron_mine",
)
HP_PER_LEVEL = {"castle": 600, "wall": 800, "tower": 500}
DEFAULT_HP_PER_LEVEL = 300
#: the largest share of a stock a raid may take
LOOT_CAP = {"gold": 0.15, "food": 0.20, "wood": 0.10, "stone": 0.10, "iron": 0.10}


def loot_factor(ratio: float) -> float:
    """What a raid is worth, by how much stronger the raider's city is than the target (ratio = raider / target)."""
    if ratio >= 3:
        return 0.1
    if ratio >= 2:
        return 0.3
    if ratio >= 1.5:
        return 0.6
    if ratio <= 0.4:
        return 1.6
    if ratio <= 0.7:
        return 1.3
    return 1.0


def get_building(building_id: str) -> Building:
    return _BUILDING[building_id]


def build_cost(building: Building, current_level: int) -> dict[str, int]:
    """The price of going from ``current_level`` to the next one."""
    factor = building.growth ** current_level
    g, w, s, i = building.cost
    return {"gold": round(g * factor), "wood": round(w * factor), "stone": round(s * factor), "iron": round(i * factor)}


#: crystals buy time: one crystal rushes this many seconds of construction or training
RUSH_SECONDS_PER_CRYSTAL = 600


def build_seconds(building: Building, current_level: int) -> int:
    """How long the next level takes to raise (the castle takes twice as long)."""
    seconds = 120 * (current_level + 1) ** 1.6 * (2 if building.id == "castle" else 1)
    return round(seconds)


def rush_crystals(seconds_left: int) -> int:
    return max(1, -(-max(0, seconds_left) // RUSH_SECONDS_PER_CRYSTAL))


def slots_for(castle_level: int) -> int:
    return 5 + (castle_level - 1)


def storage_floor(castle: int) -> int:
    """The least a storehouse can hold: always enough for the most expensive upgrade this castle level allows.

    Without it a castle of level 6 (47 thousand gold for the next level) and a small storehouse made the upgrade
    impossible for good, since production stops at the storage limit."""
    best = 0
    for b in BUILDINGS:
        if b.id == "castle":
            if castle >= MAX_CASTLE:
                continue
            level = castle
        else:
            level = max(0, min(b.max_level, castle) - 1)
        best = max(best, max(build_cost(b, level).values()))
    return -(-best * 5 // 4)


def storage_cap(warehouse: int, castle: int) -> int:
    return max(5_000 + 4_000 * warehouse + 1_000 * castle, storage_floor(castle))


def population_cap(castle: int) -> int:
    return 400 + 250 * castle


def army_capacity(levels: dict[str, int]) -> int:
    return (
        100 + 120 * levels.get("barracks", 0) + 100 * levels.get("archery", 0)
        + 100 * levels.get("stable", 0) + 80 * levels.get("siege", 0)
    )


# --- troops -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Troop:
    id: str
    emoji: str
    name: str
    about: str
    atk: int
    defense: int
    hp: int
    speed: int
    #: space taken in the army
    cap: int
    cost: tuple[int, int, int, int]  # gold, food, wood, iron
    train_seconds: int
    upkeep: float
    building: str
    needs: int
    #: damage against buildings (siege machines are made for it)
    struct: int
    siege: bool = False
    cavalry: bool = False


TROOPS: tuple[Troop, ...] = (
    Troop("sword", "🗡️", "شمشیرزن", "نیروی پیاده‌ی متعادل", 12, 10, 100, 5, 1, (60, 20, 0, 10), 30, 0.2, "barracks", 1, 6),
    Troop("spear", "🔱", "نیزه‌دار", "سواره‌نظام را از اسب می‌اندازد", 10, 14, 90, 5, 1, (50, 20, 20, 0), 30, 0.2, "barracks", 2, 5),
    Troop("archer", "🏹", "کماندار", "حمله از فاصله‌ی دور", 16, 5, 60, 4, 1, (70, 15, 30, 0), 40, 0.2, "archery", 1, 7),
    Troop("cavalry", "🐎", "سواره‌نظام سبک", "حمله‌ی سریع و برق‌آسا", 18, 8, 90, 10, 1, (110, 30, 0, 20), 45, 0.3, "stable", 1, 8, cavalry=True),
    Troop("knight", "🛡️", "شوالیه", "سواره‌ی سنگین و زره‌پوش", 30, 25, 220, 8, 2, (260, 60, 0, 80), 90, 0.4, "stable", 3, 14, cavalry=True),
    Troop("ram", "🐏", "دژکوب", "دروازه و دیوار را می‌شکند", 2, 5, 300, 3, 4, (200, 0, 150, 60), 120, 0.3, "siege", 1, 45, siege=True),
    Troop("catapult", "☄️", "منجنیق", "دیوار و ساختمان را خرد می‌کند", 6, 3, 120, 2, 20, (500, 0, 200, 150), 180, 0.5, "siege", 3, 90, siege=True),
    Troop("tower_siege", "🪜", "برج محاصره", "نیروها را از دیوار عبور می‌دهد", 0, 10, 400, 2, 10, (350, 0, 300, 40), 150, 0.4, "siege", 4, 6, siege=True),
)
_TROOP = {t.id: t for t in TROOPS}


#: every soldier has a gift of his own: (name, what it does in battle) - the numbers match engine/siege.py
SPECIALS: dict[str, tuple[str, str]] = {
    "sword": ("سپرداران پیشرو", "صفوف اول لشکر؛ هر چه شمشیرزن بیشتر باشد، آسیب تله‌ها به لشکر تا ۳۰٪ کمتر می‌شود."),
    "spear": ("دیوار نیزه", "سواره‌نظام و شوالیه‌ی دشمن را از اسب می‌اندازد؛ مهاجمِ سواره‌نظام تا ۶۰٪ بیشتر آسیب می‌بیند."),
    "archer": ("باران تیر", "در نخستین دور نبرد، قدرت حمله‌شان ۲۵٪ بیشتر است."),
    "cavalry": ("یورش برق‌آسا", "در نخستین دور نبرد با یورش ناگهانی ۳۰٪ قدرت حمله‌ی بیشتری دارد."),
    "knight": ("زره‌ی سنگین", "جان مؤثرش یک‌سوم بیشتر است؛ سخت‌تر از پا درمی‌آید."),
    "ram": ("دروازه‌شکن", "دیوار شهر تقریباً جلودارش نیست و ساختمان‌ها را به‌سرعت می‌شکند."),
    "catapult": ("سنگ‌باران", "ویرانی گسترده؛ ۱۵٪ آسیب بیشتر به ساختمان‌ها می‌زند."),
    "tower_siege": ("پل دیوار", "اگر یکی از آن‌ها زنده بماند، تأثیر دیوار شهر روی همه‌ی لشکر ۴۰٪ کمتر می‌شود."),
}


def get_special(troop_id: str) -> tuple[str, str]:
    return SPECIALS[troop_id]


#: every battle costs blood: this share of each kind of attacker never comes home
MIN_ATTACKER_LOSS = 0.08


def get_troop(troop_id: str) -> Troop:
    return _TROOP[troop_id]


def unit_power(troop: Troop) -> int:
    return round(troop.atk * 2 + troop.defense + troop.hp / 10 + troop.struct / 4)


# --- traps ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Trap:
    id: str
    emoji: str
    name: str
    damage: int
    cost: tuple[int, int, int, int]  # gold, wood, stone, iron per charge


TRAPS: tuple[Trap, ...] = (
    Trap("oil", "🛢️", "روغن داغ", 60, (80, 40, 0, 0)),
    Trap("spike", "🪤", "تله‌ی نیزه‌ای", 45, (60, 60, 0, 10)),
    Trap("rockfall", "🪨", "ریزش سنگ", 80, (90, 0, 80, 0)),
    Trap("fire", "🔥", "تله‌ی آتشین", 120, (150, 30, 0, 40)),
    Trap("pit", "🕳️", "چاله‌ی دفاعی", 35, (40, 0, 30, 0)),
)
_TRAP = {t.id: t for t in TRAPS}
TRAP_BATCH = 5
TRAP_FIRES_PER_BATTLE = 8


def get_trap(trap_id: str) -> Trap:
    return _TRAP[trap_id]


def trap_limit(castle: int) -> int:
    return 10 * castle


# --- leagues ----------------------------------------------------------------------------------
LEAGUES: tuple[tuple[int, str, str], ...] = (
    (0, "🪵", "چوبی"), (500, "🥉", "برنزی"), (1000, "🥈", "نقره‌ای"), (1500, "🥇", "طلایی"),
    (2000, "💠", "پلاتینیوم"), (2500, "💎", "الماس"), (3500, "🏆", "قهرمانان"), (5000, "🐉", "اساطیری"),
)


def league_of(trophies: int) -> tuple[str, str]:
    emoji, name = LEAGUES[0][1], LEAGUES[0][2]
    for floor, e, n in LEAGUES:
        if trophies >= floor:
            emoji, name = e, n
    return emoji, name


def shield_for(destruction: float) -> int:
    """Seconds of protection a city gets after being raided."""
    if destruction >= 1.0:
        return 14 * 3600
    if destruction >= 0.60:
        return 10 * 3600
    if destruction >= 0.30:
        return 6 * 3600
    return 0
