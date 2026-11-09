"""The exchange centre (مرکز مبادله): turn gold into crystals and crystals into gold."""

from __future__ import annotations

from ..game.services.exchange import MAX_TRADE
from ..shared.errors import GameError
from ..shared.text import bold, fa
from .panel import Ctx, Screen, _int, screen


@screen("exch")
async def exchange(c: Ctx) -> Screen:
    ex = c.services.exchange
    p = await c.refresh()
    text = "\n".join([
        f"🏦 {bold('مرکز مبادله')}",
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
        c.back("trade"),
    ]
    return Screen(text, rows)


def _selector(c: Ctx, screen_name: str, amount: int, top: int, confirm_screen: str, label: str) -> list:
    """The ➖ / ➕ rows that pick a number of crystals, and the confirm button."""

    def go(delta: int):  # noqa: ANN202
        return c.btn(("➕ " if delta > 0 else "➖ ") + fa(abs(delta)), screen_name, max(1, min(top, amount + delta)))

    return [
        [go(-100), go(-10), go(-1), go(1), go(10), go(100)],
        [c.btn(f"💎 {fa(amount)} {label}", "noop")],
        [c.btn("✅ ادامه و تأیید", confirm_screen, amount, style="success")],
    ]


def _amount(c: Ctx, top: int) -> int:
    return max(1, min(top, _int(c.a))) if c.a else 1


@screen("exchbuy")
async def exchange_buy(c: Ctx) -> Screen:
    ex = c.services.exchange
    p = await c.refresh()
    left = await ex.left_today(p.id)
    top = max(1, min(MAX_TRADE, left, p.gold // max(1, ex.buy_quote(1).gold)))
    amount = _amount(c, top)
    quote = ex.buy_quote(amount)
    text = "\n".join([
        f"🪙 {bold('تبدیل سکه به کریستال')}",
        "",
        f"🛒 هر کریستال {fa(ex.buy_quote(1).gold)} سکه (کارمزد داخلش است)",
        f"📅 تا پایان این شبانه‌روز می‌توانید {fa(left)} کریستال دیگر بخرید",
        f"👛 کیف شما: {fa(p.gold)} سکه",
        "",
        f"💎 می‌گیرید: {bold(fa(amount))} کریستال",
        f"🪙 می‌پردازید: {bold(fa(quote.gold))} سکه",
        "",
        "با ➖ و ➕ تعداد را تنظیم کنید 👇",
    ])
    rows = _selector(c, "exchbuy", amount, top, "exchbuyq", "کریستال")
    rows.append(c.back("exch"))
    return Screen(text, rows)


@screen("exchbuyq")
async def exchange_buy_ask(c: Ctx) -> Screen:
    ex = c.services.exchange
    amount = _int(c.a)
    if not 1 <= amount <= MAX_TRADE:
        raise GameError(f"هر مبادله از ۱ تا {fa(MAX_TRADE)} کریستال است.")
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
    top = max(1, min(MAX_TRADE, p.crystal))
    amount = _amount(c, top)
    quote = ex.sell_quote(amount)
    text = "\n".join([
        f"💎 {bold('تبدیل کریستال به سکه')}",
        "",
        f"💰 هر کریستال {fa(ex.sell_quote(1).gold)} سکه (کارمزد کسر شده)",
        f"👛 کیف شما: {fa(p.crystal)} کریستال",
        "",
        f"💎 می‌دهید: {bold(fa(amount))} کریستال",
        f"🪙 می‌گیرید: {bold(fa(quote.gold))} سکه",
        "",
        "با ➖ و ➕ تعداد را تنظیم کنید 👇",
    ])
    rows = _selector(c, "exchsell", amount, top, "exchsellq", "کریستال")
    rows.append(c.back("exch"))
    return Screen(text, rows)


@screen("exchsellq")
async def exchange_sell_ask(c: Ctx) -> Screen:
    ex = c.services.exchange
    amount = _int(c.a)
    if not 1 <= amount <= MAX_TRADE:
        raise GameError(f"هر مبادله از ۱ تا {fa(MAX_TRADE)} کریستال است.")
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
