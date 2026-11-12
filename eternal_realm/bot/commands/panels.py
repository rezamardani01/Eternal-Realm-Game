"""Group (and private) words that open a glass-button panel. Everything after that is buttons."""

from __future__ import annotations

from .. import panel
from .context import CommandContext
from .registry import command


def _opener(name: str, screen: str, aliases: list[str], description: str, category: str, **options):  # noqa: ANN202
    async def handler(ctx: CommandContext) -> None:
        await panel.send(ctx.message, ctx.services, ctx.me, screen, reply=True)

    return command(name, aliases, description, category=category, points=0, **options)(handler)


_opener("open_realm", "home", ["قلمرو", "realm"], "منوی اصلی قهرمان با دکمه‌ها", "👤 قهرمان")
_opener("open_inventory", "inv", ["کوله‌پشتی", "کیف", "کوله", "inventory"], "کوله‌پشتی (آیتم‌ها و صندوقچه‌ها)", "🎒 کوله‌پشتی")
_opener("open_gear", "arms", ["تجهیزات", "تجهیزات من", "تجهیزات قهرمان", "equipment"], "تجهیزات جنگی و مهارت‌های قهرمان", "🎒 کوله‌پشتی")
_opener("open_online", "online", ["مبارزه آنلاین", "مبارزه انلاین", "آنلاین", "online"], "جستجوی حریف و مبارزه‌ی آنلاین (پیوی)", "⚔️ نبرد")
_opener("open_chests", "chests", ["صندوقچه", "صندوقچه‌ها", "chests"], "صندوقچه‌ها", "🎒 کوله‌پشتی")
_opener("open_shop", "shop", ["فروشگاه", "shop"], "فروشگاه", "🛒 بازار و فروشگاه")
_opener("open_market", "market", ["بازار", "بازارچه", "market"], "بازار بازیکنان", "🛒 بازار و فروشگاه")
_opener("open_premium", "premium", ["فروشگاه ویژه", "خزانه قلمرو", "خزانه", "بسته‌ها", "premium"], "خزانه قلمرو", "🛒 بازار و فروشگاه")
_opener("open_adventure", "adv", ["ماجراجویی", "adventure"], "همه‌ی فعالیت‌ها یک‌جا", "🌍 فعالیت‌ها")
_opener("open_quests", "quests", ["داستان", "داستان‌ها", "مأموریت", "quests"], "داستان‌های انتخابی با پاداش", "📜 داستان")
_opener("open_album", "album", ["آلبوم", "کارت", "کارت‌ها", "کلکسیون", "album"], "آلبوم کارت‌های جمع‌آوری‌شده", "🃏 کارت")
_opener("open_pets", "pets", ["حیوان", "حیوان خانگی", "حیوان همراه", "پت", "pets"], "حیوانات خانگی شما", "🐱 حیوان خانگی")
_opener("open_dungeon", "dungeon", ["سیاه‌چال", "سیاهچال", "dungeon"], "سیاه‌چال پنج‌اتاقه با نگهبان", "🕳️ سیاه‌چال")
_opener("open_offers", "offers", ["پیشنهادها", "پیشنهاد", "offers"], "روشن و خاموش کردن پیشنهادهای شخصی", "✉️ پیشنهاد")
_opener("open_missions", "missions", ["مأموریت‌ها", "ماموریت‌ها", "مأموریت‌های امروز", "ماموریت‌های امروز", "ماموریت روزانه", "missions"], "مأموریت‌های شخصی امروز", "📅 مأموریت")
_opener("open_contests", "contests", ["مسابقه", "مسابقه‌ها", "مسابقات", "contests"], "مسابقه‌های هفتگی", "🏁 مسابقه")
_opener("open_altar", "altar", ["محراب", "برکت", "نفرین", "altar"], "محراب: دعا برای برکت (یا نفرین)", "🕯️ محراب")
_opener("rank", "top", ["رتبه", "رتبه گروه", "فعال‌ترین‌ها", "rank"], "رتبه‌ی گروه و تالارها", "🏆 رتبه‌بندی")
