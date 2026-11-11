"""Realm-wide events: one announcement reaches every group, anybody can join from the private chat, and when the
countdown ends the game plays everything out by itself and sends each hero the result.
"""

from __future__ import annotations

from dataclasses import dataclass

#: minutes of waiting between the announcement and the start (the owner may choose another)
LOBBY_MINUTES = 5
MIN_PLAYERS = 2
#: the longest lobby the owner may ask for
MAX_LOBBY_MINUTES = 120
#: when the owner switches the automatic mode on: hours between two events, and the hours of the day (Tehran) they may start
AUTO_GAP_HOURS = 10
AUTO_HOURS = (10, 22)


@dataclass(frozen=True)
class GlobalKind:
    id: str
    emoji: str
    title: str
    #: the words the owner may write after «رویداد سراسری»
    words: tuple[str, ...]
    #: what is announced
    blurb: str
    #: raid (everybody fights a copy of one monster, together they must break it), cup (fights ranked against each
    #: other) or lottery (a draw among everybody who joined)
    mode: str
    foe: str = ""
    mult: float = 1.0


KINDS: tuple[GlobalKind, ...] = (
    GlobalKind(
        "darkness", "🌑", "یورش لشکر تاریکی", ("لشکر", "تاریکی", "یورش"),
        "فرمانروای تاریکی با لشکرش از دروازه‌های شمالی می‌آید! اگر همه‌ی فرمانروایان قلمرو متحد شوند، می‌شود او را عقب راند.",
        "raid", "lord_of_darkness", 1.0,
    ),
    GlobalKind(
        "dragon", "🐉", "طوفان اژدهای سرخ", ("اژدها", "طوفان"),
        "آسمان قلمرو سرخ شده؛ اژدهای سرخ از کوه‌های آتش برخاسته و شهرها را می‌سوزاند. فقط اتحاد همه می‌تواند او را زمین بزند.",
        "raid", "boss_red_dragon", 1.0,
    ),
    GlobalKind(
        "undead", "💀", "خیزش پادشاه مردگان", ("مردگان", "پادشاه"),
        "گورستان‌ها شکافته شده و پادشاه مردگان با سپاه استخوانی‌اش بر قلمرو می‌تازد.",
        "raid", "boss_undead_king", 1.0,
    ),
    GlobalKind(
        "titan", "🗿", "بیداری تایتان باستانی", ("تایتان", "غول"),
        "زمین می‌لرزد؛ تایتان باستانی از خواب هزارساله بیدار شده است. هر قدمش یک روستا را نابود می‌کند.",
        "raid", "boss_titan", 1.0,
    ),
    GlobalKind(
        "cup", "🏆", "جام قهرمانان قلمرو", ("جام", "تورنمنت"),
        "شاه، همه‌ی قهرمانان را به میدان بزرگ فراخوانده! هر کس با یک حریف افسانه‌ای می‌جنگد و برترین‌ها جام و جایزه می‌برند.",
        "cup", "bot_knight", 1.1,
    ),
    GlobalKind(
        "treasure", "💰", "قرعه‌کشی گنج سلطنتی", ("گنج", "قرعه"),
        "خزانه‌دار شاه در خزانه گنجی یافته و می‌خواهد آن را میان قهرمانان قرعه بزند. فقط ثبت‌نام کنید!",
        "lottery",
    ),
)
_BY_ID = {k.id: k for k in KINDS}


def get_kind(kind_id: str) -> GlobalKind:
    return _BY_ID[kind_id]


def find_kind(word: str) -> GlobalKind | None:
    word = word.strip()
    return next((k for k in KINDS if word == k.id or word in k.words), None)


#: how the story ends, by kind
VICTORY: dict[str, str] = {
    "darkness": "پرچم‌های لشکر تاریکی سوخت و فرمانروایش به ژرفای شب گریخت. دروازه‌های شمالی دوباره به دست قهرمانان افتاد.",
    "dragon": "اژدهای سرخ با نعره‌ای لرزان از آسمان فرود آمد و آتشش خاموش شد. شهرها نفس راحتی کشیدند.",
    "undead": "استخوان‌های سپاه مردگان فرو ریخت و پادشاهشان به گور بازگشت. گورستان‌ها دوباره آرام شد.",
    "titan": "تایتان باستانی زانو زد و دوباره به خواب هزارساله رفت. زمین از لرزه ایستاد.",
}
DEFEAT: dict[str, str] = {
    "darkness": "لشکر تاریکی تا دروازه‌ها پیش آمد و سایه‌اش بر قلمرو افتاد... اما قهرمانان ایستادگی کردند و غول را زخمی کردند.",
    "dragon": "اژدهای سرخ بخشی از شهرها را سوزاند و گریخت. قهرمانان زخم‌ها را بستند و برای دفعه‌ی بعد آماده می‌شوند.",
    "undead": "پادشاه مردگان عقب نشست، اما نه شکست‌خورده. قلمرو هنوز نفس می‌کشد و قهرمانانش آماده‌ترند.",
    "titan": "تایتان با چند قدم خانه‌ها را خراب کرد و دور شد. قهرمانان تا آخرین دم جنگیدند.",
}
CUP_STORY = "میدان بزرگ پر از فریاد بود؛ شمشیرها بالا رفت و جام به شایسته‌ترین‌ها رسید."
LOTTERY_STORY = "خزانه‌دار شاه کیسه‌ی قرعه را تکان داد و اسم‌ها از میان انبوه بیرون افتاد."


# --- rewards ----------------------------------------------------------------------------------------------------------
def base_gold(level: int) -> int:
    return 600 + 45 * level


def base_xp(level: int) -> int:
    return 450 + 35 * level


#: a raid is won when the heroes together take off at least this share of one monster per hero
RAID_WIN_SHARE = 0.5
#: extra prizes for the best fighters: (crystals, chest)
PODIUM: tuple[tuple[int, str], ...] = ((10, "royal_chest"), (6, "magic_chest"), (4, "magic_chest"))
CUP_PRIZES: tuple[int, ...] = (15, 10, 8, 6, 5, 4, 3, 3, 2, 2)
#: when a raid is won everybody gets this on top
WIN_CRYSTALS, WIN_CHEST = 3, "magic_chest"
LOTTERY_JACKPOT = (20_000, 20, "royal_chest")
LOTTERY_MEDIUM = (4, 3_000, 5, "magic_chest")  # winners, gold, crystals, chest
LOTTERY_CONSOLATION = (600, 1, "wooden_chest")
