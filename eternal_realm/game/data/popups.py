"""Small happenings the bot sends a hero in the private chat by itself: a decision with a few hours to make it.

A choice's result is written like the road events of the trip: ``gold`` / ``xp`` as (low, high), ``item`` as (id, qty),
``crystal``, ``pay`` (coins asked first), ``text``, or ``{"chance": p, "win": {...}, "lose": {...}}`` (nestable).
"""

from __future__ import annotations

from dataclasses import dataclass

#: the gold and experience of a result are multiplied by this (these are small gifts, not an income)
SHARE = 0.6
#: at most one a day per hero, only between these hours (Tehran)
HOURS = (9, 22)
MIN_LEVEL = 3
GAP_HOURS = 20
MAX_PER_SWEEP = 40


@dataclass(frozen=True)
class Choice:
    label: str
    result: dict


@dataclass(frozen=True)
class Popup:
    id: str
    emoji: str
    title: str
    #: the message that arrives
    text: str
    ttl_hours: int
    choices: tuple[Choice, ...]
    weight: int = 10


POPUPS: tuple[Popup, ...] = (
    Popup("thief", "🥷", "دزد از کیفتان فرار کرد!", "کسی از میان جمعیت کیسه‌ی کوچکی از کمرتان کند و پا به فرار گذاشت. هنوز دیده می‌شود!", 2, (
        Choice("🏃 دنبالش می‌دوم", {"chance": 0.6, "win": {"gold": (120, 260), "text": "گیرش انداختید و کیسه را پس گرفتید، با کمی غرامت!"}, "lose": {"xp": (15, 35), "text": "در کوچه‌ها گمش کردید، اما ورزش خوبی شد."}}),
        Choice("🤷 بگذار برود", {"xp": (20, 45), "text": "شانه بالا انداختید؛ چیز مهمی در آن کیسه نبود."}),
    )),
    Popup("mystery_box", "🎁", "جعبه‌ی ناشناس", "جعبه‌ای درخشان بی‌صاحب کنار دروازه مانده است. می‌گویند فقط چند ساعت می‌ماند!", 3, (
        Choice("🔓 بازش می‌کنم", {"chance": 0.5, "win": {"chance": 0.5, "win": {"gold": (200, 420), "text": "جعبه پر از سکه بود!"}, "lose": {"item": ("wooden_chest", 1), "text": "یک صندوقچه‌ی چوبی درونش بود!"}}, "lose": {"chance": 0.5, "win": {"crystal": 2, "text": "دو کریستال ناب درونش برق می‌زد!"}, "lose": {"item": ("energy_potion", 2), "text": "دو معجون انرژی درونش بود."}}}),
    ), 14),
    Popup("old_map", "🗺️", "نقشه‌ی گنج", "پیرمردی نقشه‌ای کهنه به دست شما داد و گفت: «من پیرتر از آنم که دنبالش بروم.»", 6, (
        Choice("🧭 دنبال نقشه می‌روم", {"chance": 0.55, "win": {"gold": (180, 360), "item": ("wooden_chest", 1), "text": "گنج پیدا شد؛ صندوقچه‌ای زیر خاک بود!"}, "lose": {"xp": (30, 60), "text": "نقشه کهنه بود و گنج دیگر آنجا نبود."}}),
        Choice("💰 نقشه را می‌فروشم", {"gold": (90, 170), "text": "نقشه را به کلکسیونری فروختید."}),
    )),
    Popup("lost_pet", "🐕", "سگ گمشده", "سگی با قلاده‌ی طلایی دنبال شما راه افتاده و دمش را تکان می‌دهد.", 4, (
        Choice("🏠 به صاحبش برمی‌گردانم", {"gold": (100, 220), "xp": (30, 60), "text": "صاحبش از خوشحالی گریه کرد و پاداش داد."}),
        Choice("🍖 غذایش می‌دهم و می‌روم", {"xp": (35, 70), "text": "سگ سیر شد و با دم‌جنبانی بدرقه‌تان کرد."}),
    )),
    Popup("festival", "🎪", "جشن شبانه‌ی روستا", "روستایی نزدیک جشن گرفته؛ آتش، موسیقی و بازی. دعوتتان کرده‌اند.", 5, (
        Choice("💃 به جشن می‌روم", {"xp": (60, 120), "gold": (40, 100), "text": "تا صبح رقصیدید و کیسه‌تان هم سنگین شد."}),
        Choice("🎯 در مسابقه‌ی تیراندازی شرکت می‌کنم", {"chance": 0.5, "win": {"gold": (150, 300), "text": "نشانه را زدید و جایزه گرفتید!"}, "lose": {"xp": (20, 45), "text": "تیرتان به خطا رفت، اما همه کف زدند."}}),
    )),
    Popup("whisper", "🕯️", "زمزمه‌ی محراب", "از محرابی دور صدایی نجوا می‌کند: «نذری بیاور تا بختت باز شود.»", 4, (
        Choice("🪙 نذر می‌کنم (۶۰ سکه)", {"pay": 60, "chance": 0.7, "win": {"crystal": 1, "xp": (60, 110), "text": "نوری گرم بر شما نشست؛ بختتان باز شد."}, "lose": {"xp": (20, 40), "text": "محراب خاموش ماند، اما دلتان آرام گرفت."}}),
        Choice("🙏 فقط دعا می‌کنم", {"xp": (25, 50), "text": "دعایتان را خواندید و سبک‌تر شدید."}),
    )),
    Popup("caravan", "🐪", "کاروان تاجران", "کاروانی از راه رسیده و تاجرش می‌گوید: «یکی از مال‌هایم را ارزان می‌دهم، فقط امروز!»", 3, (
        Choice("🛒 می‌خرم (۱۵۰ سکه)", {"pay": 150, "chance": 0.75, "win": {"item": ("big_energy_potion", 1), "gold": (60, 120), "text": "کالای خوبی بود؛ یک معجون بزرگ هم پیدا شد."}, "lose": {"text": "کالا سفالی بیش نبود؛ فریب خوردید."}}),
        Choice("🙅 نمی‌خرم", {"text": "تاجر شانه بالا انداخت و کاروانش رفت."}),
    ), 8),
    Popup("hourly_wheel", "🎡", "چرخ ساعتی", "چرخ شانس کوچکی وسط میدان چرخیده و فقط یک ساعت می‌ماند.", 1, (
        Choice("🎡 می‌چرخانم", {"chance": 0.4, "win": {"gold": (80, 200), "text": "سکه‌ها ریخت!"}, "lose": {"chance": 0.5, "win": {"xp": (60, 120), "text": "تجربه‌ی خوبی نصیبتان شد."}, "lose": {"item": ("small_energy_potion", 2), "text": "دو معجون کوچک انرژی برنده شدید."}}}),
    ), 8),
    Popup("storm", "⛈️", "توفان در راه", "ابرها سیاه شده‌اند. می‌توانید پناه بگیرید یا از توفان برای گرفتن نیرو استفاده کنید.", 3, (
        Choice("🏠 پناه می‌گیرم", {"xp": (20, 40), "text": "در کلبه‌ای نشستید و توفان گذشت."}),
        Choice("⚡ زیر توفان تمرین می‌کنم", {"chance": 0.55, "win": {"xp": (110, 200), "text": "رعد و برق شما را آبدیده کرد!"}, "lose": {"text": "توفان شما را شست و برد، اما سالم ماندید."}}),
    )),
    Popup("bard", "🪕", "نوازنده‌ی دوره‌گرد", "نوازنده‌ای کنار آتش داستان قهرمانان را می‌خواند و کلاهش را پیش می‌آورد.", 4, (
        Choice("🪙 سکه می‌اندازم (۳۰ سکه)", {"pay": 30, "xp": (70, 130), "text": "آوازش جانی تازه به شما داد."}),
        Choice("🎶 همخوانی می‌کنم", {"chance": 0.5, "win": {"gold": (70, 150), "xp": (30, 60), "text": "جمعیت دست زد و سهمی هم به شما رسید."}, "lose": {"text": "صدایتان خشن بود؛ همه خندیدند."}}),
    )),
)
_BY_ID = {p.id: p for p in POPUPS}


def get_popup(popup_id: str) -> Popup:
    return _BY_ID[popup_id]
