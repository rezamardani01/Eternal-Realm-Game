"""The living world (جهان زنده): regions whose darkness creeps on by itself, and world events everybody fights together."""

from __future__ import annotations

from dataclasses import dataclass

#: darkness grows by itself; heroes push it back by winning fights in the region
DARKNESS_PER_HOUR = 0.8
START_DARKNESS = 15.0
ENERGY = 8
EVENT_HOURS = 18
#: a new event begins this long after the last one ended
GAP_HOURS = 4
EVENT_POINTS = 1200


@dataclass(frozen=True)
class Region:
    id: str
    emoji: str
    name: str
    blurb: str


REGIONS: tuple[Region, ...] = (
    Region("black_forest", "🌲", "جنگل سیاه", "درختانی که شب‌ها زمزمه می‌کنند"),
    Region("north_peaks", "🏔️", "کوه‌های شمالی", "برف، باد و غارهای فراموش‌شده"),
    Region("sunset_port", "⚓", "بندر غروب", "کشتی‌ها، تاجران و میدان‌های تمرین"),
    Region("red_desert", "🏜️", "صحرای سرخ", "ماسه‌های داغ و شهرهای سوخته"),
    Region("mist_valley", "🌫️", "دره‌ی مه", "راه‌هایی که در مه گم می‌شوند"),
    Region("golden_plain", "🌾", "دشت طلایی", "کشتزارها و لانه‌های دور"),
    Region("mirage_sea", "🐪", "دریای سراب", "ماسه‌های بی‌پایان و شهرهای زیر شن"),
    Region("drowned_coast", "🌊", "ساحل غرق‌شده", "کشتی‌های شکسته و آوازهای زیر آب"),
    Region("ghost_grove", "🌳", "بیشه‌ی ارواح", "درختانی که خاطره دارند"),
    Region("sky_isles", "⚡", "جزایر آسمانی", "ابرهای سنگی و طوفان‌های همیشگی"),
)
_REGION = {r.id: r for r in REGIONS}
#: where each kind of solo content happens
STORY_REGION = {1: "black_forest", 2: "red_desert", 3: "north_peaks", 4: "mist_valley", 5: "mirage_sea", 6: "drowned_coast", 7: "ghost_grove", 8: "sky_isles"}
DUNGEON_REGION = {
    "crypt": "black_forest", "inferno": "red_desert", "prison": "north_peaks", "temple": "mist_valley", "lair": "golden_plain",
    "swamp": "ghost_grove", "clockwork": "sunset_port", "library": "mist_valley", "volcano": "red_desert", "abyss": "sky_isles",
    "colosseum": "mirage_sea", "crystal": "north_peaks",
}
ARENA_REGION = "sunset_port"


def get_region(region_id: str) -> Region:
    return _REGION[region_id]


def status_of(darkness: float) -> str:
    if darkness < 30:
        return "عادی"
    if darkness < 60:
        return "جنگی"
    if darkness < 85:
        return "نفرین‌شده"
    return "متروکه"


def effect_of(darkness: float) -> tuple[float, float]:
    """Dangerous regions fight harder and pay more: (enemy strength, reward) multipliers."""
    share = max(0.0, min(100.0, darkness)) / 100
    return 1 + 0.15 * share, 1 + 0.30 * share


@dataclass(frozen=True)
class EventKind:
    id: str
    emoji: str
    title: str
    text: str
    region: str
    foe: str


EVENT_KINDS: tuple[EventKind, ...] = (
    EventKind("blood_dragon", "🐉", "ظهور اژدهای خونین",
              "اژدهای باستانی پس از هزار سال از خواب بیدار شده و به سرزمین‌های شمالی حمله کرده است. فرمانروایان می‌توانند برای مقابله با این موجود افسانه‌ای متحد شوند.",
              "north_peaks", "dragon_brood"),
    EventKind("undead_army", "💀", "حمله‌ی ارتش مردگان",
              "گورها در جنگل سیاه شکافته‌اند و ارتشی از مردگان به سوی روستاها می‌رود. هر ضربه‌ی شما یک روستا را نجات می‌دهد.",
              "black_forest", "crypt_lord"),
    EventKind("curse_spread", "🕸️", "شیوع نفرین",
              "نفرینی کهن در دره‌ی مه پخش می‌شود و مردم یکی‌یکی به خواب سایه‌ها می‌روند. جادوگری که این نفرین را رها کرده باید متوقف شود.",
              "mist_valley", "forbidden_mage"),
    EventKind("legendary_mine", "⛏️", "معدن افسانه‌ای",
              "در صحرای سرخ معدنی از سنگ‌های درخشان پیدا شده، اما هیولای گداخته‌ای از آن نگهبانی می‌کند. هر که بیشتر کمک کند، سهم بیشتری می‌برد.",
              "red_desert", "lava_beast"),
    EventKind("dark_riot", "😈", "شورش موجودات تاریک",
              "موجودات تاریک در دشت طلایی سر به شورش برداشته‌اند و کشتزارها را می‌سوزانند. باید پیش از شب ریشه‌ی شورش را کند.",
              "golden_plain", "fire_imp"),
    EventKind("dimension_gate", "🌀", "دروازه‌ای از جهانی ناشناخته",
              "در بندر غروب دروازه‌ای از نور باز شده و سایه‌هایی از آن بیرون می‌آیند. بسته شدنش به همت همه‌ی فرمانروایان بستگی دارد.",
              "sunset_port", "mirror_shade"),
    EventKind("sand_curse", "🏜️", "بیداری فرعون",
              "فرعونی که هزاره‌ها خوابیده بود از هرم بیرون آمده و ماسه‌ها را به لشکر تبدیل می‌کند. فرمانروایان باید پیش از رسیدنش به شهرها او را متوقف کنند.",
              "mirage_sea", "mummy"),
    EventKind("sea_wrath", "🌊", "خشم لویاتان",
              "امواجی غول‌آسا به ساحل غرق‌شده یورش آورده‌اند و کشتی‌ها یکی‌یکی به قعر می‌روند. باید مهار اقیانوس را به دست گرفت.",
              "drowned_coast", "kraken_spawn"),
    EventKind("grove_awaken", "🌳", "بیداری بیشه",
              "درختان بیشه‌ی ارواح راه افتاده‌اند و هر که را ببینند در ریشه‌هایشان می‌بندند. باید ریشه‌ی خشم را پیدا کرد.",
              "ghost_grove", "treant"),
    EventKind("sky_fall", "⚡", "سقوط جزیره‌ی آسمانی",
              "جزیره‌ای از ابر و سنگ از آسمان می‌افتد و موجوداتش به زمین می‌ریزند. هر ضربه‌ی شما سرعت سقوط را کم می‌کند.",
              "sky_isles", "storm_hawk"),
)
_KIND = {k.id: k for k in EVENT_KINDS}


def get_kind(kind_id: str) -> EventKind:
    return _KIND[kind_id]
