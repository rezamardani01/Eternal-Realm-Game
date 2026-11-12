"""Real-money products. Prices are in rial (the unit of Bale wallet invoices).

Everything sold here is shown with its exact content before the player pays. Change prices and
contents freely: nothing else in the code depends on the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .arms import ARMS, PRICE_RISE, pack_id


@dataclass(frozen=True)
class Pack:
    id: str
    emoji: str
    title: str  # <= 32 characters (Bale invoice limit)
    price_rial: int
    gold: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)
    section: str = "coins"
    #: contents are rolled at delivery from the day's theme (see lucky.py)
    lucky: bool = False
    #: a companion pet delivered with this pack
    pet: str = ""
    #: unlocks the current season's ticket track
    season: bool = False
    #: days of VIP the pack adds
    vip_days: int = 0
    #: hours of the 2x reward boost the pack adds
    boost_hours: int = 0
    #: experience the pack gives (applied to the buyer's current level)
    xp: int = 0
    #: spins of the wheel of fortune the pack adds
    spins: int = 0
    #: resources added to the buyer's city (gold, food, wood, stone, iron)
    city: dict[str, int] = field(default_factory=dict)
    #: hours of city shield the pack adds
    city_shield_hours: int = 0
    #: pieces of hero war gear the pack adds (see arms.py)
    arms: dict[str, int] = field(default_factory=dict)

    @property
    def price_toman(self) -> int:
        return self.price_rial // 10

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.title}"


SECTIONS = {
    "coins": "🪙 بسته‌های سکه",
    "crystals": "💎 بسته‌های کریستال",
    "bundles": "🎁 بسته‌های ویژه",
    "materials": "⛓️ منابع",
    "lucky": "🎲 بسته‌های شانسی",
    "pets": "🐾 حیوانات همراه",
    "services": "🎫 خدمات",
    "path": "🎟️ مسیر قهرمانی",
    "vip": "💠 اشتراک VIP",
    "boost": "🚀 بوست دو برابر",
    "xp": "⭐ بسته‌های تجربه",
    "wheel": "🎡 گردونه شانس",
    "city": "🏰 منابع دهکده",
    "rare": "💠 منابع کمیاب",
}

BOOST_FACTOR = 2

PACKS: dict[str, Pack] = {
    p.id: p
    for p in (
        Pack("coins_s", "🪙", "۵٬۰۰۰ سکه", 50_000, gold=5_000, section="coins"),
        Pack("coins_m", "🪙", "۳۰٬۰۰۰ سکه", 250_000, gold=30_000, section="coins"),
        Pack("coins_l", "💰", "۱۰۰٬۰۰۰ سکه", 700_000, gold=100_000, section="coins"),
        Pack("crystal_s", "💎", "۲۰ کریستال", 100_000, crystal=20, section="crystals"),
        Pack("crystal_m", "💎", "۱۱۰ کریستال", 500_000, crystal=110, section="crystals"),
        Pack("crystal_l", "💎", "۳۰۰ کریستال", 1_200_000, crystal=300, section="crystals"),
        Pack(
            "adventurer", "🧳", "بسته ماجراجو", 150_000, gold=3_000,
            items={"big_energy_potion": 5, "magic_chest": 1, "gold_ore": 3}, section="bundles",
        ),
        Pack(
            "chests_x5", "🎁", "۵ صندوقچه جادویی", 400_000, items={"magic_chest": 5}, section="bundles",
        ),
        Pack("ore_5", "⛓️", "۵ سنگ آهن", 12_000, items={"iron_ore": 5}, section="materials"),
        Pack("ore_10", "⛓️", "۱۰ سنگ آهن", 22_000, items={"iron_ore": 10}, section="materials"),
        Pack("ore_s", "⛓️", "۲۰ سنگ آهن", 40_000, items={"iron_ore": 20}, section="materials"),
        Pack("ore_m", "⛓️", "۱۰۰ سنگ آهن", 160_000, items={"iron_ore": 100}, section="materials"),
        Pack("ore_l", "⛓️", "۴۰۰ سنگ آهن", 500_000, items={"iron_ore": 400}, section="materials"),
        Pack("deal_magic_chest", "🎁", "صندوقچه جادویی", 90_000, items={"magic_chest": 1}, section="deal"),
        Pack("deal_royal_chest", "👑", "صندوقچه سلطنتی", 300_000, items={"royal_chest": 1}, section="deal"),
        Pack("deal_energy_x10", "🔋", "۱۰ معجون انرژی بزرگ", 120_000, items={"big_energy_potion": 10}, section="deal"),
        Pack("deal_scales", "🐉", "۳ فلس اژدها", 200_000, items={"dragon_scale": 3}, section="deal"),
        Pack("pet_fox", "🦊", "حیوان همراه: روباه آتشین", 80_000, pet="fox", section="pets"),
        Pack("pet_wolf", "🐺", "حیوان همراه: گرگ سپیده", 120_000, pet="wolf", section="pets"),
        Pack("pet_phoenix", "🔥", "حیوان همراه: ققنوس کوچک", 250_000, pet="phoenix", section="pets"),
        Pack("pet_tiger", "🐯", "حیوان همراه: ببر برفی", 160_000, pet="tiger", section="pets"),
        Pack("pet_eagle", "🦅", "حیوان همراه: عقاب طلایی", 400_000, pet="eagle", section="pets"),
        Pack("pet_unicorn", "🦄", "حیوان همراه: تک‌شاخ مهتاب", 700_000, pet="unicorn", section="pets"),
        Pack("pet_dragon", "🐲", "حیوان همراه: اژدهای کوچک", 900_000, pet="dragon", section="pets"),
        Pack("season_ticket", "🎟️", "بلیط مسیر قهرمانی (این فصل)", 499_000, season=True, section="path"),
        Pack("vip_30", "💠", "اشتراک VIP ۳۰ روزه", 199_000, vip_days=30, section="vip"),
        Pack("boost_24", "🚀", "بوست دو برابر ۲۴ ساعته", 60_000, boost_hours=24, section="boost"),
        Pack("boost_48", "🚀", "بوست دو برابر ۴۸ ساعته", 100_000, boost_hours=48, section="boost"),
        Pack("boost_72", "🚀", "بوست دو برابر ۷۲ ساعته", 130_000, boost_hours=72, section="boost"),
        Pack("xp_s", "⭐", "بسته‌ی تجربه‌ی کوچک", 40_000, xp=1_500, section="xp"),
        Pack("xp_m", "🌟", "بسته‌ی تجربه‌ی متوسط", 120_000, xp=6_000, section="xp"),
        Pack("xp_l", "✨", "بسته‌ی تجربه‌ی بزرگ", 300_000, xp=20_000, section="xp"),
        Pack("svc_rename", "🏷️", "برگه‌ی تغییر نام", 40_000, items={"rename_ticket": 1}, section="services"),
        Pack("svc_race", "🧬", "برگه‌ی تغییر نژاد", 100_000, items={"race_ticket": 1}, section="services"),
        Pack("svc_class", "⚔️", "برگه‌ی تغییر کلاس", 100_000, items={"class_ticket": 1}, section="services"),
        Pack("wheel_1", "🎡", "۱ فرصت گردونه شانس", 80_000, spins=1, section="wheel"),
        Pack("wheel_2", "🎡", "۲ فرصت گردونه شانس", 150_000, spins=2, section="wheel"),
        Pack("wheel_5", "🎡", "۵ فرصت گردونه شانس", 350_000, spins=5, section="wheel"),
        Pack("wheel_10", "🎡", "۱۰ فرصت گردونه شانس", 650_000, spins=10, section="wheel"),
        Pack("city_res_s", "📦", "بسته‌ی منابع شهر · کوچک", 60_000, section="city",
             city={"gold": 10_000, "food": 5_000, "wood": 5_000, "stone": 4_000, "iron": 2_000}),
        Pack("city_res_m", "📦", "بسته‌ی منابع شهر · متوسط", 200_000, section="city",
             city={"gold": 40_000, "food": 20_000, "wood": 20_000, "stone": 15_000, "iron": 8_000}),
        Pack("city_res_l", "📦", "بسته‌ی منابع شهر · بزرگ", 600_000, section="city",
             city={"gold": 150_000, "food": 80_000, "wood": 80_000, "stone": 60_000, "iron": 30_000}),
        Pack("city_build", "🏗️", "بسته‌ی ساخت‌وساز", 90_000, section="city",
             city={"gold": 20_000, "wood": 40_000, "stone": 40_000, "iron": 10_000}),
        Pack("city_army", "⚔️", "بسته‌ی لشکرسازی", 120_000, section="city",
             city={"gold": 40_000, "food": 30_000, "wood": 10_000, "iron": 20_000}),
        Pack("city_food", "🌾", "بسته‌ی آذوقه و غله", 40_000, section="city", city={"food": 60_000}),
        Pack("city_shield_24", "🔰", "سپر دفاعی شهر ۲۴ ساعته", 50_000, section="city", city_shield_hours=24),
        Pack("city_shield_72", "🔰", "سپر دفاعی شهر ۷۲ ساعته", 120_000, section="city", city_shield_hours=72),
        # the rare materials, each at a price that matches how hard it is to find (a dragon scale: 5 000 toman)
        Pack("rare_scale_1", "🐉", "۱ فلس اژدها", 50_000, items={"dragon_scale": 1}, section="rare"),
        Pack("rare_scale_3", "🐉", "۳ فلس اژدها", 135_000, items={"dragon_scale": 3}, section="rare"),
        Pack("rare_scale_5", "🐉", "۵ فلس اژدها", 210_000, items={"dragon_scale": 5}, section="rare"),
        Pack("rare_shard_1", "💠", "۱ پاره‌کریستال", 30_000, items={"crystal_shard": 1}, section="rare"),
        Pack("rare_shard_5", "💠", "۵ پاره‌کریستال", 135_000, items={"crystal_shard": 5}, section="rare"),
        Pack("rare_goldore_5", "🥇", "۵ سنگ طلا", 50_000, items={"gold_ore": 5}, section="rare"),
        Pack("rare_moon_5", "🍀", "۵ گیاه ماه‌تاب", 40_000, items={"moon_herb": 5}, section="rare"),
        Pack("rare_scroll_5", "📜", "۵ طومار کهنه", 35_000, items={"old_scroll": 5}, section="rare"),
        Pack("rare_fang_10", "🦷", "۱۰ دندان هیولا", 50_000, items={"monster_fang": 10}, section="rare"),
        Pack("rare_hide_10", "🧶", "۱۰ پوست هیولا", 50_000, items={"monster_hide": 10}, section="rare"),
        Pack("lucky_s", "🎲", "بسته شانسی کوچک", 60_000, section="lucky", lucky=True),
        Pack("lucky_m", "🎲", "بسته شانسی متوسط", 200_000, section="lucky", lucky=True),
        Pack("lucky_l", "🎲", "بسته شانسی بزرگ", 600_000, section="lucky", lucky=True),
    )
}

# --- the names the shop shows (a bigger container for a bigger amount), more sizes in every section, and the price rise ----
_TITLES = {
    "coins_s": "یک مشت سکه ×۵٬۰۰۰", "coins_m": "یک کیسه سکه ×۳۰٬۰۰۰", "coins_l": "یک صندوق سکه ×۱۰۰٬۰۰۰",
    "crystal_s": "یک مشت کریستال ×۲۰", "crystal_m": "یک جعبه کریستال ×۱۱۰", "crystal_l": "یک خورجین کریستال ×۳۰۰",
    "chests_x5": "یک کوله صندوقچه جادویی ×۵",
    "ore_5": "یک مشت سنگ آهن ×۵", "ore_10": "یک کیسه سنگ آهن ×۱۰", "ore_s": "یک خورجین سنگ آهن ×۲۰",
    "ore_m": "یک گاری سنگ آهن ×۱۰۰", "ore_l": "یک انبار سنگ آهن ×۴۰۰",
    "boost_24": "بوست دو برابر · یک روز", "boost_48": "بوست دو برابر · دو روز", "boost_72": "بوست دو برابر · سه روز",
    "xp_s": "یک جرعه تجربه ×۱٬۵۰۰", "xp_m": "یک جام تجربه ×۶٬۰۰۰", "xp_l": "یک خُم تجربه ×۲۰٬۰۰۰",
    "wheel_1": "یک چرخش شانس", "wheel_2": "دو چرخش شانس", "wheel_5": "پنج چرخش شانس", "wheel_10": "ده چرخش شانس",
    "city_res_s": "یک کیسه منابع شهر", "city_res_m": "یک گاری منابع شهر", "city_res_l": "یک انبار منابع شهر",
}

#: bigger and smaller sizes of the same goods (prices here are before the rise)
_EXTRA: tuple[Pack, ...] = (
    Pack("coins_xs", "🪙", "چند سکه ×۱٬۵۰۰", 20_000, gold=1_500, section="coins"),
    Pack("coins_xl", "🏦", "یک انبار سکه ×۳۵۰٬۰۰۰", 1_700_000, gold=350_000, section="coins"),
    Pack("coins_xxl", "👑", "گنجینه‌ی سکه ×۱٬۰۰۰٬۰۰۰", 4_200_000, gold=1_000_000, section="coins"),
    Pack("crystal_xs", "💎", "یک دانه کریستال ×۵", 30_000, crystal=5, section="crystals"),
    Pack("crystal_xl", "💎", "یک انبار کریستال ×۸۰۰", 2_800_000, crystal=800, section="crystals"),
    Pack("crystal_xxl", "💎", "گنجینه‌ی کریستال ×۲٬۰۰۰", 6_500_000, crystal=2_000, section="crystals"),
    Pack("ore_xl", "⛓️", "یک معدن سنگ آهن ×۱٬۵۰۰", 1_600_000, items={"iron_ore": 1_500}, section="materials"),
    Pack("chests_x10", "🎁", "یک گاری صندوقچه جادویی ×۱۰", 700_000, items={"magic_chest": 10}, section="bundles"),
    Pack("royal_x3", "👑", "سه صندوقچه‌ی سلطنتی", 800_000, items={"royal_chest": 3}, section="bundles"),
    Pack("energy_x25", "🔋", "یک خمره معجون انرژی ×۲۵", 250_000, items={"big_energy_potion": 25}, section="bundles"),
    Pack(
        "hero_chest", "🛡️", "بسته‌ی سردار", 600_000, gold=20_000, section="bundles",
        items={"big_energy_potion": 10, "magic_chest": 3, "royal_chest": 1},
    ),
    Pack("boost_168", "🚀", "بوست دو برابر · یک هفته", 270_000, boost_hours=168, section="boost"),
    Pack("boost_720", "🚀", "بوست دو برابر · یک ماه", 900_000, boost_hours=720, section="boost"),
    Pack("xp_xl", "🌊", "یک چشمه تجربه ×۶۰٬۰۰۰", 800_000, xp=60_000, section="xp"),
    Pack("xp_xxl", "🏞️", "یک رود تجربه ×۲۰۰٬۰۰۰", 2_300_000, xp=200_000, section="xp"),
    Pack("xp_xxxl", "🌌", "اقیانوس تجربه ×۶۰۰٬۰۰۰", 6_500_000, xp=600_000, section="xp"),
    Pack("svc_all", "🎫", "بسته‌ی بازسازی قهرمان", 220_000, section="services",
         items={"rename_ticket": 1, "race_ticket": 1, "class_ticket": 1}),
    Pack("wheel_25", "🎡", "یک کیسه‌ی شانس ×۲۵ چرخش", 1_500_000, spins=25, section="wheel"),
    Pack("wheel_50", "🎡", "یک انبار شانس ×۵۰ چرخش", 2_800_000, spins=50, section="wheel"),
    Pack("city_res_xl", "🏰", "گنجینه‌ی منابع شهر", 1_500_000, section="city",
         city={"gold": 400_000, "food": 200_000, "wood": 200_000, "stone": 150_000, "iron": 80_000}),
    Pack("rare_scale_10", "🐉", "۱۰ فلس اژدها", 400_000, items={"dragon_scale": 10}, section="rare"),
    Pack("rare_shard_10", "💠", "۱۰ پاره‌کریستال", 250_000, items={"crystal_shard": 10}, section="rare"),
    Pack("vip_90", "💠", "اشتراک VIP · سه ماه", 500_000, vip_days=90, section="vip"),
)
for _pack in _EXTRA:
    PACKS[_pack.id] = _pack
for _pid, _title in _TITLES.items():
    PACKS[_pid] = replace(PACKS[_pid], title=_title)


def _risen(rial: int) -> int:
    """The price after the rise, rounded to a whole thousand rial."""
    return round(rial * PRICE_RISE / 1000) * 1000


for _pid, _pack in list(PACKS.items()):
    PACKS[_pid] = replace(_pack, price_rial=_risen(_pack.price_rial))

# every piece of hero war gear can be bought with real money (the cheap ones also with coins, see arms.py); it is the same piece
for _arm in (a for a in ARMS.values() if not a.boss):
    PACKS[pack_id(_arm.id)] = Pack(
        pack_id(_arm.id), _arm.emoji, _arm.name, _arm.rial, arms={_arm.id: 1}, section="arms"
    )

#: an unpaid order is abandoned after this long
ORDER_TTL_SECONDS = 3600
