"""The card album: sets, single cards, pack opening, duplicates and set rewards."""

from __future__ import annotations

from dataclasses import replace

from ..game.data.cards import PACK_ODDS, PACK_PRICE, PACK_SIZE, RARITY_NAMES, cards_in, dust_value, get_card, get_set
from ..shared.text import bold, fa
from .panel import Ctx, Screen, screen


@screen("album")
async def album(c: Ctx) -> Screen:
    progress = await c.services.cards.progress(c.player.id)
    total = sum(p.owned for p in progress)
    owned = await c.services.cards.owned(c.player.id)
    worth = sum(dust_value(get_card(k)) * q for k, q in owned.items())
    lines = [
        f"🃏 {bold('آلبوم کارت‌ها')}",
        "",
        f"تا الان {bold(fa(total))} کارت جمع کرده‌اید.",
        f"💰 ارزش کل آلبوم: {fa(worth)} سکه",
        "",
    ]
    rows = []
    for p in progress:
        done = " ✔" if p.claimed else (" 🎁" if p.complete else "")
        rows.append([c.btn(f"{p.set.emoji} {p.set.name} · {fa(p.owned)}/{fa(p.total)}{done}", "cset", p.set.id)])
    lines += [
        "کارت‌ها را از شکار هیولا، شکست باس‌ها و بسته‌های کارت به دست می‌آورید.",
        "",
        "هر مجموعه که کامل شود، عنوان و کریستال هدیه دارد.",
        "",
        "کارت‌ها قدرت رزمی ندارند؛ فقط برای شکوه و جمع‌آوری‌اند.",
    ]
    rows.append([c.btn(f"🛍️ بسته‌ی کارت ({fa(PACK_PRICE)}🪙)", "cpackq", style="success")])
    rows.append(c.back("home"))
    return Screen("\n".join(lines), rows)


@screen("cset")
async def card_set(c: Ctx) -> Screen:
    s = get_set(c.a)
    owned = await c.services.cards.owned(c.player.id)
    cards = cards_in(s.id)
    have = sum(1 for k in cards if k.id in owned)
    rows = [
        [c.btn((f"{k.emoji} {k.name} · {fa(dust_value(k))}🪙" if k.id in owned else "❔ ناشناخته") + (f" ×{fa(owned[k.id])}" if owned.get(k.id, 0) > 1 else ""),
               "card", k.id)]
        for k in cards
    ]
    lines = [f"{s.emoji} {bold(s.name)}", "", f"{fa(have)} از {fa(len(cards))} کارت", ""]
    progress = next(p for p in await c.services.cards.progress(c.player.id) if p.set.id == s.id)
    if progress.claimed:
        lines.append(f"🏅 این مجموعه را کامل کرده‌اید و عنوان «{s.title}» را گرفته‌اید.")
    elif progress.complete:
        lines.append(f"🎉 مجموعه کامل شد! عنوان «{s.title}» و {fa(s.crystals)} کریستال منتظر شماست.")
        rows.append([c.btn("🎁 دریافت پاداش مجموعه", "cclaim", s.id, style="success")])
    else:
        lines.append(f"🎁 پاداش کامل شدن: عنوان «{s.title}» و {fa(s.crystals)} کریستال")
    rows.append(c.back("album"))
    return Screen("\n".join(lines), rows)


@screen("card")
async def card(c: Ctx) -> Screen:
    k = get_card(c.a)
    owned = await c.services.cards.owned(c.player.id)
    qty = owned.get(k.id, 0)
    if not qty:
        return Screen(None, toast="❔ این کارت را هنوز پیدا نکرده‌اید.", alert=True)
    lines = [
        f"{k.emoji} {bold(k.name)}",
        RARITY_NAMES[k.rarity],
        "",
        k.story,
        "",
        f"💰 ارزش این کارت: {fa(dust_value(k))} سکه",
        f"در آلبوم شما: {fa(qty)} عدد",
    ]
    rows = []
    if qty > 1:
        lines.append(f"♻️ کارت تکراری را می‌توانید به بازارچه بفروشید: {fa(dust_value(k))} سکه")
        rows.append([c.btn(f"💰 فروش یک تکراری ({fa(dust_value(k))}🪙)", "csellq", k.id)])
    rows.append(c.back("cset", "🔙 بازگشت", k.set_id))
    return Screen("\n".join(lines), rows)


@screen("csellq")
async def card_sell_ask(c: Ctx) -> Screen:
    k = get_card(c.a)
    owned = (await c.services.cards.owned(c.player.id)).get(k.id, 0)
    if owned < 2:
        raise_ = Screen(None, toast="فقط کارت تکراری فروخته می‌شود.", alert=True)
        return raise_
    value = dust_value(k)
    text = (
        f"💰 {bold('تأیید فروش کارت تکراری')}\n\n{k.emoji} {k.name}\n\n"
        f"دریافتی: {bold(fa(value))} سکه\n\nکیسه‌ی شما: {fa(c.player.gold)} ← {fa(c.player.gold + value)} سکه\n\n"
        "یک نسخه از آلبومتان می‌ماند. مطمئنید؟"
    )
    return Screen(text, [[c.btn("✅ بله، بفروش", "csell", k.id, style="danger"), c.btn("↩️ نه", "card", k.id)]])


@screen("csell")
async def card_sell(c: Ctx) -> Screen:
    gold = await c.services.cards.sell_duplicate(c.player, c.a)
    shown = await card(c) if (await c.services.cards.owned(c.player.id)).get(c.a, 0) > 1 else await card_set(
        _with(c, get_card(c.a).set_id)
    )
    shown.toast = f"💰 {fa(gold)} سکه گرفتید"
    return shown


def _with(c: Ctx, a: str) -> Ctx:

    return replace(c, a=a)


@screen("cclaim")
async def claim(c: Ctx) -> Screen:
    s = await c.services.cards.claim_set(c.player, c.a)
    shown = await card_set(c)
    shown.toast, shown.alert = f"🏅 عنوان «{s.title}» و {fa(s.crystals)} کریستال گرفتید!", True
    return shown


@screen("cpackq")
async def pack_ask(c: Ctx) -> Screen:
    p = await c.refresh()
    odds = "\n".join(f"{RARITY_NAMES[r]}: {fa(w)}٪" for r, w in PACK_ODDS.items())
    base = (
        f"🛍️ {bold('بسته‌ی کارت')}\n\n"
        f"هر بسته {fa(PACK_SIZE)} کارت دارد. قیمت: {bold(fa(PACK_PRICE))} سکه\n\n"
        f"شانس هر کارت:\n{odds}\n\n"
        "بسته فقط با سکه‌ی بازی خریداری می‌شود و کارت‌ها قدرت رزمی ندارند.\n\n"
    )
    if p.gold < PACK_PRICE:
        text = base + f"💸 موجودی شما {fa(p.gold)} سکه است؛ {fa(PACK_PRICE - p.gold)} سکه کم دارید."
        return Screen(text, [c.back("album")])
    text = base + f"کیسه‌ی شما: {fa(p.gold)} ← {fa(p.gold - PACK_PRICE)} سکه\n\nبخریم؟"
    return Screen(text, [[c.btn("✅ بله، بخر", "cpack", style="success"), c.btn("↩️ نه", "album")]])


@screen("cpack")
async def pack_open(c: Ctx) -> Screen:
    await c.show(f"🃏 {bold('در حال بازکردن بسته...')}\n\nکارت‌ها یکی‌یکی رو می‌شوند ✨")
    result = await c.services.cards.buy_pack(c.player)
    lines = [f"🃏 {bold('کارت‌های بسته‌ی شما')}", ""]
    for k, new in result.cards:
        lines += [f"{k.emoji} {k.name}" + (" · تازه!" if new else " · تکراری"), f"   {RARITY_NAMES[k.rarity]}", ""]
    rows = [[c.btn("🛍️ بسته‌ی دیگر", "cpackq"), c.btn("🃏 آلبوم", "album")]]
    return Screen("\n".join(lines).strip(), rows)


# --- the card market ---------------------------------------------------------------------------------------
