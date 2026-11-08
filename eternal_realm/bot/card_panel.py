"""The card album: sets, single cards, pack opening, duplicates and set rewards."""

from __future__ import annotations

from dataclasses import replace

from ..game.data.cards import PACK_ODDS, PACK_PRICE, PACK_SIZE, RARITY_NAMES, cards_in, dust_value, get_card, get_set
from ..shared.text import bold, fa
from .panel import Ctx, Screen, _int, screen


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
        rows.append([c.btn("🏷️ فروش در بازار کارت", "cplist", k.id, str(dust_value(k) * 2))])
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
    from dataclasses import replace

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
@screen("cmarket")
async def card_market(c: Ctx) -> Screen:
    page, rarity = max(0, _int(c.a or "0")), _int(c.b or "0")
    found, nxt = await c.services.cards.market_page(rarity, page, 6)
    label = "همه" if rarity == 0 else RARITY_NAMES[rarity].split(" ", 1)[1]
    rows = [[c.btn(f"🔎 فیلتر کمیابی: {label}", "cfilter", "0", rarity)]]
    if not found:
        rows.append([c.btn("🚫 هیچ کارتی برای خرید وجود ندارد", "cmarket", "0", rarity)])
    for lst in found:
        rows.append([c.btn(f"{lst.card.emoji} {lst.card.name} — {fa(lst.price)}🪙", "cmlist", lst.id)])
    nav = ([c.btn("‹ قبلی", "cmarket", page - 1, rarity)] if page else []) + (
        [c.btn("بعدی ›", "cmarket", page + 1, rarity)] if nxt else []
    )
    if nav:
        rows.append(nav)
    rows.append([c.btn("📋 آگهی‌های من", "cmine")])
    rows.append(c.back("market"))
    text = (
        f"🏪 {bold('بازار کارت')}\n\n"
        "کارت‌های تکراری بازیکنان، از ارزان به گران. خرید و فروش فقط با سکه است.\n\n"
        f"کارمزد فروش: {fa(5)}٪"
    )
    return Screen(text, rows)


@screen("cfilter")
async def card_filter(c: Ctx) -> Screen:
    current = _int(c.b or "0")
    rows = []
    for key, label in {0: "🧺 همه", **{r: n for r, n in RARITY_NAMES.items()}}.items():
        mark = "✅ " if key == current else "⬜ "
        rows.append([c.btn(mark + label.split(" ", 1)[1], "cfilter", "0", key)])
    rows.append([c.btn("🏪 نمایش کارت‌ها", "cmarket", "0", current, style="primary")])
    return Screen(f"🔎 {bold('فیلتر کمیابی')}\n\nکمیابی دلخواه را تیک بزنید، بعد «نمایش کارت‌ها».", rows)


@screen("cmlist")
async def card_listing(c: Ctx) -> Screen:
    lst = await c.services.cards.listing(_int(c.a))
    if lst is None:
        shown = await card_market(replace(c, a="0", b="0"))
        shown.toast = "این آگهی دیگر نیست"
        return shown
    lines = [
        f"{lst.card.emoji} {bold(lst.card.name)}",
        RARITY_NAMES[lst.card.rarity],
        "",
        lst.card.story,
        "",
        f"💰 بها: {bold(fa(lst.price))} سکه",
        f"👤 فروشنده: {lst.seller}",
    ]
    own = lst.seller_id == c.player.id
    rows = [[c.btn("↩️ لغو آگهی", "cmcancel", lst.id, style="danger")]] if own else [
        [c.btn(f"🛍️ خرید با {fa(lst.price)}🪙", "cmbuyq", lst.id, style="success")]
    ]
    rows.append(c.back("cmarket", "🔙 بازگشت", "0"))
    return Screen("\n".join(lines), rows)


@screen("cmbuyq")
async def card_buy_ask(c: Ctx) -> Screen:
    lst = await c.services.cards.listing(_int(c.a))
    if lst is None:
        return Screen(None, toast="این آگهی دیگر نیست", alert=True)
    p = await c.refresh()
    if p.gold < lst.price:
        text = (
            f"💸 {bold('موجودی کافی نیست')}\n\n{lst.card.emoji} {lst.card.name}\nبها: {fa(lst.price)} 🪙\n"
            f"موجودی شما: {fa(p.gold)} 🪙\nکمبود: {bold(fa(lst.price - p.gold))} 🪙"
        )
        return Screen(text, [c.back("cmlist", "🔙 بازگشت", lst.id)])
    text = (
        f"🛍️ {bold('تأیید خرید کارت')}\n\n{lst.card.emoji} {lst.card.name}\n{RARITY_NAMES[lst.card.rarity]}\n\n"
        f"بها: {bold(fa(lst.price))} سکه\nفروشنده: {lst.seller}\n\n"
        f"کیسه‌ی شما: {fa(p.gold)} ← {fa(p.gold - lst.price)} سکه\n\nبخریم؟"
    )
    return Screen(text, [[c.btn("✅ بله، بخر", "cmbuy", lst.id, style="success"), c.btn("↩️ نه", "cmlist", lst.id)]])


@screen("cmbuy")
async def card_buy(c: Ctx) -> Screen:
    lst = await c.services.cards.buy_card(c.player, _int(c.a))
    shown = await card_market(replace(c, a="0", b="0"))
    shown.toast, shown.alert = f"🃏 {lst.card.name} به آلبوم شما اضافه شد!", True
    return shown


@screen("cmine")
async def card_mine(c: Ctx) -> Screen:
    mine = await c.services.cards.my_listings(c.player.id)
    rows = [[c.btn(f"{x.card.emoji} {x.card.name} — {fa(x.price)}🪙", "cmlist", x.id)] for x in mine]
    rows.append(c.back("cmarket", "🔙 بازگشت", "0"))
    return Screen(f"📋 {bold('آگهی‌های کارت من')}\n\n" + ("یکی را بزنید تا لغو کنید 👇" if mine else "آگهی فعالی ندارید."), rows)


@screen("cmcancel")
async def card_cancel(c: Ctx) -> Screen:
    lst = await c.services.cards.cancel_listing(c.player, _int(c.a))
    shown = await card_mine(c)
    shown.toast = f"↩️ {lst.card.name} به آلبوم برگشت"
    return shown


@screen("cplist")
async def card_price(c: Ctx) -> Screen:
    k = get_card(c.a)
    price = max(50, min(5_000_000, _int(c.b or "100")))

    def step(delta: int):  # noqa: ANN202
        return c.btn(f"{'+' if delta > 0 else '-'}{fa(abs(delta))}", "cplist", k.id, max(50, min(5_000_000, price + delta)))

    rows = [
        [step(-1000), step(-100), step(100), step(1000)],
        [step(-10_000), step(10_000)],
        [c.btn(f"✅ تأیید قیمت ({fa(price)})", "cplistq", k.id, price, style="success")],
        c.back("card", "🔙 بازگشت", k.id),
    ]
    text = (
        f"🏷️ {bold('قیمت فروش کارت')}\n\n{k.emoji} {k.name}\n\n"
        f"قیمت انتخابی: {bold(fa(price))} سکه\n\n"
        "با دکمه‌ها قیمت را کم و زیاد کنید، بعد دکمه‌ی سبز را بزنید 👇"
    )
    return Screen(text, rows)


@screen("cplistq")
async def card_list_ask(c: Ctx) -> Screen:
    k, price = get_card(c.a), _int(c.b)
    fee = price * 5 // 100
    text = (
        f"🏷️ {bold('تأیید آگهی کارت')}\n\n{k.emoji} {k.name}\n\nقیمت: {bold(fa(price))} سکه\n\n"
        f"کارمزد بازار: {fa(fee)} سکه\nدریافتی شما پس از فروش: {bold(fa(price - fee))} سکه\n\nثبت شود؟"
    )
    return Screen(text, [[c.btn("✅ ثبت آگهی", "cplistdo", k.id, price, style="success"), c.btn("❌ انصراف", "card", k.id)]])


@screen("cplistdo")
async def card_list_do(c: Ctx) -> Screen:
    lst = await c.services.cards.list_card(c.player, c.a, _int(c.b))
    text = f"🏷️ {bold('آگهی کارت نصب شد')}\n\n{lst.card.emoji} {lst.card.name} — {fa(lst.price)} سکه\n\nهمه‌ی بازیکنان در بازار کارت می‌بینندش."
    return Screen(text, [[c.btn("🏪 بازار کارت", "cmarket", "0", "0"), c.btn("🃏 آلبوم", "album")]])
