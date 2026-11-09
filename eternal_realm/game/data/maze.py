"""The Eternal Maze (هزارتوی ابدی): a roguelike run of up to thirty floors. Every floor offers three paths."""

from __future__ import annotations

FLOORS = 30
ENERGY = 10
#: heroes recover this share of their health at a campfire floor, and at the start of a run they are whole
CAMPFIRE_HEAL = 0.5
#: floors with a guardian instead of a choice
BOSS_FLOORS = {10: "crypt_lord", 20: "dragon_brood", 30: "lord_of_darkness"}
#: floors that offer a campfire in place of the treasure path
CAMPFIRE_EVERY = 7
#: lasting prizes for reaching a floor for the first time: (crystals, chest)
MILESTONES: dict[int, tuple[int, str]] = {10: (5, "magic_chest"), 20: (10, "magic_chest"), 30: (20, "royal_chest")}
#: a lost run still pays this share of what it gathered
DEFEAT_SHARE = 0.5

PATHS: dict[str, tuple[str, str, str]] = {
    "war": ("⚔️", "مسیر جنگجو", "نبرد با دشمنی قدرتمند؛ پاداش بیشتر و احتمال دریافت تجهیزات"),
    "gold": ("💎", "مسیر گنج", "منابع و غنیمت؛ اما ممکن است تله‌ای فعال شود"),
    "magic": ("🔮", "مسیر جادو", "نیروی موقت یا نفرین؛ ریسک و پاداش در دست جادوست"),
    "rest": ("🔥", "آتشگاه", "کنار آتش استراحت کنید و نیمی از جانتان برمی‌گردد"),
    "guardian": ("👑", "نگهبان طبقه", "راهی جز نبرد نیست؛ پاداش ماندگار در پی پیروزی است"),
}

#: foes by depth: floors up to the key use that list
POOLS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (7, ("skeleton_raider", "dark_goblin", "shadow_wolf", "zombie", "fire_imp")),
    (15, ("stone_guardian", "cultist", "ash_bandit", "ice_wolf", "frost_wraith", "lava_beast")),
    (23, ("burnt_warden", "forbidden_mage", "ice_knight", "mirror_shade", "blood_giant")),
    (30, ("bridge_keeper", "shadow_mage", "hell_warden", "jailer", "temple_guardian")),
)

#: temporary powers a blessing can give: id -> (label, stat, amount)
BLESSINGS: dict[str, tuple[str, str, float]] = {
    "atk": ("قدرت حمله‌ی شما ۱۲٪ بیشتر شد", "atk", 0.12),
    "def": ("دفاع شما ۱۵٪ بیشتر شد", "def", 0.15),
    "hp": ("جان شما ۱۵٪ بیشتر شد", "hp", 0.15),
}
CURSE = ("نفرین! قدرت حمله‌ی شما ۱۰٪ کمتر شد", "atk", -0.10)


def pool_for(floor: int) -> tuple[str, ...]:
    return next(foes for limit, foes in POOLS if floor <= limit)


def floor_mult(floor: int) -> float:
    return 0.8 + 0.02 * floor


def floor_reward(floor: int) -> tuple[int, int]:
    """Base gold and experience of one floor (scaled by the hero's level)."""
    return 40 + 8 * floor, 50 + 9 * floor
