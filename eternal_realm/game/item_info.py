"""What an item is for and where it comes from, worked out from the game's own tables (so it never goes stale).

``uses(item)`` and ``sources(item)`` return short Persian lines, one emoji each, ready for an item screen.
"""

from __future__ import annotations

from functools import lru_cache

from ..shared.text import fa
from .data.activities import ACTIVITIES
from .data.chests import CHESTS
from .data.items import ITEMS, Item, Kind, get_item
from .data.lucky import THEMES
from .data.monsters import MONSTERS
from .data.packs import PACKS
from .data.quests import QUESTS
from .data.recipes import RECIPES
from .data.sets import BOSS_DROPS
from .data.world_events import METEOR_LOOT

#: things no table can say
SPECIAL_USES = {
    "rename_ticket": "🏷️ تغییر نام قهرمان؛ از «قهرمان من ← ارتقای قهرمان ← خدمات»",
    "race_ticket": "🧬 تغییر نژاد قهرمان؛ از «قهرمان من ← ارتقای قهرمان ← خدمات»",
    "class_ticket": "⚔️ تغییر کلاس قهرمان؛ از «قهرمان من ← ارتقای قهرمان ← خدمات»",
}
#: the forge and the smithy are the same for every piece of gear
UPGRADE_LINE = "⬆️ ارتقای تجهیزات در آهنگری"
UPGRADE_MATERIALS = {"iron_ore": "از +۱", "crystal_shard": "از +۶"}
SLOT_NAMES = {
    "weapon": "سلاح", "armor": "زره", "helmet": "کلاه‌خود", "shield": "سپر", "boots": "چکمه", "ring": "انگشتر",
    "amulet": "گردنبند",
}


def _names(ids: list[str], limit: int = 4) -> str:
    shown = [get_item(i).name for i in ids[:limit]]
    more = f" و {fa(len(ids) - limit)} مورد دیگر" if len(ids) > limit else ""
    return "، ".join(shown) + more


@lru_cache(maxsize=None)
def sources(item_id: str) -> tuple[str, ...]:
    """Where the item can be found, one short line per kind of source."""
    item = ITEMS[item_id]
    lines: list[str] = []
    activities = [a.title for a in ACTIVITIES.values() if any(d.item_id == item_id for o in a.outcomes for d in o.drops)]
    if activities:
        lines.append("🌍 ماجراجویی: " + "، ".join(activities))
    monsters = [m.name for m in MONSTERS if any(d.item_id == item_id for d in m.drops)]
    if monsters:
        lines.append("🐺 شکار: " + "، ".join(monsters))
    chests = [get_item(c.item_id).name for c in CHESTS.values() if any(p.item_id == item_id for p in c.prizes)]
    if chests:
        lines.append("🎁 صندوقچه: " + "، ".join(chests))
    if any(i == item_id for i, _ in BOSS_DROPS):
        lines.append("🐉 غنیمت باس‌های گروهی")
    if item.buy > 0 and item.kind is not Kind.CHEST:
        lines.append(f"🛒 فروشگاه: {fa(item.buy)} سکه")
    crafted = [r for r in RECIPES if r.result == item_id]
    if crafted:
        lines.append("🔥 ساخت در کوره")
    if any(item_id in pack.items for pack in PACKS.values()):
        lines.append("💎 خزانه قلمرو")
    if any(p.item_id == item_id for t in THEMES for p in t.prizes):
        lines.append("🎲 بسته‌ی شانسی خزانه قلمرو")
    from .services.events import MERCHANT_STOCK

    if any(i == item_id for i, _ in MERCHANT_STOCK):
        lines.append("🧳 تاجر دوره‌گرد")
    if any(i == item_id for i, _ in METEOR_LOOT):
        lines.append("☄️ شهاب‌سنگ (رویداد گروه)")
    if any(item_id == i for q in QUESTS for s in q.steps.values() if s.reward for i, _ in s.reward.items):
        lines.append("📜 پاداش داستان‌ها")
    return tuple(lines[:6]) or ("🎁 رویدادها و غنیمت‌های ویژه",)


@lru_cache(maxsize=None)
def uses(item_id: str) -> tuple[str, ...]:
    """What the item is good for."""
    item = ITEMS[item_id]
    lines: list[str] = []
    if item_id in SPECIAL_USES:
        lines.append(SPECIAL_USES[item_id])
    if item.kind is Kind.CONSUMABLE:
        lines.append(f"🧪 با نوشیدنش {fa(item.energy)} انرژی برمی‌گردد")
    if item.is_gear:
        slot = SLOT_NAMES.get(item.slot or "", "تجهیزات")
        lines.append(f"🛡️ جایگاه: {slot} · سطح لازم {fa(item.level_req)}")
        lines.append(UPGRADE_LINE + " (تا +۱۰)")
        made = [get_item(r.result).name for r in RECIPES if r.base == item_id]
        if made:
            lines.append("🔥 پایه‌ی ساخت در کوره: " + "، ".join(made))
    if item.kind is Kind.CHEST:
        lines.append("🗝️ باز کردنش سکه، منابع یا تجهیزات می‌دهد؛ «شانس‌ها» را ببینید")
    if item_id in UPGRADE_MATERIALS:
        lines.append(f"{UPGRADE_LINE} ({UPGRADE_MATERIALS[item_id]})")
    forged = [get_item(r.result).name for r in RECIPES if item_id in r.materials]
    if forged:
        lines.append("🔥 ساخت در کوره: " + "، ".join(forged))
    if item.sell > 0:
        lines.append(f"💰 فروش به بازارچه: {fa(item.sell)} سکه")
    if item.tradable:
        lines.append("🏷️ قابل فروش در بازار به بازیکنان دیگر")
    else:
        lines.append("🔒 قابل فروش به بازیکنان دیگر نیست")
    return tuple(lines)


def info_lines(item: Item) -> list[str]:
    """The «کاربرد» and «از کجا» blocks for an item screen."""
    out = ["", "📖 *کاربرد*", *uses(item.id), "", "📍 *از کجا به دست می‌آید؟*", *sources(item.id)]
    return out
