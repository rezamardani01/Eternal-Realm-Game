"""The kinds of private messages the bot sends by itself, and which of them a hero can switch off.

Every queued message has a key (``energyfull:17000``, ``ach:wins:3`` ...); the part before the first colon says which
category it belongs to. A key nobody listed is always delivered (money and safety news cannot be muted).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: str
    emoji: str
    name: str
    about: str


CATEGORIES: tuple[Category, ...] = (
    Category("energy", "⚡", "پر شدن انرژی", "وقتی نوار انرژی کامل شد و قهرمانتان آماده‌ی ماجراجویی است."),
    Category("daily", "🎁", "جایزه‌ی روزانه", "وقتی گنجینه‌ی روزانه‌تان آماده‌ی برداشتن است."),
    Category("city", "🏗️", "دهکده", "پایان ساخت و آموزش سرباز، گرسنگی، پر شدن انبار و پایان سپر."),
    Category("expedition", "🏕️", "برگشتن از اعزام", "وقتی قهرمانتان از اعزام برگشت و پاداشش آماده است."),
    Category("path", "🎟️", "مسیر قهرمانی", "وقتی به مرحله‌ی تازه‌ای رسیدید و جایزه‌اش آماده است."),
    Category("tips", "💡", "پیشنهاد فرمانده", "هر روز یک پیشنهاد کوتاه برای قدم بعدی."),
    Category("news", "🏅", "دستاوردها و اخبار", "دستاورد، فروش در بازار، رویدادهای جهان، لیگ و جنگ خاندان."),
    Category("online", "🌐", "مبارزه‌ی آنلاین", "هشدار «چند ثانیه تا پایان نوبت» و بسته شدن جستجو."),
)
BY_ID = {c.id: c for c in CATEGORIES}

#: key prefix -> category
KEY_CATEGORY = {
    "energyfull": "energy", "dailyready": "daily", "expedition": "expedition", "tip": "tips",
    "ach": "news", "sold": "news", "seller": "news", "world": "news", "popup": "news", "raid": "news", "ladder": "news",
    "cwar": "news", "goal": "news", "friendgift": "news", "friendreq": "news", "friendyes": "news", "clangift": "news",
    "boost_until": "news", "vip_until": "news",
}


def category_of(key: str) -> str | None:
    """The category a queued message belongs to, or ``None`` when it cannot be muted."""
    return KEY_CATEGORY.get(key.partition(":")[0])


def parse(stored: str) -> set[str]:
    """The categories a hero switched off, from the stored comma-separated text."""
    return {c for c in stored.split(",") if c in BY_ID}


def dump(off: set[str]) -> str:
    return ",".join(c.id for c in CATEGORIES if c.id in off)
