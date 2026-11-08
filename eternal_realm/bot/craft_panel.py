"""The forge screens: pick a recipe, see what is missing, confirm, craft."""

from __future__ import annotations

from ..game.data.recipes import RECIPES
from ..game.data.items import get_item
from ..game.services.crafting import CraftView
from ..shared.text import bold, fa
from .panel import Ctx, Screen, screen


@screen("craft")
async def craft(c: Ctx) -> Screen:
    rows = []
    for r in RECIPES:
        item = get_item(r.result)
        rows.append([c.btn(f"{item.label} · {item.rarity_label.split(' ')[1]}", "craftq", r.id)])
    rows.append(c.back("home"))
    text = (
        f"🔥 {bold('کوره‌ی آهنگری')}\n\n"
        "یک تجهیزات ساده را با مواد کمیاب ترکیب کنید و تجهیزات افسانه‌ای بسازید. "
        "تجهیزاتی که برای ساختن می‌دهید از بین می‌رود.\n\n"
        "یک نقشه را انتخاب کنید 👇"
    )
    return Screen(text, rows)


def _needs(v: CraftView) -> list[str]:
    lines = []
    if v.base is not None:
        mark = "✅" if v.base.ok else "❌"
        lines.append(f"{mark} {v.base.item.label} (آزاد)")
    for n in v.materials:
        mark = "✅" if n.ok else "❌"
        lines.append(f"{mark} {n.item.label}: {fa(n.have)} از {fa(n.need)}")
    mark = "✅" if v.gold_have >= v.recipe.gold else "❌"
    lines.append(f"{mark} سکه: {fa(v.gold_have)} از {fa(v.recipe.gold)}")
    return lines


@screen("craftq")
async def craft_ask(c: Ctx) -> Screen:
    v = await c.services.crafting.view(c.player, c.a)
    lines = [f"{v.result.emoji} {bold(v.result.name)}", v.result.rarity_label, "", *v.result.stats.bonus_lines(), ""]
    if v.already_owned:
        lines.append("✅ این تجهیزات را از قبل دارید؛ ساختن دوباره لازم نیست.")
        return Screen("\n".join(lines), [c.back("craft")])
    lines += [f"{bold('نیازمندی‌ها')}", *_needs(v), ""]
    if v.ready:
        lines.append("همه‌چیز آماده است. بسازیم؟")
        rows = [[c.btn("🔥 بله، بساز", "craftdo", v.recipe.id, style="success"), c.btn("↩️ نه", "craft")]]
    else:
        lines.append("هنوز همه‌ی نیازمندی‌ها را ندارید. مواد را از ماجراجویی، شکار و باس‌ها جمع کنید.")
        rows = [c.back("craft")]
    return Screen("\n".join(lines), rows)


@screen("craftdo")
async def craft_do(c: Ctx) -> Screen:
    await c.show(f"🔥 {bold('کوره روشن شد')}\n\nفلز سرخ می‌شود و پتک بر سندان می‌کوبد...")
    made = await c.services.crafting.craft(c.player, c.a)
    text = (
        f"🔨 {bold('ساخته شد!')}\n\n{made.label}\n{made.rarity_label}\n\n"
        + "\n".join(made.stats.bonus_lines())
        + "\n\nاز «تجهیزات» می‌توانید بپوشیدش."
    )
    return Screen(text, [[c.btn("🧰 تجهیزات", "gear"), c.btn("🔥 کوره", "craft")]], toast="🔨 ساخته شد!")
