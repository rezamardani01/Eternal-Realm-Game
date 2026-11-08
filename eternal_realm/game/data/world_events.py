"""Content of the world events: hidden chests (with clues), monster invasions and meteor falls."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    #: the riddle that points at this place
    clue: str


PLACES: tuple[Place, ...] = (
    Place("cave", "🕳️ غار خفاش‌ها", "جایی که تاریکی زمزمه می‌کند و از سقفش قطره‌های سرد می‌چکد."),
    Place("tower", "🗼 برج شکسته", "جایی که بادها از میان سنگ‌های ترک‌خورده‌اش آواز می‌خوانند و بالای همه‌ی درخت‌هاست."),
    Place("spring", "⛲ چشمه‌ی ماه", "جایی که آب در شب نقره‌ای می‌شود و ماه در آن خودش را نگاه می‌کند."),
    Place("ruins", "🏛️ ویرانه‌ی باستانی", "جایی که ستون‌های شکسته‌ی پادشاهی فراموش‌شده هنوز ایستاده‌اند."),
    Place("forest", "🌲 جنگل نجواها", "جایی که درخت‌ها نام مسافران را زیر لب تکرار می‌کنند."),
    Place("cliff", "🏔️ صخره‌ی باد", "جایی که زمین تمام می‌شود و عقاب‌ها لانه دارند."),
)
_PLACE_BY_ID = {p.id: p for p in PLACES}


def place(place_id: str) -> Place:
    return _PLACE_BY_ID[place_id]


#: (emoji + name, short cry shown in the announcement)
ARMIES: tuple[tuple[str, str], ...] = (
    ("🧟 ارتش مردگان", "از گورستان‌ها برخاسته و به سوی قلمرو می‌آید!"),
    ("🐺 گله‌ی گرگ‌های سایه", "از دل جنگلِ تاریک بیرون ریخته و روستاها را می‌درد!"),
    ("👹 لشکر اورک‌ها", "طبل جنگ می‌کوبد و دروازه‌ها را هدف گرفته است!"),
    ("🕷️ هجوم عنکبوت‌های غول‌پیکر", "تار می‌تند و راه کاروان‌ها را می‌بندد!"),
    ("🐉 بچه‌اژدهاهای آتش‌افروز", "آسمان را قرمز کرده و مزارع را می‌سوزانند!"),
)

REGIONS: tuple[str, ...] = ("🏔️ قله‌ی بادها", "🌲 جنگل نجواها", "🏜️ دشت سوخته", "🌊 ساحل مه‌آلود", "⛏️ معدن فراموش‌شده")

#: (item id, weight) a fallen meteor may hold
METEOR_LOOT: tuple[tuple[str, int], ...] = (
    ("crystal_shard", 45), ("gold_ore", 22), ("ancient_coin", 18), ("dragon_scale", 10), ("moon_herb", 5),
)
METEOR_PIECES = 12
METEOR_PER_PLAYER = 3
