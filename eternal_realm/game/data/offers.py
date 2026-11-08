"""Personal offers: small rules that look at one player's situation and suggest the next step.

Every rule is a plain, named check over a :class:`Facts` snapshot (no strings are ever executed).
To add an offer, add a check function and one :class:`Rule`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

DAY = 86400
#: at most this many personal offers per player per day, and never twice the same rule inside its cooldown
DAILY_CAP = 1


@dataclass
class Facts:
    level: int
    gold: int
    crystal: int
    wins: int
    losses: int
    inactive_days: int
    has_pet: bool
    in_clan: bool
    has_second_class: bool
    best_set_ratio: float
    best_set_name: str
    best_set_missing: int
    ready_path_rewards: int
    path_tier: int
    has_ticket: bool


@dataclass(frozen=True)
class Rule:
    id: str
    #: all of these must hold
    check: Callable[[Facts], bool]
    title: str
    #: message body; ``{x}`` fields are filled from the facts
    text: str
    button: str
    screen: str
    #: seconds before the same rule may fire again for the same player
    cooldown: int = 7 * DAY
    priority: int = 0


RULES: tuple[Rule, ...] = (
    Rule(
        "comeback", lambda f: f.inactive_days >= 7, "قلمرو دلتنگ شماست!",
        "{days} روز است که قلمرو را ندیده‌اید و میدان بدون شما ساکت مانده. برای بازگشتتان یک هدیه کنار گذاشته‌ایم: ۵۰۰ سکه.",
        "🎁 دریافت هدیه‌ی بازگشت", "offerreturn", 30 * DAY, 10,
    ),
    Rule(
        "path_ready", lambda f: f.ready_path_rewards >= 3, "جایزه‌هایتان منتظرند!",
        "{ready} جایزه‌ی «مسیر قهرمانی» آماده‌ی دریافت است. دستتان را دراز کنید و بردارید!",
        "🎟️ مسیر قهرمانی", "path", 3 * DAY, 8,
    ),
    Rule(
        "collection", lambda f: 0.6 <= f.best_set_ratio < 1.0, "مجموعه‌ی کارتتان تقریباً کامل است",
        "از مجموعه‌ی «{set}» فقط {missing} کارت کم دارید. با کامل شدنش عنوان و کریستال می‌گیرید.",
        "🃏 آلبوم کارت", "album", 5 * DAY, 6,
    ),
    Rule(
        "second_class", lambda f: f.level >= 15 and not f.has_second_class, "وقت یک تخصص تازه است",
        "به سطح {level} رسیده‌اید و می‌توانید کلاس دوم را برگزینید و نیمی از توان یک کلاس دیگر را بگیرید.",
        "✨ ارتقای قهرمان", "ascend", 10 * DAY, 5,
    ),
    Rule(
        "rich", lambda f: f.gold >= 20_000, "کیسه‌تان سنگین شده!",
        "{gold} سکه دارید. شاید وقتش باشد تجهیزات بهتری بخرید یا در کوره‌ی آهنگری چیزی افسانه‌ای بسازید.",
        "🛒 فروشگاه آیتم", "shop", 7 * DAY, 4,
    ),
    Rule(
        "struggling", lambda f: f.losses >= 5 and f.losses > f.wins * 1.5, "سخت‌ترین روزها",
        "چند شکست پشت‌سرهم دیده‌اید. یک ماجراجویی آرام (ماهیگیری، معدن و گیاه) سکه و تجربه می‌دهد تا قوی‌تر برگردید.",
        "🗺️ ماجراجویی", "adv", 5 * DAY, 3,
    ),
    Rule(
        "pet", lambda f: not f.has_pet and f.level >= 8 and f.gold >= 3_000, "یک یار وفادار می‌خواهید؟",
        "هنوز حیوان خانگی ندارید. یک گربه‌ی چابک یا شاهین نگهبان با سکه در دسترس شماست.",
        "🐱 حیوان خانگی", "pets", 10 * DAY, 2,
    ),
    Rule(
        "clan_war", lambda f: f.in_clan, "خاندانتان در جنگ است",
        "این هفته خاندانتان در «جنگ خاندان‌ها» امتیاز می‌گیرد. هر دوئل و باس به رتبه‌شان کمک می‌کند.",
        "⚔️ جنگ خاندان‌ها", "clanwar", 7 * DAY, 1,
    ),
    Rule(
        "ticket", lambda f: not f.has_ticket and f.path_tier >= 10, "مسیر قهرمانی را عمیق‌تر ببینید",
        "به مرحله‌ی {tier} رسیده‌اید. بلیط فصل جایزه‌های ویژه‌ی همه‌ی مراحل را باز می‌کند؛ کاملاً اختیاری است و جایزه‌های رایگان همچنان مال شماست.",
        "🎟️ مسیر قهرمانی", "path", 14 * DAY, 0,
    ),
)

_BY_ID = {r.id: r for r in RULES}


def get_rule(rule_id: str) -> Rule:
    return _BY_ID[rule_id]
