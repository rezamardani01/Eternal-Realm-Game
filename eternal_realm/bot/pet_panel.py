"""Companion pets: see yours, pick the active one, buy the coin pets."""

from __future__ import annotations

from ..game.data.items import RARITIES
from ..game.data.pets import PETS, get_pet
from ..shared.text import bold, fa
from .panel import Ctx, Screen, screen


@screen("pets")
async def pets(c: Ctx) -> Screen:
    owned = await c.services.pets.owned(c.player.id)
    lines = [
        f"🐾 {bold('حیوانات همراه')}",
        "",
        "هر حیوان همراه کمی قدرت می‌دهد و فقط یکی می‌تواند هم‌زمان کنارتان باشد.",
        "",
    ]
    rows = []
    for pet in PETS:
        if pet.id in owned:
            mark = " · همراه فعلی" if owned[pet.id] else " · دارید"
        elif pet.price_gold:
            mark = f" · {fa(pet.price_gold)}🪙"
        else:
            mark = " · خزانه‌ی ویژه"
        rows.append([c.btn(f"{pet.emoji} {pet.name}{mark}", "pet", pet.id)])
    if not owned:
        lines.append("هنوز حیوان همراهی ندارید. یکی از ارزان‌ترها را با سکه بگیرید!")
    rows.append(c.back("home"))
    return Screen("\n".join(lines), rows)


@screen("pet")
async def pet(c: Ctx) -> Screen:
    p = get_pet(c.a)
    owned = await c.services.pets.owned(c.player.id)
    icon, rarity = RARITIES[p.rarity]
    lines = [f"{p.emoji} {bold(p.name)}", f"{icon} {rarity}", "", p.story, "", *p.bonus.bonus_lines()]
    rows = []
    if p.id in owned:
        if owned[p.id]:
            lines += ["", "✅ همین حالا همراه شماست."]
        else:
            rows.append([c.btn("🐾 همراه من شود", "petuse", p.id, style="success")])
    elif p.price_gold:
        lines += ["", f"🪙 بها: {bold(fa(p.price_gold))} سکه"]
        rows.append([c.btn(f"🛍️ خرید ({fa(p.price_gold)}🪙)", "petbuyq", p.id, style="success")])
    else:
        lines += ["", "💎 این حیوان همراه در «خزانه‌ی ویژه» (پیام خصوصی ربات) فروخته می‌شود."]
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
        f"🛍️ {bold('تأیید خرید حیوان همراه')}\n\n{p.emoji} {p.name}\n\n"
        f"بها: {bold(fa(p.price_gold))} سکه\n\nکیسه‌ی شما: {fa(me.gold)} ← {fa(me.gold - p.price_gold)} سکه\n\nبخریم؟"
    )
    return Screen(text, [[c.btn("✅ بله، بخر", "petbuy", p.id, style="success"), c.btn("↩️ نه", "pet", p.id)]])


@screen("petbuy")
async def pet_buy(c: Ctx) -> Screen:
    p = await c.services.pets.buy_with_gold(c.player, c.a)
    shown = await pet(c)
    shown.toast, shown.alert = f"🐾 {p.name} به شما پیوست!", True
    return shown


@screen("petuse")
async def pet_use(c: Ctx) -> Screen:
    p = await c.services.pets.activate(c.player, c.a)
    shown = await pet(c)
    shown.toast = f"🐾 {p.name} حالا همراه شماست"
    return shown
