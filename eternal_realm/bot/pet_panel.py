"""Companion pets: see yours, pick the active one, buy the coin pets."""

from __future__ import annotations

from ..game.data.items import RARITIES
from ..game.data.pets import MAX_PET_LEVEL, PETS, bonus_at, get_pet, upgrade_cost
from ..shared.text import bold, fa
from .panel import Ctx, Screen, screen


@screen("pets")
async def pets(c: Ctx) -> Screen:
    owned = await c.services.pets.owned(c.player.id)
    levels = await c.services.pets.levels(c.player.id)
    lines = [
        f"🐱 {bold('حیوانات خانگی')}",
        "",
        "هر حیوان خانگی کمی قدرت می‌دهد و فقط یکی می‌تواند هم‌زمان کنارتان باشد.",
        "",
    ]
    rows = []
    for pet in PETS:
        if pet.id in owned:
            tag = ("✅ همراه من" if owned[pet.id] else "🐾 دارید") + f" · سطح {fa(levels[pet.id])}"
        elif pet.price_gold:
            tag = f"🪙 {fa(pet.price_gold)}"
        else:
            tag = "💎 خزانه قلمرو"
        rows.append([c.btn(f"{pet.emoji} {pet.name}", "pet", pet.id), c.btn(tag, "pet", pet.id)])  # name, then its price or state
    if not owned:
        lines.append("هنوز حیوان خانگی ندارید. یکی از ارزان‌ترها را با سکه بگیرید!")
    rows.append(c.back("home"))
    return Screen("\n".join(lines), rows)


@screen("pet")
async def pet(c: Ctx) -> Screen:
    p = get_pet(c.a)
    owned = await c.services.pets.owned(c.player.id)
    level = (await c.services.pets.levels(c.player.id)).get(p.id, 1)
    icon, rarity = RARITIES[p.rarity]
    lines = [f"{p.emoji} {bold(p.name)}", f"{icon} {rarity}", "", p.story, "", *bonus_at(p, level).bonus_lines()]
    rows = []
    if p.id in owned:
        lines += ["", f"⭐ سطح {fa(level)} از {fa(MAX_PET_LEVEL)}"]
        lines.append("در دوئل و شکار گاهی همراه شما حمله می‌کند.")
        if owned[p.id]:
            lines += ["", "✅ همین حالا همراه شماست."]
        else:
            rows.append([c.btn("🐱 همراه من شود", "petuse", p.id, style="success")])
        if level < MAX_PET_LEVEL:
            rows.append([c.btn(f"⬆️ ارتقا ({fa(upgrade_cost(level))}💎)", "petupq", p.id)])
    elif p.price_gold:
        lines += ["", f"🪙 بها: {bold(fa(p.price_gold))} سکه"]
        rows.append([c.btn(f"🛍️ خرید ({fa(p.price_gold)}🪙)", "petbuyq", p.id, style="success")])
    else:
        lines += ["", "💎 این حیوان خانگی در «خزانه قلمرو» (پیام خصوصی ربات) فروخته می‌شود."]
    rows.append(c.back("pets"))
    return Screen("\n".join(lines), rows)


@screen("petbuyq")
async def pet_buy_ask(c: Ctx) -> Screen:
    p = get_pet(c.a)
    me = await c.refresh()
    if me.gold < p.price_gold:
        text = (
            f"💸 {bold('موجودی کافی نیست')}\n\n{p.emoji} {p.name}\nبها: {fa(p.price_gold)} 🪙\n"
            f"موجودی شما: {fa(me.gold)} 🪙\nکمبود: {bold(fa(p.price_gold - me.gold))} 🪙"
        )
        return Screen(text, [c.back("pet", "🔙 بازگشت", p.id)])
    text = (
        f"🛍️ {bold('تأیید خرید حیوان خانگی')}\n\n{p.emoji} {p.name}\n\n"
        f"بها: {bold(fa(p.price_gold))} سکه\n\nکیسه‌ی شما: {fa(me.gold)} ← {fa(me.gold - p.price_gold)} سکه\n\nبخریم؟"
    )
    return Screen(text, [[c.btn("✅ بله، بخر", "petbuy", p.id, style="success"), c.btn("↩️ نه", "pet", p.id)]])


@screen("petbuy")
async def pet_buy(c: Ctx) -> Screen:
    p = await c.services.pets.buy_with_gold(c.player, c.a)
    shown = await pet(c)
    shown.toast, shown.alert = f"🐱 {p.name} به شما پیوست!", True
    return shown


@screen("petupq")
async def pet_up_ask(c: Ctx) -> Screen:
    p = get_pet(c.a)
    level = (await c.services.pets.levels(c.player.id)).get(p.id)
    if level is None:
        raise_screen = Screen(None, toast="این حیوان خانگی مال شما نیست.", alert=True)
        return raise_screen
    me = await c.refresh()
    cost = upgrade_cost(level)
    gain = "\n".join(bonus_at(p, level + 1).bonus_lines())
    if me.crystal < cost:
        text = (
            f"💸 {bold('کریستال کافی نیست')}\n\nارتقای {p.emoji} {p.name} به سطح {fa(level + 1)}\n"
            f"هزینه: {fa(cost)} 💎\nموجودی شما: {fa(me.crystal)} 💎\nکمبود: {bold(fa(cost - me.crystal))} 💎"
        )
        return Screen(text, [c.back("pet", "🔙 بازگشت", p.id)])
    text = (
        f"⬆️ {bold('تأیید ارتقای حیوان خانگی')}\n\n{p.emoji} {p.name}\nسطح {fa(level)} ← سطح {fa(level + 1)}\n\n"
        f"بعد از ارتقا:\n{gain}\n\nهزینه: {bold(fa(cost))} کریستال\n"
        f"کریستال شما: {fa(me.crystal)} ← {fa(me.crystal - cost)}\n\nارتقا بدهیم؟"
    )
    return Screen(text, [[c.btn("✅ بله، ارتقا", "petup", p.id, style="success"), c.btn("↩️ نه", "pet", p.id)]])


@screen("petup")
async def pet_up(c: Ctx) -> Screen:
    p, level = await c.services.pets.upgrade(c.player, c.a)
    shown = await pet(c)
    shown.toast, shown.alert = f"⬆️ {p.name} به سطح {fa(level)} رسید!", True
    return shown


@screen("petuse")
async def pet_use(c: Ctx) -> Screen:
    p = await c.services.pets.activate(c.player, c.a)
    shown = await pet(c)
    shown.toast = f"🐱 {p.name} حالا همراه شماست"
    return shown
