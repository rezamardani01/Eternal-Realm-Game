"""Offline life (اعزام): send the hero away for a few hours and read the report on return.

Rewards are deliberately small per hour and capped by time and by a daily limit, so waiting never beats playing.
"""

from __future__ import annotations

from dataclasses import dataclass

HOURS = (1, 4, 8, 12)
DAILY_LIMIT = 1
#: the gold and experience of a report are multiplied by this
REWARD_SHARE = 0.4
#: the resources an expedition brings back are multiplied by this too
ITEM_SHARE = 0.75


@dataclass(frozen=True)
class Kind:
    id: str
    emoji: str
    name: str
    about: str
    #: per hour: gold, experience (both scaled by the hero's level) and items as (item, qty per hour, chance)
    gold: int = 0
    xp: int = 0
    items: tuple[tuple[str, float, float], ...] = ()
    #: a line that may be added to the report, with its chance per expedition
    finds: tuple[tuple[str, float], ...] = ()


KINDS: tuple[Kind, ...] = (
    Kind("mine", "⛏️", "اعزام به معدن", "سنگ آهن و سنگ از دل کوه", gold=10, items=(("iron_ore", 3, 1.0), ("stone", 4, 1.0), ("gold_ore", 0.4, 0.6)),
         finds=(("یک رگه‌ی غنی پیدا شد", 0.2),)),
    Kind("herb", "🌿", "گیاه‌چینی", "گیاه شفابخش و ماه‌تاب از جنگل", gold=10, items=(("herb", 4, 1.0), ("moon_herb", 0.7, 0.6)),
         finds=(("دشت گل‌های درخشان پیدا شد", 0.2),)),
    Kind("train", "⚔️", "تمرین در میدان", "تجربه‌ی رزمی بدون هیچ خطر", xp=70, finds=(("استاد قدیمی یک ترفند یاد داد", 0.2),)),
    Kind("treasure", "🧭", "جستجوی گنج", "سکه و گاهی صندوقچه", gold=70, items=(("wooden_chest", 0.12, 1.0),),
         finds=(("غار ناشناخته‌ای کشف شد", 0.25),)),
    Kind("guard", "🛡️", "نگهبانی از منطقه", "سکه و تجربه برای دفع خطر", gold=40, xp=30, finds=(("راهزنان از ترس گریختند", 0.3),)),
    Kind("fish", "🎣", "ماهیگیری در دریا", "ماهی و گاهی ماهی طلایی", gold=15, items=(("small_fish", 5, 1.0), ("trout", 2, 0.8), ("golden_fish", 0.15, 0.5)),
         finds=(("تور پر از ماهی درخشان شد", 0.2),)),
    Kind("hunt", "🏹", "شکار در جنگل", "پوست و دندان هیولا", gold=20, xp=15, items=(("monster_hide", 3, 1.0), ("monster_fang", 1.5, 0.7)),
         finds=(("رد یک شکار بزرگ پیدا شد", 0.2),)),
    Kind("caravan", "🐪", "همراهی کاروان", "سکه برای نگهبانی از مسیر", gold=55, xp=20, finds=(("بازرگانی پاداش اضافه داد", 0.25),)),
    Kind("ruins", "🏛️", "کاوش در ویرانه", "طومار و سکه‌ی کهن", gold=20, items=(("old_scroll", 1.0, 0.7), ("ancient_coin", 0.3, 0.5), ("crystal_shard", 0.1, 0.4)),
         finds=(("اتاق مخفی پیدا شد", 0.2),)),
    Kind("farm", "🌾", "کار در کشتزار", "گندم و عسل", gold=12, items=(("wheat", 6, 1.0), ("honey", 0.6, 0.6)), finds=(("محصول امسال فراوان بود", 0.25),)),
    Kind("sea", "🚢", "سفر دریایی", "سکه و تجربه از بندرها", gold=45, xp=35, items=(("crystal_shard", 0.12, 0.5),),
         finds=(("کشتی‌ای غرق‌شده دیده شد", 0.2),)),
)
_KIND = {k.id: k for k in KINDS}


def get_kind(kind_id: str) -> Kind:
    return _KIND[kind_id]
