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
_opener("open_inventory", "inv", ["کوله‌پشتی", "کیف", "کوله", "inventory"], "کوله‌پشتی و تجهیزات", "🎒 کوله‌پشتی")
_opener("open_gear", "gear", ["تجهیزات", "تجهیزات من", "equipment"], "تجهیزات شما", "🎒 کوله‌پشتی")
_opener("open_chests", "chests", ["صندوقچه", "صندوقچه‌ها", "chests"], "صندوقچه‌ها", "🎒 کوله‌پشتی")
_opener("open_shop", "shop", ["فروشگاه", "بازارچه", "shop"], "فروشگاه", "🛒 بازار و فروشگاه")
_opener("open_market", "market", ["بازار", "market"], "بازار بازیکنان", "🛒 بازار و فروشگاه")
_opener("open_premium", "premium", ["فروشگاه ویژه", "بسته‌ها", "premium"], "خزانه‌ی ویژه", "🛒 بازار و فروشگاه")
_opener("open_adventure", "adv", ["ماجراجویی", "adventure"], "همه‌ی فعالیت‌ها یک‌جا", "🌍 فعالیت‌ها")
_opener("open_quests", "quests", ["داستان", "داستان‌ها", "مأموریت", "quests"], "داستان‌های انتخابی با پاداش", "📜 داستان")
_opener("open_album", "album", ["آلبوم", "کارت", "کارت‌ها", "کلکسیون", "album"], "آلبوم کارت‌های جمع‌آوری‌شده", "🃏 کارت")
_opener("rank", "top", ["رتبه", "رتبه گروه", "فعال‌ترین‌ها", "rank"], "رتبه‌ی گروه و تالارها", "🏆 رتبه‌بندی")
