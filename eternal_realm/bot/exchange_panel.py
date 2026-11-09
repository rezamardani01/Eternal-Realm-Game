"""The exchange centre (مرکز مبادله): turn gold into crystals and crystals into gold."""

from __future__ import annotations

from ..game.services.exchange import STEPS
from ..shared.errors import GameError
from ..shared.text import bold, fa
from . import keyboards
from .panel import Ctx, Screen, _int, screen


@screen("exch")
async def exchange(c: Ctx) -> Screen:
    ex = c.services.exchange
    p = await c.refresh()
    text = "\n".join([
        f"💱 {bold('مرکز مبادله')}",
        "",
        "اینجا سکه و کریستال را با هم عوض می‌کنید.",
        "",
        f"📈 نرخ پایه: هر کریستال = {fa(ex.rate)} سکه",
        f"🧾 کارمزد: {fa(ex.fee_percent)}٪ از هر مبادله (به خزانه‌ی ربات می‌رود)",
        "",
        f"🛒 خرید هر کریستال: {fa(ex.buy_quote(1).gold)} سکه",
        f"💰 فروش هر کریستال: {fa(ex.sell_quote(1).gold)} سکه",
        "",
        f"👛 کیف شما: {fa(p.gold)} سکه · {fa(p.crystal)} کریستال",
        "",
        "کدام را می‌خواهید؟ 👇",
    ])
    rows = [
        [c.btn("🪙 تبدیل سکه به کریستال", "exchbuy", style="primary")],
        [c.btn("💎 تبدیل کریستال به سکه", "exchsell", style="success")],
        c.back("home"),
    ]
    return Screen(text, rows)


@screen("exchbuy")
async def exchange_buy(c: Ctx) -> Screen:
    ex = c.services.exchange
    p = await c.refresh()
    left = await ex.left_today(p.id)
    text = "\n".join([
        f"🪙 {bold('تبدیل سکه به کریستال')}",
        "",
        f"🛒 هر کریستال {fa(ex.buy_quote(1).gold)} سکه (کارمزد داخلش است)",
        f"📅 تا پایان این شبانه‌روز می‌توانید {fa(left)} کریستال دیگر بخرید",
        "",
        f"👛 کیف شما: {fa(p.gold)} سکه",
        "",
        "چند کریستال می‌خواهید؟ 👇",
    ])
    buttons = [
        c.btn(f"💎 {fa(n)} · {fa(ex.buy_quote(n).gold)} سکه", "exchbuyq", n,
              style="success" if p.gold >= ex.buy_quote(n).gold and n <= left else None)
        for n in STEPS
    ]
    rows = keyboards.grid(buttons, 2)
    rows.append(c.back("exch"))
    return Screen(text, rows)


@screen("exchbuyq")
async def exchange_buy_ask(c: Ctx) -> Screen:
    ex = c.services.exchange
    amount = _int(c.a)
    if amount not in STEPS:
        raise GameError("این مقدار در مرکز مبادله نیست؛ یکی از دکمه‌ها را بزنید.")
    quote = ex.buy_quote(amount)
    p = await c.refresh()
    left = await ex.left_today(p.id)
    lines = [
        f"🪙 {bold('تأیید خرید کریستال')}",
        "",
        f"💎 می‌گیرید: {bold(fa(amount))} کریستال",
        f"🪙 می‌پردازید: {bold(fa(quote.gold))} سکه",
        f"🧾 کارمزد ربات: {fa(quote.fee)} سکه (داخل همین مبلغ)",
        "",
        f"سکه‌ی شما: {fa(p.gold)} ← {fa(max(0, p.gold - quote.gold))}",
        f"کریستال شما: {fa(p.crystal)} ← {fa(p.crystal + amount)}",
    ]
    if p.gold < quote.gold:
        lines += ["", f"💸 {fa(quote.gold - p.gold)} سکه کم دارید."]
        return Screen("\n".join(lines), [c.back("exchbuy")])
    if amount > left:
        lines += ["", f"📅 سقف خرید امروز شما {fa(left)} کریستال دیگر است."]
        return Screen("\n".join(lines), [c.back("exchbuy")])
    lines += ["", "مبادله انجام شود؟"]
    return Screen("\n".join(lines), [[c.btn("✅ بله، تبدیل کن", "exchbuyok", amount, style="success"), c.btn("↩️ نه", "exchbuy")]])


@screen("exchbuyok")
async def exchange_buy_do(c: Ctx) -> Screen:
    quote = await c.services.exchange.buy(c.player, _int(c.a))
    shown = await exchange_buy(c)
    shown.toast, shown.alert = f"✅ {fa(quote.crystals)} کریستال گرفتید و {fa(quote.gold)} سکه دادید", True
    return shown


@screen("exchsell")
async def exchange_sell(c: Ctx) -> Screen:
    ex = c.services.exchange
    p = await c.refresh()
    text = "\n".join([
        f"💎 {bold('تبدیل کریستال به سکه')}",
        "",
        f"💰 هر کریستال {fa(ex.sell_quote(1).gold)} سکه (کارمزد کسر شده)",
        "",
        f"👛 کیف شما: {fa(p.crystal)} کریستال",
        "",
        "چند کریستال می‌فروشید؟ 👇",
    ])
    buttons = [
        c.btn(f"💎 {fa(n)} · {fa(ex.sell_quote(n).gold)} سکه", "exchsellq", n, style="success" if p.crystal >= n else None)
        for n in STEPS
    ]
    rows = keyboards.grid(buttons, 2)
    rows.append(c.back("exch"))
    return Screen(text, rows)


@screen("exchsellq")
async def exchange_sell_ask(c: Ctx) -> Screen:
    ex = c.services.exchange
    amount = _int(c.a)
    if amount not in STEPS:
        raise GameError("این مقدار در مرکز مبادله نیست؛ یکی از دکمه‌ها را بزنید.")
    quote = ex.sell_quote(amount)
    p = await c.refresh()
    lines = [
        f"💎 {bold('تأیید فروش کریستال')}",
        "",
        f"💎 می‌دهید: {bold(fa(amount))} کریستال",
        f"🪙 می‌گیرید: {bold(fa(quote.gold))} سکه",
        f"🧾 کارمزد ربات: {fa(quote.fee)} سکه (کسر شده)",
        "",
        f"کریستال شما: {fa(p.crystal)} ← {fa(max(0, p.crystal - amount))}",
        f"سکه‌ی شما: {fa(p.gold)} ← {fa(p.gold + quote.gold)}",
    ]
    if p.crystal < amount:
        lines += ["", f"💸 {fa(amount - p.crystal)} کریستال کم دارید."]
        return Screen("\n".join(lines), [c.back("exchsell")])
    lines += ["", "مبادله انجام شود؟"]
    return Screen("\n".join(lines), [[c.btn("✅ بله، تبدیل کن", "exchsellok", amount, style="success"), c.btn("↩️ نه", "exchsell")]])


@screen("exchsellok")
async def exchange_sell_do(c: Ctx) -> Screen:
    quote = await c.services.exchange.sell(c.player, _int(c.a))
    shown = await exchange_sell(c)
    shown.toast, shown.alert = f"✅ {fa(quote.crystals)} کریستال دادید و {fa(quote.gold)} سکه گرفتید", True
    return shown
