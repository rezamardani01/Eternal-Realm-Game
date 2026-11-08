"""Daily activities (fishing, mining, ...) described purely as data.

Adding an activity means adding an entry here: the engine, the service and the group commands
are generic. Texts speak to the player as «فرمانده» in simple, story-like Persian.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Drop:
    item_id: str
    qty: tuple[int, int] = (1, 1)
    chance: float = 1.0


@dataclass(frozen=True)
class Outcome:
    weight: float
    text: str
    gold: tuple[int, int] = (0, 0)
    xp: tuple[int, int] = (0, 0)
    drops: tuple[Drop, ...] = ()
    crystal: int = 0
    #: rare outcomes become likelier with the player's luck
    rare: bool = False
    min_level: int = 1


@dataclass(frozen=True)
class Activity:
    id: str
    emoji: str
    title: str
    aliases: tuple[str, ...]
    intro: str
    energy: int
    cooldown: int
    outcomes: tuple[Outcome, ...]


FISHING = Activity(
    "fishing", "🎣", "ماهیگیری",
    ("ماهیگیری", "ماهی", "برو ماهی بگیر", "fish"),
    "🎣 فرمانده {name} کنار دریاچه‌ی نقره‌ای ایستاد و قلاب را به آب انداخت...\n"
    "🌊 آب آرام بود و فقط صدای باد می‌آمد...",
    energy=5, cooldown=20,
    outcomes=(
        Outcome(15, "👢 فقط یک چکمه‌ی کهنه از آب بیرون آمد! لابد کسی سال‌ها پیش گمش کرده. دفعه‌ی بعد بخت با شماست!",
                gold=(0, 4), xp=(2, 4)),
        Outcome(38, "🐟 یک ماهی کوچک به قلاب افتاد. شروع خوبی است، فرمانده!", xp=(7, 10),
                drops=(Drop("small_fish", (1, 2)),)),
        Outcome(24, "🐠 قزل‌آلایی درشت و پرتلاش صید کردید! شام امشب حاضر است.", xp=(11, 15),
                drops=(Drop("trout"),)),
        Outcome(
            12, "🕸️ تور را بالا کشیدید و پر از ماهی بود! ماهیگیران ساحل هم برایتان هورا کشیدند.", xp=(13, 19),
            drops=(Drop("small_fish", (3, 5)), Drop("trout", (1, 2), 0.6)),
        ),
        Outcome(
            5, "✨ ای بخت بلند! ماهی طلایی افسانه‌ها به دام افتاد و زیر نور خورشید درخشید!",
            gold=(30, 80), xp=(28, 38), rare=True, drops=(Drop("golden_fish"),),
        ),
        Outcome(
            2, "🍾 موج‌ها یک بطری قدیمی را به ساحل آوردند؛ درونش نقشه‌ی یک گنج پنهان بود!",
            gold=(120, 260), xp=(20, 30), rare=True, drops=(Drop("crystal_shard", (1, 1), 0.5),),
        ),
        Outcome(
            0.3, "🦪 صدفی از ته دریا بالا آمد و درونش مرواریدی جادویی می‌درخشید: یک کریستال ناب!",
            xp=(30, 40), crystal=1, rare=True,
        ),
    ),
)

MINING = Activity(
    "mining", "⛏️", "معدن‌کاری",
    ("معدن", "معدن‌کاری", "برو معدن", "mine"),
    "⛏️ فرمانده {name} کلنگ را برداشت و به دل معدن تاریک رفت...\n"
    "🕯️ صدای ضربه‌ها در تونل‌های سنگی پیچید...",
    energy=8, cooldown=30,
    outcomes=(
        Outcome(14, "💨 فقط خاک و غبار بود. اما معدن‌چی‌های واقعی هیچ‌وقت تسلیم نمی‌شوند!", xp=(3, 5)),
        Outcome(36, "🪨 چند تکه سنگ محکم از دیوار بیرون کشیدید.", xp=(8, 12),
                drops=(Drop("stone", (2, 4)),)),
        Outcome(
            28, "⛓️ رگه‌ی آهن زیر نور فانوس برق زد!", xp=(12, 17), gold=(2, 8),
            drops=(Drop("iron_ore", (1, 3)),),
        ),
        Outcome(
            10, "🥇 رگه‌ی طلا در تاریکی درخشید! چشم همه‌ی معدن‌چیان گرد شد.", xp=(18, 26),
            gold=(10, 30), min_level=3, drops=(Drop("gold_ore", (1, 2)),),
        ),
        Outcome(
            4, "💠 پاره‌کریستالی درخشان از دیوار بیرون آوردید؛ جادو درونش می‌تپید!", xp=(28, 38),
            rare=True, min_level=5, drops=(Drop("crystal_shard"),),
        ),
        Outcome(
            0.4, "💎 قلب یک کریستال خالص در دیوار پنهان بود: یک کریستال ناب!", xp=(40, 55),
            crystal=1, rare=True, min_level=8,
        ),
    ),
)

HERBS = Activity(
    "herb", "🌿", "گیاه‌چینی",
    ("گیاه", "گیاه‌چینی", "برو گیاه بچین", "herb"),
    "🌿 فرمانده {name} وارد جنگل سبز شد و میان برگ‌ها دنبال گیاهان جادویی گشت...",
    energy=4, cooldown=20,
    outcomes=(
        Outcome(20, "🍂 فقط چند برگ خشک پیدا کردید. جنگل رازهایش را آسان نمی‌دهد!", xp=(2, 4)),
        Outcome(52, "🌿 چند شاخه گیاه شفابخش چیدید؛ بوی خوبی دارند.", xp=(6, 9),
                drops=(Drop("herb", (1, 3)),)),
        Outcome(
            18, "🍀 گیاه ماه‌تاب زیر سایه‌ی درختی کهن می‌درخشید!", xp=(13, 18), min_level=3,
            drops=(Drop("moon_herb"),),
        ),
        Outcome(
            6, "🌸 باغچه‌ای پنهان پر از گیاهان کمیاب پیدا کردید! جنگل امروز مهربان است.", xp=(18, 25),
            rare=True, drops=(Drop("herb", (3, 5)), Drop("moon_herb", (1, 2), 0.5)),
        ),
    ),
)

SEARCH = Activity(
    "search", "🔍", "جستجو",
    ("جستجو", "بگرد", "جست‌وجو", "search"),
    "🔍 فرمانده {name} میان ویرانه‌ها و صخره‌ها را با دقت جستجو کرد...",
    energy=6, cooldown=25,
    outcomes=(
        Outcome(22, "🕸️ جز تار عنکبوت چیزی پیدا نشد. دفعه‌ی بعد جای دیگری را بگردید!", xp=(3, 5)),
        Outcome(30, "👛 کیسه‌ی سکه‌ای گمشده پیدا کردید؛ صاحبش هیچ‌وقت سراغش نیامد!", gold=(12, 40), xp=(7, 11)),
        Outcome(14, "📜 طومار کهنه‌ای لای خرابه‌ها بود؛ خط‌هایش از قرن‌ها پیش مانده.", xp=(10, 14),
                drops=(Drop("old_scroll"),)),
        Outcome(14, "⚡ معجون انرژی‌ای کنار صخره افتاده بود؛ انگار کسی برای شما جا گذاشته!", xp=(9, 13),
                drops=(Drop("energy_potion"),)),
        Outcome(
            8, "📦 صندوقچه‌ای نیمه‌مدفون زیر خاک پیدا کردید! چه رازی در آن است؟", gold=(30, 90),
            xp=(16, 22), rare=True, drops=(Drop("wooden_chest"),),
        ),
        Outcome(
            2, "🗝️ گنجینه‌ی پنهان یک جادوگر قدیمی را کشف کردید! نام شما در افسانه‌ها خواهد ماند.",
            gold=(150, 400), xp=(26, 36), rare=True, min_level=5,
            drops=(Drop("crystal_shard", (1, 2), 0.7),),
        ),
    ),
)

ACTIVITIES: dict[str, Activity] = {a.id: a for a in (FISHING, MINING, HERBS, SEARCH)}
