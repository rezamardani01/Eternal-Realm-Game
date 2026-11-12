"""Real-money products. Prices are in rial (the unit of Bale wallet invoices).

Everything sold here is shown with its exact content before the player pays. Change prices and
contents freely: nothing else in the code depends on the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .arms import ARMS, pack_id


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
    "city": "🏰 منابع فرمانروایی",
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
            items={"steel_sword": 1, "chain_mail": 1, "big_energy_potion": 5}, section="bundles",
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
        Pack("deal_staff", "🔮", "عصای کریستالی", 220_000, items={"crystal_staff": 1}, section="deal"),
        Pack("deal_dagger", "🗡️", "خنجر سایه", 180_000, items={"shadow_dagger": 1}, section="deal"),
        Pack("deal_boots", "👟", "چکمه تندرو", 90_000, items={"swift_boots": 1}, section="deal"),
        Pack("deal_chain", "🦺", "زره زنجیری", 100_000, items={"chain_mail": 1}, section="deal"),
        Pack("deal_ring", "💍", "انگشتر قدرت", 90_000, items={"strength_ring": 1}, section="deal"),
        Pack("deal_amulet", "📿", "گردنبند حیات", 90_000, items={"life_amulet": 1}, section="deal"),
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
        # the rare materials of the forge, each at a price that matches how hard it is to find (a dragon scale: 5 000 toman)
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
        # everything a forge recipe asks for (except the gold and the base piece), a little cheaper than buying the parts
        Pack("kit_fire_sword", "🔥", "کیت شمشیر آتشین", 280_000, section="rare",
             items={"dragon_scale": 3, "crystal_shard": 5, "iron_ore": 10}),
        Pack("kit_dragon_armor", "🐲", "کیت زره اژدها", 350_000, section="rare",
             items={"dragon_scale": 5, "crystal_shard": 4, "iron_ore": 12}),
        Pack("kit_shadow_dagger", "🗡️", "کیت خنجر سایه", 155_000, section="rare",
             items={"crystal_shard": 3, "gold_ore": 4, "monster_fang": 6}),
        Pack("kit_crystal_staff", "🔮", "کیت عصای کریستالی", 220_000, section="rare",
             items={"crystal_shard": 6, "moon_herb": 4, "old_scroll": 3}),
        Pack("kit_dragonbane_helm", "🪖", "کیت کلاه‌خود اژدهاکُش", 150_000, section="rare",
             items={"dragon_scale": 3, "iron_ore": 8}),
        Pack("kit_dragonbane_boots", "👢", "کیت چکمه اژدهاکُش", 180_000, section="rare",
             items={"dragon_scale": 3, "monster_hide": 8}),
        Pack("lucky_s", "🎲", "بسته شانسی کوچک", 60_000, section="lucky", lucky=True),
        Pack("lucky_m", "🎲", "بسته شانسی متوسط", 200_000, section="lucky", lucky=True),
        Pack("lucky_l", "🎲", "بسته شانسی بزرگ", 600_000, section="lucky", lucky=True),
    )
}

# every piece of hero war gear can also be bought with real money, at the price of its coins; it is the same piece
for _arm in ARMS.values():
    PACKS[pack_id(_arm.id)] = Pack(
        pack_id(_arm.id), _arm.emoji, _arm.name, _arm.rial, arms={_arm.id: 1}, section="arms"
    )

#: an unpaid order is abandoned after this long
ORDER_TTL_SECONDS = 3600
