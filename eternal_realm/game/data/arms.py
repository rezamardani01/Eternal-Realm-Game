"""Hero equipment ("تجهیزات قهرمان"): the war gear a hero carries into a fight, four pieces at a time.

This catalogue is separate from ``items.py`` on purpose: those items are the economy (materials, potions, chests and the
older gear); these are the pieces that change *how a fight is played*. Everything here is data. To add a piece, add one
``_arm(...)`` line; the shop, the equip screens and the fight engine read it from here.

Balance rules (so no piece wins a fight by itself, and nothing is bought into an unfair lead):

* the stat bonuses stay in a narrow band per rarity (see ``TIERS``), traits are small, and ``CAPS`` limits what four
  pieces can stack for every trait kind;
* war gear is bought only with real money from the realm treasury (never with coins), so nothing here can be farmed; free
  players still find the cheap pieces (common and uncommon) as lucky drops of hunts, trips, chests and bosses;
* a piece needs a hero level, some need a class; in fights between heroes the stronger side's lead is capped anyway.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.text import fa, normalize
from .stats import Stats

MAX_EQUIPPED = 4

CATEGORIES: dict[str, tuple[str, str]] = {
    "weapon": ("⚔️", "شمشیر و سلاح‌های تهاجمی"),
    "armor": ("🛡️", "زره و تجهیزات دفاعی"),
    "ring": ("💍", "انگشتر و جواهرات جادویی"),
    "charm": ("🧿", "طلسم و آیتم‌های ویژه"),
    "boost": ("⚡", "تجهیزات سرعت و قدرت"),
    "heal": ("🧪", "آیتم‌های بازیابی سلامتی"),
}

#: the button text of each category (two words)
CATEGORY_SHORT: dict[str, str] = {
    "weapon": "شمشیر و سلاح", "armor": "زره و دفاع", "ring": "انگشتر و جواهر", "charm": "طلسم و جادو",
    "boost": "سرعت و قدرت", "heal": "بازیابی سلامتی",
}

RARITIES: dict[int, tuple[str, str]] = {
    1: ("⚪", "معمولی"),
    2: ("🟢", "غیرمعمول"),
    3: ("🔵", "کمیاب"),
    4: ("🟣", "حماسی"),
    5: ("🟠", "افسانه‌ای"),
    6: ("🔴", "اسطوره‌ای"),
}

#: rarity -> (coins, level) a typical piece of that rarity costs; a piece strays only a little from these
TIERS = {1: (450, 1), 2: (1_800, 4), 3: (5_200, 8), 4: (12_500, 14), 5: (32_000, 22), 6: (95_000, 30)}
#: the real-money price in rial is the base ``price`` times this
RIAL_PER_COIN = 10
#: every price of the treasury was raised by this factor (see packs.py, where the packs are priced)
PRICE_RISE = 1.3
#: a wallet invoice never goes below this (the cheapest pieces cost this much in money)
MIN_RIAL = 20_000


@dataclass(frozen=True)
class Trait:
    """A special ability of a piece. k kind; v strength; c chance to trigger (1 = always); t turns."""

    k: str
    v: float = 0.0
    c: float = 1.0
    t: int = 0


#: kind -> the most four pieces can add up to (traits of the same kind are summed, then limited)
CAPS: dict[str, float] = {
    "crit_chance": 0.35, "crit_mult": 1.5, "dmg_cut": 0.25, "evade": 0.20, "thorns": 0.35, "regen": 0.08,
    "armor_pen": 0.40, "skill_power": 0.30, "defend_heal": 0.20, "leech_pct": 0.25, "leech_flat": 30,
    "leech_foe_hp": 0.10, "extra_hit": 0.40, "cd_cut": 0.60, "execute": 0.60, "phys_power": 0.25, "magic_power": 0.25, "crit_resist": 0.60,
    "low_hp_def": 0.50, "backstab": 0.50, "resist_all": 0.60,
}

#: rough power one unit of a trait adds, so that the "who is stronger" comparison between heroes counts the traits too
RATING = {
    "crit_chance": 140, "crit_mult": 40, "dmg_cut": 260, "evade": 160, "thorns": 70, "regen": 700, "armor_pen": 80,
    "skill_power": 90, "defend_heal": 60, "leech_pct": 150, "leech_flat": 1.2, "leech_foe_hp": 150, "extra_hit": 120,
    "cd_cut": 50, "execute": 50, "inflict": 40, "undying": 90, "last_stand": 70, "shield_start": 12, "opening": 25,
    "phys_power": 200, "magic_power": 200, "crit_resist": 40, "low_hp_def": 60, "backstab": 70, "resist_all": 120,
}


def trait_text(t: Trait) -> str:
    chance = f" ({fa(round(t.c * 100))}٪ شانس)" if t.c < 1 else ""
    p = f"{fa(round(t.v * 100))}٪"
    inflict = {
        "poison": "مسموم", "burn": "سوخته", "bleed": "خونریز", "slow": "کُند", "stun": "گیج", "def_down": "زره‌شکسته",
        "freeze": "یخ‌زده", "shock": "شوک‌زده",
    }
    if t.k.startswith("inflict_"):
        status = inflict[t.k.split("_", 1)[1]]
        return f"🗡️ با هر ضربه‌ی موفق دشمن را «{status}» می‌کند{chance}" + (f" برای {fa(t.t)} نوبت" if t.t else "")
    return {
        "crit_chance": f"🎯 شانس ضربه‌ی کاری +{p}",
        "crit_mult": f"💥 ضربه‌ی کاری {fa(f'{1.5 + t.v:.1f}'.replace('.', '٫'))} برابر (به‌جای ۱٫۵)",
        "dmg_cut": f"🧱 {p} از هر آسیبی که می‌بینید کم می‌شود",
        "evade": f"💨 {p} شانس جاخالی بیشتر",
        "thorns": f"🌵 {p} از آسیبی که می‌بینید به مهاجم برمی‌گردد",
        "regen": f"💚 هر نوبت {p} از جان کل‌تان برمی‌گردد",
        "armor_pen": f"🗡️ {p} از دفاع دشمن نادیده گرفته می‌شود",
        "skill_power": f"✨ آسیب مهارت‌ها {p} بیشتر",
        "defend_heal": f"🛡️ هنگام دفاع {p} جان اضافه برمی‌گردد",
        "leech_pct": f"🩸 {p} از آسیب هر ضربه به جان شما برمی‌گردد",
        "leech_flat": f"🩸 با هر ضربه‌ی موفق {fa(round(t.v))} جان می‌گیرید",
        "leech_foe_hp": f"🍷 با هر ضربه‌ی موفق، {p} از جان فعلی دشمن را برای خود برمی‌دارید (حداکثر ۸٪ جان کل‌تان)",
        "extra_hit": f"⚡ {fa(round(t.c * 100))}٪ شانس ضربه‌ی دوباره (با ۶۰٪ قدرت) پس از هر حمله",
        "cd_cut": f"⏳ {fa(round(t.c * 100))}٪ شانس این‌که پس از هر مهارت، یک نوبتِ انتظار از همه‌ی مهارت‌ها کم شود",
        "execute": f"⚰️ اگر جان دشمن زیر ۳۰٪ باشد آسیب {p} بیشتر",
        "undying": f"🔥 یک‌بار در هر نبرد، به‌جای افتادن با {p} جان کل‌تان برمی‌خیزید",
        "last_stand": f"💖 یک‌بار در هر نبرد، وقتی جانتان زیر ۳۰٪ رفت {p} از جان کل‌تان برمی‌گردد",
        "shield_start": "🛡️ نبرد را با یک سپر شروع می‌کنید (ضربه‌ی اول نصف می‌شود)",
        "opening": f"💢 در {fa(t.t)} نوبت نخست، حمله‌ی شما {p} بیشتر است",
        "phys_power": f"💥 آسیب ضربه‌ها و مهارت‌های فیزیکی {p} بیشتر",
        "magic_power": f"🔮 آسیب مهارت‌های جادویی {p} بیشتر",
        "crit_resist": f"🧱 شانس ضربه‌ی کاری دشمن روی شما {p} کمتر",
        "low_hp_def": f"🩸 وقتی جانتان زیر ۴۰٪ است، دفاعتان {p} بیشتر می‌شود",
        "backstab": f"🗡️ به دشمنی که اثر بد (زهر، خونریزی، ...) دارد {p} آسیب بیشتر می‌زنید",
        "resist_all": f"🧿 {p} شانس مقاومت در برابر سوختگی، زهر، یخ‌زدگی و اثرهای بد",
    }[t.k]


@dataclass(frozen=True)
class Arm:
    id: str
    name: str
    emoji: str
    cat: str
    rarity: int
    price: int
    level_req: int
    stats: Stats
    traits: tuple[Trait, ...]
    blurb: str
    #: classes allowed to carry it (empty = any)
    classes: tuple[str, ...] = ()
    #: dropped only by bosses; never sold, neither for coins nor for money
    boss: bool = False

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"

    @property
    def rarity_label(self) -> str:
        icon, name = RARITIES[self.rarity]
        return f"{icon} {name}"

    @property
    def rial(self) -> int:
        return round(max(MIN_RIAL, self.price * RIAL_PER_COIN) * PRICE_RISE / 1000) * 1000

    def limits(self) -> list[str]:
        from .classes import CLASSES

        out = [f"🎓 حداقل سطح: {fa(self.level_req)}"] if self.level_req > 1 else []
        if self.classes:
            out.append("⚔️ ویژه‌ی " + "، ".join(CLASSES[c].name for c in self.classes))
        return out

    def card(self) -> str:
        """The whole piece, as a shop card."""
        lines = [f"{self.label}", f"{self.rarity_label} · {CATEGORIES[self.cat][1]}", "", f"«{self.blurb}»", ""]
        if self.boss:
            lines.insert(2, "🏆 غنیمت باس‌ها؛ در فروشگاه فروخته نمی‌شود")
        lines += self.stats.bonus_lines() or ["(بدون افزایش آمار)"]
        lines += [text for t in self.traits if (text := trait_text(t))]
        lines += ["", *(self.limits() or ["🎓 بدون محدودیت"])]
        return "\n".join(lines)


def _arm(id_, name, emoji, cat, rarity, blurb, stats=None, traits=(), *, price=None, level=None, classes=(), boss=False):  # noqa: ANN001, ANN202
    base_price, base_level = TIERS[rarity]
    return Arm(
        id_, name, emoji, cat, rarity, price or base_price, level or base_level, Stats(**(stats or {})), tuple(traits),
        blurb, tuple(classes), boss,
    )


T = Trait

_ARMS: tuple[Arm, ...] = (
    # --- swords and offensive weapons -------------------------------------------------------------------------------
    _arm("novice_dagger", "خنجر نوآموز", "🔪", "weapon", 1, "اولین تیغِ هر قهرمانی که هنوز اسمی ندارد.",
         {"atk": 3, "speed": 1}, price=380),
    _arm("iron_blade", "تیغ آهنین", "⚔️", "weapon", 2, "سنگین، ساده و قابل‌اعتماد؛ زره‌های نازک را می‌شکافد.",
         {"atk": 7}, [T("armor_pen", 0.08)]),
    _arm("twin_axe", "تبر دوسر", "🪓", "weapon", 2, "هر ضربه‌اش زخمی می‌گذارد که دیر خوب می‌شود.",
         {"atk": 8, "speed": -1}, [T("inflict_bleed", 0.12, 0.25, 3)], price=2_100),
    _arm("blood_sword", "شمشیر خونین", "🗡️", "weapon", 3, "تشنه‌ی خون؛ هر ضربه‌ی موفق، کمی جان به صاحبش می‌دهد.",
         {"atk": 10, "speed": 1}, [T("leech_flat", 8)]),
    _arm("hunt_longbow", "کمان شکاری", "🏹", "weapon", 3, "برای کسی که هیچ شکاری از دستش در نمی‌رود.",
         {"atk": 9, "luck": 3}, [T("crit_chance", 0.07)], classes=("archer", "rogue")),
    _arm("star_staff", "عصای ستارگان", "🪄", "weapon", 3, "نور ستاره‌ها در سنگ سرش جمع شده است.",
         {"magic": 12}, [T("skill_power", 0.10)], classes=("mage",)),
    _arm("venom_blade", "تیغ زهرآگین", "🐍", "weapon", 4, "تیغی که روی نیشِ مار آب‌دیده شده.",
         {"atk": 13, "speed": 3}, [T("inflict_poison", 0.15, 0.30, 3)]),
    _arm("quake_hammer", "پتک زلزله", "🔨", "weapon", 4, "زمین زیر ضربه‌اش می‌لرزد و دشمن از پا می‌افتد.",
         {"atk": 18, "speed": -3}, [T("armor_pen", 0.18), T("inflict_stun", 0, 0.12, 1)], classes=("warrior", "guardian")),
    _arm("dragon_slayer", "نابودگر اژدها", "🐉", "weapon", 5, "گفته‌اند با آن، اژدهایی را در یک شب از پا انداختند.",
         {"atk": 24}, [T("execute", 0.35), T("leech_pct", 0.08)]),
    # --- armour and defence -------------------------------------------------------------------------------------------
    _arm("leather_vest", "جلیقه‌ی چرمی", "🦺", "armor", 1, "سبک است و جای دو سه خراش را می‌گیرد.",
         {"defense": 3, "hp": 12}, price=420),
    _arm("light_mail", "زره‌ی زنجیری سبک", "⛓️", "armor", 2, "حلقه‌های ریز که آسیب را پخش می‌کنند.",
         {"defense": 6, "hp": 25}, [T("dmg_cut", 0.03)]),
    _arm("bulwark_shield", "سپر برجی", "🛡️", "armor", 3, "آن‌قدر بزرگ که تیرها را پشت سر خود گم می‌کند؛ خارهایش به مهاجم می‌خورد.",
         {"defense": 10, "hp": 30}, [T("thorns", 0.10)], classes=("warrior", "guardian")),
    _arm("smoke_robe", "ردای دودآلود", "👘", "armor", 3, "هر که ضربه بزند، فقط دود می‌بیند.",
         {"defense": 5, "hp": 20, "magic": 6}, [T("evade", 0.05)]),
    _arm("ghost_cloak", "شنل شبح", "🧥", "armor", 3, "سبک‌تر از سایه؛ دشمن بیشتر خطا می‌کند.",
         {"defense": 4, "hp": 15, "speed": 4}, [T("evade", 0.08)]),
    _arm("mountain_plate", "زره‌ی فولاد کوهستان", "🪖", "armor", 4, "از دل معدن بیرون آمده و از صخره سخت‌تر است.",
         {"defense": 15, "hp": 55}, [T("dmg_cut", 0.08)]),
    _arm("thorn_mail", "زره‌ی خارپشت", "🌵", "armor", 4, "هر که دست بزند، دستش زخم می‌شود.",
         {"defense": 12, "hp": 40}, [T("thorns", 0.22)]),
    _arm("iron_court", "بارگاه آهنین", "🏰", "armor", 5, "نبرد را با دیواری دور خودتان شروع می‌کنید.",
         {"defense": 20, "hp": 80}, [T("dmg_cut", 0.12), T("shield_start", 1.0)]),
    # --- rings and magic jewels ---------------------------------------------------------------------------------------
    _arm("turquoise_ring", "انگشتر فیروزه", "💍", "ring", 1, "نگینی آبی که شانس را کمی مهربان‌تر می‌کند.",
         {"luck": 3, "hp": 8}, price=400),
    _arm("emerald_ring", "انگشتر زمرد", "💚", "ring", 2, "سبزی‌اش زخم‌ها را کم‌کم می‌بندد.",
         {"luck": 4}, [T("regen", 0.02)]),
    _arm("lapis_ring", "انگشتر لاجورد", "🔷", "ring", 2, "تمرکز جادوگران را دوچندان می‌کند.",
         {"magic": 5}, [T("skill_power", 0.08)]),
    _arm("agate_ring", "انگشتر عقیق", "🟠", "ring", 3, "نگینش داغ است و ضربه‌ها را می‌سوزاند.",
         {"atk": 5, "speed": 2}, [T("inflict_burn", 0.18, 0.20, 3)]),
    _arm("ruby_ring", "انگشتر یاقوت", "♦️", "ring", 3, "هر ضربه‌ی موفق، رنگ سرخش را از جان دشمن می‌گیرد.",
         {"atk": 4}, [T("leech_foe_hp", 0.05), T("crit_chance", 0.10), T("crit_mult", 0.8)], price=5_800),
    _arm("diamond_ring", "حلقه‌ی الماس", "💎", "ring", 4, "سخت‌ترین سنگ جهان؛ هم می‌برد، هم دوام می‌آورد.",
         {"defense": 6, "luck": 5}, [T("crit_chance", 0.06), T("dmg_cut", 0.04)]),
    _arm("blood_price_ring", "حلقه‌ی خون‌بها", "🩸", "ring", 4, "قیمتش را از دشمنان می‌گیرد، نه از شما.",
         {"atk": 9}, [T("leech_pct", 0.10)]),
    _arm("royal_ring", "حلقه‌ی سلطنتی", "👑", "ring", 5, "نشانِ فرمانروایانِ قلمرو؛ مهارت‌ها زودتر برمی‌گردند.",
         {"atk": 10, "magic": 10, "luck": 6}, [T("cd_cut", 0.0, 0.25), T("skill_power", 0.10)]),
    # --- charms and special items --------------------------------------------------------------------------------------
    _arm("evil_eye", "تعویذ چشم‌بد", "🧿", "charm", 2, "چشمی که بدخواهان را می‌پاید.",
         {"defense": 2}, [T("evade", 0.06)]),
    _arm("bravery_charm", "تعویذ شجاعت", "🔥", "charm", 2, "سه نوبت اول، دلتان از آتش است.",
         {"atk": 3}, [T("opening", 0.20, 1, 3)]),
    _arm("old_warrior_badge", "نشان جنگجوی کهن", "🎖️", "charm", 3, "وقتی پایتان به لبه رسید، یک بار دیگر برمی‌خیزید.",
         {"hp": 25}, [T("last_stand", 0.25)]),
    _arm("silence_seal", "مهر خاموشی", "🔇", "charm", 3, "ضربه‌هایتان دشمن را کُند و خسته می‌کند.",
         {"magic": 4}, [T("inflict_slow", 0.2, 0.25, 2)]),
    _arm("eagle_eye", "چشم عقاب", "🦅", "charm", 3, "نقطه‌ی ضعف را از دور می‌بیند.",
         {"luck": 5}, [T("armor_pen", 0.10), T("crit_chance", 0.04)]),
    _arm("time_charm", "طلسم زمان", "⏳", "charm", 4, "گاهی زمان برایتان می‌ایستد و مهارت‌ها زودتر برمی‌گردند.",
         {"speed": 4}, [T("cd_cut", 0.0, 0.35)]),
    _arm("blood_chalice", "جام خون", "🏆", "charm", 4, "جامی که هرگز خالی نمی‌شود؛ از ضربه‌ها جان می‌نوشد.",
         {"hp": 30}, [T("leech_pct", 0.06), T("regen", 0.02)]),
    _arm("phoenix_charm", "طلسم ققنوس", "🪶", "charm", 5, "از خاکسترِ خودتان دوباره برمی‌خیزید.",
         {"hp": 40, "magic": 6}, [T("undying", 0.30)]),
    # --- speed and power -------------------------------------------------------------------------------------------------
    _arm("gale_boots", "چکمه‌ی باد", "👢", "boost", 2, "گام‌هایتان سبک می‌شود و ضربه‌ها خطا می‌روند.",
         {"speed": 5}, [T("evade", 0.03)]),
    _arm("battle_gloves", "دستکش نبرد", "🧤", "boost", 2, "مشت را سنگین‌تر می‌کند.",
         {"atk": 5, "hp": 8}),
    _arm("giant_belt", "کمربند غول", "🥋", "boost", 3, "زور غول‌ها را به کمر می‌بندید.",
         {"atk": 6, "hp": 20}, price=5_000),
    _arm("lightning_boots", "چکمه‌ی برق", "⚡", "boost", 3, "پیش از آن‌که چشم باز کنند، دومین ضربه هم رسیده است.",
         {"speed": 8, "atk": 3}, [T("extra_hit", 0.0, 0.16), T("armor_pen", 0.08)]),
    _arm("rage_gauntlets", "دستکش خشم", "🥊", "boost", 4, "هر چه خشم بیشتر، ضربه‌ی دوم نزدیک‌تر.",
         {"atk": 12, "speed": 3}, [T("extra_hit", 0.0, 0.18)]),
    _arm("storm_crown", "تاج طوفان", "👑", "boost", 4, "ابرهای طوفان به فرمانِ شماست.",
         {"speed": 9, "magic": 8, "atk": 4}, [T("extra_hit", 0.0, 0.22), T("armor_pen", 0.10)]),
    _arm("dragon_armband", "بازوبند اژدها", "🐲", "boost", 5, "نیرویی که فقط در خون اژدهاست.",
         {"atk": 16, "speed": 6}, [T("extra_hit", 0.0, 0.25), T("skill_power", 0.08)]),
    _arm("clear_charm", "طلسم پاک‌کننده", "🪬", "charm", 3, "اثرهای بد را از تن‌تان دور نگه می‌دارد.",
         {"hp": 15}, [T("resist_all", 0.20)]),
    # --- healing -------------------------------------------------------------------------------------------------------
    _arm("green_pendant", "گردنبند سبز", "📗", "heal", 1, "عطر گیاهان شفابخش را با خود دارد.",
         {"hp": 15}, [T("regen", 0.015)], price=480),
    _arm("heal_pendant", "گردنبند شفا", "💠", "heal", 2, "زخم‌هایتان را در میانه‌ی نبرد هم می‌بندد.",
         {"hp": 25}, [T("regen", 0.025)]),
    _arm("life_flask", "بطری حیات", "🍶", "heal", 2, "وقتی دفاع می‌کنید، جرعه‌ای از آن می‌نوشید.",
         {"hp": 20}, [T("defend_heal", 0.08)]),
    _arm("small_spring", "چشمه‌ی کوچک", "⛲", "heal", 3, "قطره‌قطره جان می‌بخشد.",
         {"hp": 40}, [T("regen", 0.03)]),
    _arm("mercy_charm", "تعویذ رحمت", "🕊️", "heal", 3, "وقتی کار به لبه می‌رسد، دستی نامرئی شما را می‌گیرد.",
         {"hp": 30}, [T("last_stand", 0.30)]),
    _arm("healing_bowl", "کاسه‌ی بهبود", "🥣", "heal", 4, "دفاع کردن را به بهترین درمان تبدیل می‌کند.",
         {"hp": 60}, [T("regen", 0.04), T("defend_heal", 0.10)]),
    _arm("ancient_heart", "قلب درخت کهن", "🌳", "heal", 4, "ریشه‌هایش هنوز در خاک جان دارند.",
         {"hp": 70, "defense": 4}, [T("regen", 0.035)]),
    _arm("eternal_elixir", "اکسیر جاودان", "⚗️", "heal", 5, "بوی همیشه‌زنده ماندن می‌دهد.",
         {"hp": 100}, [T("regen", 0.04), T("last_stand", 0.35)]),
    # --- spoils of the bosses: one exclusive piece per element, never on sale ---------------------------------------
    _arm("b_fire", "قلب آتشفشان", "🌋", "charm", 4, "از سینه‌ی باس‌های آتشین بیرون کشیده شده؛ هنوز می‌سوزد.",
         {"atk": 10}, [T("inflict_burn", 0.22, 0.35, 3)], boss=True),
    _arm("b_ice", "اشک یخ‌بند", "🧊", "ring", 4, "قطره‌ای از گریه‌ی باس‌های یخی که هرگز آب نمی‌شود.",
         {"magic": 9, "defense": 4}, [T("inflict_freeze", 0, 0.15, 1)], boss=True),
    _arm("b_lightning", "تاج صاعقه", "⚡", "boost", 4, "صاعقه‌ای که در طلا زندانی شده است.",
         {"speed": 10, "atk": 6}, [T("extra_hit", 0.0, 0.20)], boss=True),
    _arm("b_nature", "ریشه‌ی جهان", "🌿", "heal", 4, "ریشه‌ای که از دل جنگل‌های باس‌های طبیعت کنده شده.",
         {"hp": 80}, [T("regen", 0.05)], boss=True),
    _arm("b_water", "مروارید طوفان", "🫧", "ring", 4, "دریا در آن می‌غلتد؛ ضربه‌ها از رویش می‌لغزند.",
         {"magic": 8, "hp": 30}, [T("evade", 0.10), T("regen", 0.02)], boss=True),
    _arm("b_shadow", "نقاب شب", "🎭", "charm", 4, "هر که بپوشد، از پشت می‌زند.",
         {"speed": 6, "luck": 6}, [T("backstab", 0.30), T("crit_chance", 0.08)], boss=True),
    _arm("b_earth", "قلب سنگ", "🪨", "armor", 4, "تپش آرام زمین در سینه‌ی شماست.",
         {"defense": 14, "hp": 60}, [T("dmg_cut", 0.12)], boss=True),
    _arm("b_wind", "پر گردباد", "🪽", "boost", 4, "سبک‌تر از باد؛ ضربه‌ها را گم می‌کند.",
         {"speed": 12}, [T("evade", 0.10), T("extra_hit", 0.0, 0.12)], boss=True),
    _arm("b_light", "پرتو نخستین", "🌟", "ring", 4, "نخستین نوری که از تاریکی بیرون آمد.",
         {"magic": 8, "luck": 6}, [T("cd_cut", 0.0, 0.30), T("skill_power", 0.10)], boss=True),
    _arm("b_poison", "نیش ملکه", "🦂", "weapon", 4, "نیش ملکه‌ی زهر؛ هر زخمش دیر خوب می‌شود.",
         {"atk": 12}, [T("inflict_poison", 0.2, 0.40, 3), T("backstab", 0.15)], boss=True),
    # --- mythic: the rarest war gear of the realm (also dropped by the strongest bosses) ------------------------------
    _arm("doom_blade", "تیغ آخرالزمان", "☄️", "weapon", 6, "گفته‌اند پایان جهان را با آن نوشته‌اند.",
         {"atk": 34, "speed": 4}, [T("execute", 0.40), T("leech_pct", 0.10), T("phys_power", 0.08)]),
    _arm("eternity_plate", "زره‌ی ابدیت", "🏛️", "armor", 6, "نه زمان می‌شکندش، نه افسون.",
         {"defense": 28, "hp": 120}, [T("dmg_cut", 0.14), T("regen", 0.03), T("resist_all", 0.25)]),
    _arm("first_crown", "تاج نخستین فرمانروا", "🔱", "ring", 6, "هر که بر سر گذاشت، قلمرو را به نامش نوشت.",
         {"atk": 12, "magic": 12, "defense": 8, "luck": 8}, [T("cd_cut", 0.0, 0.30), T("skill_power", 0.12), T("crit_chance", 0.06)]),
)

ARMS: dict[str, Arm] = {a.id: a for a in _ARMS}
_BY_NAME = {normalize(a.name): a for a in _ARMS}


def get_arm(arm_id: str) -> Arm:
    return ARMS[arm_id]


def find_arm(text: str) -> Arm | None:
    return _BY_NAME.get(normalize(text))


def arms_of(cat: str) -> list[Arm]:
    """The pieces the shop sells in a category (boss spoils are not for sale)."""
    return sorted((a for a in _ARMS if a.cat == cat and not a.boss), key=lambda a: (a.rarity, a.price))


def pack_id(arm_id: str) -> str:
    """Id of the real-money pack that sells this piece (see ``packs.py``)."""
    return f"arm_{arm_id}"


def arm_of_pack(pid: str) -> Arm | None:
    return ARMS.get(pid[4:]) if pid.startswith("arm_") else None


# --- upgrading a piece: +1 to +10 -------------------------------------------------------------------------------------------------------
MAX_UPGRADE = 10
#: the chance that an attempt to reach +1, +2, ... +10 succeeds
UPGRADE_CHANCE = (1.0, 0.95, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20)


def upgrade_gold(arm: Arm, target: int) -> int:
    return round(arm.price * 0.10 * target**1.3)


def upgrade_materials(target: int) -> dict[str, int]:
    """What reaching ``+target`` consumes besides coins (all of it comes from the realm's own activities)."""
    if target <= 3:
        return {"iron_ore": 2 * target}
    if target <= 6:
        return {"iron_ore": target, "crystal_shard": target - 3}
    if target <= 9:
        return {"crystal_shard": target - 3, "gold_ore": target - 5}
    return {"dragon_scale": 2, "crystal_shard": 6, "gold_ore": 5}


def upgraded_stats(arm: Arm, level: int) -> Stats:
    """Stats of a piece at ``+level``: every level adds 12% of the base, at least +1 on each stat the piece has."""
    if level <= 0:
        return arm.stats
    import math

    values = {}
    for name, base in arm.stats.as_dict().items():
        values[name] = base + (max(level, math.ceil(base * 0.12 * level)) if base > 0 else 0)
    return Stats(**values)


def plus(level: int) -> str:
    return f"+{fa(level)}" if level else ""
