"""How a hero grows beyond the number on his level: attribute points, level unlocks and class talents.

* every level gives ``POINTS_PER_LEVEL`` attribute points; the player decides where they go, so two heroes of one class
  can be built very differently;
* some things open only at a given level (skills, gear places, talent places, ...);
* every class has talents; a hero may carry only as many as his level allows, so he has to choose.

All of it is data: add an attribute, an unlock or a talent here and the screens and the fight engine pick it up.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.text import fa
from .arms import Trait, trait_text
from .stats import Stats

POINTS_PER_LEVEL = 2
#: the most points that can go into one attribute (keeps builds from collapsing into one number)
ATTR_CAP = 400
#: gold per hero level to take all the points back and spend them again
RESET_GOLD_PER_LEVEL = 400


@dataclass(frozen=True)
class Attr:
    id: str
    emoji: str
    name: str
    blurb: str
    #: what one point adds (floats; the sum is rounded once)
    atk: float = 0.0
    defense: float = 0.0
    hp: float = 0.0
    magic: float = 0.0
    speed: float = 0.0
    luck: float = 0.0
    #: what one point adds to the resistance against harmful effects (burn, poison, freeze, ...)
    resist: float = 0.0


ATTRS: dict[str, Attr] = {
    a.id: a
    for a in (
        Attr("str", "💪", "قدرت", "آسیب فیزیکی و سلامتی بیشتر", atk=1.0, hp=3),
        Attr("agi", "🏃", "چابکی", "سرعت بیشتر و جاخالی دادن", speed=0.8, luck=0.2),
        Attr("int", "🧠", "هوش", "مهارت‌های جادویی قوی‌تر", magic=1.2),
        Attr("vit", "🛡️", "استقامت", "دفاع، سلامتی و مقاومت در برابر اثرها", defense=0.7, hp=5, resist=0.0015),
        Attr("luk", "🍀", "شانس", "ضربه‌ی کاری و اتفاق‌های ویژه", luck=1.0),
    )
}


def points_earned(level: int) -> int:
    return max(0, level - 1) * POINTS_PER_LEVEL


def attr_stats(points: dict[str, int]) -> Stats:
    """The stat bonus of the attribute points a hero has spent."""
    sums = {k: 0.0 for k in ("hp", "atk", "defense", "magic", "speed", "luck")}
    for attr_id, count in points.items():
        attr = ATTRS.get(attr_id)
        if attr is None:
            continue
        for key in sums:
            sums[key] += getattr(attr, key) * count
    return Stats(**{k: round(v) for k, v in sums.items()})


def attr_resist(points: dict[str, int]) -> float:
    return min(0.25, sum(ATTRS[k].resist * n for k, n in points.items() if k in ATTRS))


def attr_effect_text(attr: Attr) -> str:
    parts = []
    for key, label in (("atk", "⚔️ حمله"), ("hp", "❤️ جان"), ("defense", "🛡️ دفاع"), ("magic", "✨ جادو"), ("speed", "💨 سرعت"), ("luck", "🍀 شانس")):
        value = getattr(attr, key)
        if value:
            parts.append(f"{label} +{fa(f'{value:g}'.replace('.', '٫'))}")
    if attr.resist:
        parts.append("🧿 مقاومت")
    return " · ".join(parts)


# --- things that open at a level ----------------------------------------------------------------------------------------------------
#: the level at which each of the hero's three skills opens
SKILL_LEVELS = (1, 5, 12)
#: the level at which each of the four gear places opens
SLOT_LEVELS = (1, 1, 8, 15)
#: the level at which the 1st, 2nd and 3rd talent place opens
TALENT_LEVELS = (5, 15, 25)


def slots_open(level: int) -> int:
    return sum(level >= need for need in SLOT_LEVELS)


def talent_places(level: int) -> int:
    return sum(level >= need for need in TALENT_LEVELS)


#: (level, emoji, title, what it gives) shown on the progress page and when a hero reaches the level
UNLOCKS: tuple[tuple[int, str, str, str], ...] = (
    (1, "⚔️", "مهارت اول", "نخستین مهارت اختصاصی قهرمان"),
    (2, "🎯", "امتیاز ویژگی", "با هر سطح ۲ امتیاز می‌گیرید و خودتان تقسیمشان می‌کنید"),
    (5, "🌟", "مهارت دوم", "مهارتی قوی‌تر با اثر ویژه"),
    (5, "🧬", "نخستین استعداد", "یک استعداد کلاس را انتخاب کنید"),
    (8, "🧰", "جایگاه سوم تجهیزات", "سومین تجهیزات را همزمان بپوشید"),
    (12, "💥", "مهارت سوم", "مهارت ویژه و نهایی قهرمان"),
    (15, "🧰", "جایگاه چهارم تجهیزات", "چهار تجهیزات هم‌زمان"),
    (15, "🧬", "استعداد دوم", "دومین استعداد کلاس"),
    (15, "🎭", "کلاس دوم", "یک کلاس دوم برای قهرمان"),
    (20, "✨", "بیداری قدرت", "قدرت پنهان نژاد بیدار می‌شود"),
    (25, "🧬", "استعداد سوم", "سومین استعداد کلاس"),
)


def unlocked_between(old: int, new: int) -> list[tuple[int, str, str, str]]:
    return [u for u in UNLOCKS if old < u[0] <= new]


def next_unlock(level: int) -> tuple[int, str, str, str] | None:
    return next((u for u in UNLOCKS if u[0] > level), None)


# --- talents -------------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Talent:
    id: str
    class_id: str
    emoji: str
    name: str
    blurb: str
    traits: tuple[Trait, ...] = ()
    stats: Stats = Stats()

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"

    def lines(self) -> list[str]:
        out = self.stats.bonus_lines()
        out += [text for t in self.traits if (text := trait_text(t))]
        return out


def _t(id_, cls, emoji, name, blurb, *traits, **stats) -> Talent:  # noqa: ANN001, ANN003
    return Talent(id_, cls, emoji, name, blurb, tuple(traits), Stats(**stats))


T = Trait
TALENTS: tuple[Talent, ...] = (
    # warrior
    _t("w_might", "warrior", "💪", "خشم پولادین", "ضربه‌های فیزیکی‌ات سنگین‌تر فرود می‌آیند.", T("phys_power", 0.10)),
    _t("w_iron", "warrior", "🧱", "پوست سنگی", "ضربه‌ی کاری دشمن کمتر به تو کار می‌کند.", T("crit_resist", 0.40)),
    _t("w_last", "warrior", "🩸", "ایستادگی", "وقتی جانت کم شد، دفاعت بالا می‌رود.", T("low_hp_def", 0.30)),
    _t("w_vigor", "warrior", "❤️", "تن‌ومند", "جان بیشتر برای نبردهای طولانی.", hp=45),
    _t("w_cleave", "warrior", "🪓", "شکافنده", "بخشی از دفاع دشمن را نادیده می‌گیری.", T("armor_pen", 0.12)),
    _t("w_thirst", "warrior", "🍷", "خون‌تشنه", "بخشی از آسیب ضربه‌هایت جان می‌شود.", T("leech_pct", 0.05)),
    # mage
    _t("m_focus", "mage", "🔮", "تمرکز", "جادوی قوی‌تر در هر مهارت.", T("magic_power", 0.10)),
    _t("m_pierce", "mage", "🗡️", "نفوذ جادو", "از دفاع دشمن کمتر می‌گذرد.", T("armor_pen", 0.12)),
    _t("m_calm", "mage", "🧘", "ذهن آرام", "گاهی مهارت‌ها زودتر برمی‌گردند.", T("cd_cut", 0.0, 0.18)),
    _t("m_ward", "mage", "🧿", "سپر ذهن", "در برابر سوختگی، زهر و یخ‌زدگی مقاوم می‌شوی.", T("resist_all", 0.20)),
    _t("m_flame", "mage", "🔥", "آتش درون", "ضربه‌هایت گاهی دشمن را می‌سوزانند.", T("inflict_burn", 0.18, 0.20, 3)),
    _t("m_spring", "mage", "⛲", "چشمه‌ی جادو", "هر نوبت کمی جان بازمی‌یابی.", T("regen", 0.015)),
    # archer
    _t("a_eye", "archer", "🦅", "چشم عقاب", "ضربه‌ی کاری بیشتر.", T("crit_chance", 0.08)),
    _t("a_quick", "archer", "⚡", "تیراندازی تند", "گاهی ضربه‌ی دوم می‌زنی.", T("extra_hit", 0.0, 0.14)),
    _t("a_venom", "archer", "☠️", "تیر زهر", "ضربه‌هایت گاهی دشمن را مسموم می‌کنند.", T("inflict_poison", 0.15, 0.20, 3)),
    _t("a_agile", "archer", "💨", "چابک", "بیشتر جاخالی می‌دهی.", T("evade", 0.06)),
    _t("a_far", "archer", "🎯", "دوردست", "ضربه‌های فیزیکی‌ات قوی‌تر.", T("phys_power", 0.08)),
    _t("a_hunter", "archer", "🏹", "شکارچی", "دشمنِ آسیب‌دیده با اثرها را بیشتر زخمی می‌کنی.", T("backstab", 0.15)),
    # guardian
    _t("g_wall", "guardian", "🧱", "دیوار", "از هر آسیبی که می‌بینی کمی کم می‌شود.", T("dmg_cut", 0.06)),
    _t("g_thorn", "guardian", "🌵", "خار", "بخشی از آسیب به مهاجم برمی‌گردد.", T("thorns", 0.12)),
    _t("g_mend", "guardian", "💚", "بازسازی", "هر نوبت کمی جان بازمی‌یابی.", T("regen", 0.02)),
    _t("g_ward", "guardian", "🛡️", "سپر نخستین", "نبرد را با سپر شروع می‌کنی.", T("shield_start", 1.0)),
    _t("g_resist", "guardian", "🧿", "تن مقاوم", "در برابر اثرهای بد مقاومی.", T("resist_all", 0.25)),
    _t("g_bash", "guardian", "💫", "کوبنده", "ضربه‌هایت گاهی دشمن را گیج می‌کنند.", T("inflict_stun", 0, 0.10, 1)),
    # rogue
    _t("r_crit", "rogue", "🎯", "چشم قاتل", "ضربه‌ی کاری بیشتر.", T("crit_chance", 0.10)),
    _t("r_back", "rogue", "🗡️", "ضربه‌ی پشت", "به دشمنِ اثرخورده آسیب بسیار بیشتری می‌زنی.", T("backstab", 0.25)),
    _t("r_twin", "rogue", "⚡", "حمله‌ی دوم", "اغلب ضربه‌ی دوم هم می‌زنی.", T("extra_hit", 0.0, 0.20)),
    _t("r_evade", "rogue", "🌑", "سایه‌گریز", "بیشتر جاخالی می‌دهی.", T("evade", 0.08)),
    _t("r_venom", "rogue", "🐍", "خنجر زهری", "ضربه‌هایت گاهی مسموم می‌کنند.", T("inflict_poison", 0.15, 0.25, 3)),
    _t("r_thirst", "rogue", "🩸", "تشنه", "بخشی از آسیب ضربه‌ها جانت می‌شود.", T("leech_pct", 0.06)),
)
TALENT_BY_ID: dict[str, Talent] = {t.id: t for t in TALENTS}


def talents_of(class_id: str) -> list[Talent]:
    return [t for t in TALENTS if t.class_id == class_id]
