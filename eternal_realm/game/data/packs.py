"""Real-money products. Prices are in rial (the unit of Bale wallet invoices).

Everything sold here is shown with its exact content before the player pays. Change prices and
contents freely: nothing else in the code depends on the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
}

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
        Pack("svc_rename", "🏷️", "برگه‌ی تغییر نام", 40_000, items={"rename_ticket": 1}, section="services"),
        Pack("svc_race", "🧬", "برگه‌ی تغییر نژاد", 100_000, items={"race_ticket": 1}, section="services"),
        Pack("svc_class", "⚔️", "برگه‌ی تغییر کلاس", 100_000, items={"class_ticket": 1}, section="services"),
        Pack("lucky_s", "🎲", "بسته شانسی کوچک", 60_000, section="lucky", lucky=True),
        Pack("lucky_m", "🎲", "بسته شانسی متوسط", 200_000, section="lucky", lucky=True),
        Pack("lucky_l", "🎲", "بسته شانسی بزرگ", 600_000, section="lucky", lucky=True),
    )
}

#: an unpaid order is abandoned after this long
ORDER_TTL_SECONDS = 3600
