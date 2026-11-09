"""Realm rule (فرمانروایی) in the private chat: found a city, build, train, defend and march on other cities."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from baleropy import F, Router
from baleropy.exceptions import BaleAPIError
from baleropy.fsm import FSMContext, State, StatesGroup
from baleropy.types import Message

from ..game.data import city as d
from ..game.services.city import City, Target, clean_city_name
from ..shared.errors import GameError
from ..shared.text import bar, bold, duration, fa, headline
from . import keyboards
from .panel import Ctx, Screen, _int, screen
from .services import Services

router = Router(name="city")
log = logging.getLogger("eternal_realm.city")


class CityFlow(StatesGroup):
    name = State()


#: the name a hero typed while they pick a flag: Bale user id -> name
_names: dict[int, str] = {}


def _res_line(res: str, amount: int) -> str:
    emoji, name = d.RES_INFO[res]
    return f"{emoji} {name}: {fa(amount)}"


def _sign(c: City, now: int) -> str:
    return f"🔰 سپر دفاعی: {duration(c.shield_until - now)} مانده" if c.shielded(now) else "⚠️ سپر دفاعی ندارد"


def _stars(n: int) -> str:
    return f"🌟 ستاره‌ها: {fa(n)} از ۳"


def _parse_delta(text: str) -> int:
    sign = -1 if text.startswith("m") else 1
    return sign * _int(text[1:])


LINE = "─" * 12


def _work_line(city: City, now: int) -> str:
    if city.builds:
        w = city.builds[0]
        b = d.get_building(w.kind)
        return f"🏗️ {b.name} ← سطح {fa(w.level)} · {duration(w.ready_at - now)} مانده"
    return "🏗️ سازندگان بیکارند"


def _advice(city: City) -> str:
    prod, eaten = city.rates()
    if city.happiness < 30:
        return "🍞 فرمانده: مردم گرسنه‌اند؛ مزرعه را بالا ببرید یا بسته‌ی آذوقه بخرید."
    if prod["food"] < eaten:
        return "🌾 فرمانده: مصرف غذا از تولید بیشتر است؛ مزرعه را ارتقا دهید."
    if not city.builds:
        return "🏗️ فرمانده: سازندگان بیکارند؛ ساختمانی را ارتقا دهید."
    if not city.army and not city.training:
        return "⚔️ فرمانده: شهر بی‌لشکر است؛ در سربازخانه نیرو تربیت کنید."
    return "🌟 فرمانده: شهر آرام است و آماده‌ی فرمان شما."


def _need_city_text() -> str:
    return "شما هنوز شهری ندارید. از «فرمانروایی» شهرتان را بنا کنید."


# --- entrance and founding ----------------------------------------------------------------------------
@screen("city")
async def realm(c: Ctx) -> Screen:
    if c.is_group:
        raise GameError("فرمانروایی در پیام خصوصی ربات باز می‌شود؛ آنجا بیایید.")
    p = await c.refresh()
    city = await c.services.city.mine(p)
    if city is None:
        b = c.services.ctx.balance
        text = [
            f"🏰 {bold('فرمانروایی')}",
            "",
            "هر فرمانده‌ای می‌تواند برای خودش شهری بسازد؛ مزرعه و معدن برپا کند، لشکر بپروراند و به سرزمین دشمنان بتازد.",
            "",
            f"🎓 سطح لازم: {fa(b.city_min_level)} (سطح شما: {fa(p.level)})",
            f"💰 هزینه‌ی بنای شهر: {fa(b.city_found_gold)} سکه",
            "🔰 شهر تازه‌تأسیس یک شبانه‌روز در پناه سپر است",
        ]
        rows = []
        if p.level >= b.city_min_level:
            rows.append([c.btn("🏗️ بنای شهر", "cityfound", style="success")])
        else:
            text += ["", f"🔒 هنوز {fa(b.city_min_level - p.level)} سطح مانده تا بتوانید شهر بسازید."]
        rows.append(c.back("home"))
        return Screen("\n".join(text), rows)
    now = c.services.ctx.now()
    unseen = await c.services.city.unseen_reports(p.id)
    league = d.league_of(city.trophies)
    working = len(city.builds) + len(city.training)
    text = [
        f"🏰 {bold('فرمانروایی')}",
        LINE,
        f"{city.flag} {bold('شهر ' + city.name)} · قلعه‌ی سطح {fa(city.castle)}",
        f"{league[0]} لیگ {league[1]} · {fa(city.trophies)} جام",
        _sign(city, now),
        LINE,
        *[_res_line(r, city.amount(r)) for r in d.RES],
        LINE,
        f"🏘️ جمعیت: {fa(int(city.pop))} · رضایت {fa(round(city.happiness))}٪",
        f"⚔️ ارتش: {fa(city.army)} نفر · قدرت {fa(city.army_power)}",
        _work_line(city, now),
        LINE,
        _advice(city),
    ]
    rows = [
        [c.btn("🏰 شهر من", "citymine"), c.btn("🏗️ ساختمان‌ها", "citybuild")],
        [c.btn("👥 جمعیت و مردم", "citypeople"), c.btn("🌾 منابع و آذوقه", "citystock")],
        [c.btn("⚔️ ارتش و سربازان", "citytroops"), c.btn("🛡️ دفاع شهر", "citydef")],
        [c.btn("🗡️ حمله به شهرها", "cityatk", style="danger"), c.btn("🗺️ نقشه جهان", "citymap")],
        [c.btn("🏆 لیگ و رتبه‌بندی", "cityleague"), c.btn(f"📜 گزارش جنگ‌ها{f' ({fa(unseen)})' if unseen else ''}", "cityreports")],
        [c.btn(f"⏱️ صف کارها{f' ({fa(working)})' if working else ''}", "cityqueue", style="primary" if working else None),
         c.btn("⚙️ تنظیمات شهر", "citycfg")],
        [c.btn("🛒 خرید منابع از خزانه", "prem", "city", style="success")],
        c.back("home"),
    ]
    return Screen("\n".join(text), rows)


@screen("cityfound")
async def city_found(c: Ctx) -> Screen:
    p = await c.refresh()
    b = c.services.ctx.balance
    if p.level < b.city_min_level:
        raise GameError(f"برای بنای شهر باید به سطح {fa(b.city_min_level)} برسید.")
    if c.state is None:
        raise GameError("برای نوشتن نام از پیوی ربات شروع کنید.")
    await c.state.set_state(CityFlow.name)
    text = (
        f"🏗️ {bold('بنای شهر')}\n\n"
        f"نام شهرتان را بفرستید ({fa(d.NAME_MIN)} تا {fa(d.NAME_MAX)} حرف).\n"
        "مثال: آذرگان"
    )
    return Screen(text, [c.back("city", "❌ انصراف")])


@router.message(CityFlow.name, F.text)
async def got_city_name(message: Message, state: FSMContext, services: Services) -> None:
    user = message.from_user
    assert user is not None
    await services.players.require(user.id)
    await state.clear()
    name = clean_city_name(message.text or "")
    _names[user.id] = name
    flags = keyboards.grid(
        [keyboards.panel_button(f"{emoji} {label}", "cityflag", user.id, str(i)) for i, (emoji, label) in enumerate(d.FLAGS)], 3
    )
    flags.append([keyboards.panel_button("❌ انصراف", "city", user.id)])
    await message.answer(
        headline(f"🚩 {bold('پرچم شهر')}\n\nشهر {bold(name)}\n\nنشان و پرچم شهرتان را برگزینید 👇"), buttons=flags
    )


@screen("cityflag")
async def city_flag(c: Ctx) -> Screen:
    name = _names.get(c.player.platform_user_id)
    if not name:
        raise GameError("نام شهر را دوباره بفرستید.")
    index = _int(c.a)
    if not 0 <= index < len(d.FLAGS):
        raise GameError("این پرچم وجود ندارد.")
    b = c.services.ctx.balance
    p = await c.refresh()
    emoji, label = d.FLAGS[index]
    text = "\n".join([
        f"🏗️ {bold('تأیید بنای شهر')}",
        "",
        f"{emoji} شهر {bold(name)} (پرچم {label})",
        f"💰 هزینه: {bold(fa(b.city_found_gold))} سکه",
        f"کیسه‌ی شما: {fa(p.gold)} ← {fa(max(0, p.gold - b.city_found_gold))}",
        "",
        "با بنای شهر، قلعه، مزرعه، چوب‌بری، معدن سنگ و سربازخانه ساخته می‌شود و شهر یک شبانه‌روز سپر دارد.",
    ])
    if p.gold < b.city_found_gold:
        return Screen(text + f"\n\n💸 {fa(b.city_found_gold - p.gold)} سکه کم دارید.", [c.back("city")])
    return Screen(text, [[c.btn("✅ بله، بنا کن", "cityfoundok", index, style="success"), c.btn("↩️ نه", "city")]])


@screen("cityfoundok")
async def city_found_do(c: Ctx) -> Screen:
    name = _names.pop(c.player.platform_user_id, "")
    if not name:
        raise GameError("نام شهر را دوباره بفرستید.")
    index = _int(c.a)
    city = await c.services.city.found(c.player, name, d.FLAGS[index][0] if 0 <= index < len(d.FLAGS) else "")
    shown = await realm(c)
    shown.text = f"🎉 {bold('شهر ' + city.name + ' بنا شد!')}\n\nپرچم شما بر فراز دیوارها به اهتزاز درآمد.\n\n{shown.text}"
    shown.toast, shown.alert = f"🏰 شهر {city.name} بنا شد!", True
    return shown


async def _city(c: Ctx) -> City:
    city = await c.services.city.mine(await c.refresh())
    if city is None:
        raise GameError(_need_city_text())
    return city


# --- my city ------------------------------------------------------------------------------------------------
@screen("citymine")
async def city_mine(c: Ctx) -> Screen:
    city, now = await _city(c), c.services.ctx.now()
    league = d.league_of(city.trophies)
    text = [
        f"🏰 {bold('شهر ' + city.name)}",
        f"{city.flag} پرچم شهر",
        "",
        f"👑 فرمانروا: {city.owner_name}",
        f"🏛️ سطح قلعه: {fa(city.castle)}",
        f"🛡️ خاندان: {city.clan or 'ندارد'}",
        "",
        f"👥 جمعیت: {fa(int(city.pop))}",
        f"😊 رضایت مردم: {fa(round(city.happiness))}٪",
        "",
        *[_res_line(r, city.amount(r)) for r in d.RES],
        "",
        f"⚔️ قدرت ارتش: {fa(city.army_power)}",
        f"🧱 قدرت دفاعی: {fa(city.defense_power)}",
        f"{league[0]} لیگ {league[1]} · {fa(city.trophies)} جام",
        _sign(city, now),
    ]
    rows = [[c.btn("💰 واریز سکه به خزانه‌ی شهر", "citydep")], c.back("city")]
    return Screen("\n".join(text), rows)


@screen("citydep")
async def city_deposit(c: Ctx) -> Screen:
    city, p = await _city(c), c.player
    text = (
        f"💰 {bold('خزانه‌ی شهر')}\n\n"
        "سکه‌ی شما جدا از سکه‌ی خزانه‌ی شهر است. هر مقدار واریز کنید در خزانه‌ی شهر می‌ماند و برای ساخت و سرباز خرج می‌شود.\n\n"
        f"👛 کیف شما: {fa(p.gold)} سکه\n🏰 خزانه‌ی شهر: {fa(city.amount('gold'))} سکه"
    )
    rows = keyboards.grid([c.btn(f"🪙 {fa(n)}", "citydepq", n) for n in (1_000, 5_000, 20_000, 100_000)], 2)
    rows.append(c.back("citymine"))
    return Screen(text, rows)


@screen("citydepq")
async def city_deposit_ask(c: Ctx) -> Screen:
    amount, city, p = _int(c.a), await _city(c), c.player
    lines = [
        f"💰 {bold('تأیید واریز')}", "",
        f"مبلغ: {bold(fa(amount))} سکه", "",
        f"کیف شما: {fa(p.gold)} ← {fa(max(0, p.gold - amount))}",
        f"خزانه‌ی شهر: {fa(city.amount('gold'))} ← {fa(city.amount('gold') + amount)}",
    ]
    if p.gold < amount:
        return Screen("\n".join(lines + ["", f"💸 {fa(amount - p.gold)} سکه کم دارید."]), [c.back("citydep")])
    return Screen("\n".join(lines + ["", "واریز شود؟"]), [[c.btn("✅ بله، واریز کن", "citydepok", amount, style="success"), c.btn("↩️ نه", "citydep")]])


@screen("citydepok")
async def city_deposit_do(c: Ctx) -> Screen:
    amount = _int(c.a)
    await c.services.city.deposit(c.player, amount)
    await c.refresh()
    shown = await city_deposit(c)
    shown.toast = f"💰 {fa(amount)} سکه به خزانه‌ی شهر رفت"
    return shown


# --- buildings -------------------------------------------------------------------------------------------------
@screen("citybuild")
async def city_build(c: Ctx) -> Screen:
    city = await _city(c)
    text = "\n".join([
        f"🏗️ {bold('ساختمان‌ها')}",
        "",
        f"🏛️ سطح قلعه: {fa(city.castle)}",
        f"📐 جایگاه ساختمان: {fa(city.slots_used)} از {fa(city.slots_total)} پر است",
        _work_line(city, c.services.ctx.now()),
        "با ارتقای قلعه، هم سطح ساختمان‌ها بالاتر می‌رود و هم جایگاه تازه باز می‌شود.",
        "",
        "روی هر ساختمان بزنید 👇",
    ])
    buttons = []
    for b in d.BUILDINGS:
        lv = city.levels.get(b.id, 0)
        building_now = any(w.kind == b.id for w in city.builds)
        tag = fa(lv) if lv else ("🔒" if b.id != "castle" and city.castle < b.needs else "—")
        if building_now:
            tag += " ⏳"
        buttons.append(c.btn(f"{b.emoji} {b.name} · {tag}", "citybv", b.id))
    rows = keyboards.grid(buttons, 2)
    rows.append(c.back("city"))
    return Screen(text, rows)


def _effect(b: d.Building, level: int) -> str:
    if b.id in d.PRODUCTION:
        res, per = d.PRODUCTION[b.id]
        return f"{d.RES_INFO[res][0]} تولید {d.RES_INFO[res][1]}: ساعتی {fa(per * level)}"
    if b.id == "warehouse":
        return f"📦 ظرفیت انبار: {fa(4000 * level)} بیشتر"
    if b.id == "smithy":
        return f"⚔️ قدرت حمله‌ی نیروها: {fa(3 * level)}٪ بیشتر"
    if b.id == "hospital":
        return f"🏥 درمان تلفات: {fa(5 * level)}٪"
    if b.id == "castle":
        return f"🏛️ جایگاه ساختمان: {fa(d.slots_for(level))} · جمعیت تا {fa(d.population_cap(level))}"
    if b.id == "wall":
        return f"🧱 مقاومت در برابر پیاده‌نظام: {fa(20 * level)}٪ بیشتر"
    if b.id == "tower":
        return f"🗼 تیر برج: {fa(45 * level)} آسیب در هر دور"
    return f"⚔️ ظرفیت ارتش: {fa(100 * level)} بیشتر"


@screen("citybv")
async def city_building(c: Ctx) -> Screen:
    city = await _city(c)
    try:
        b = d.get_building(c.a)
    except KeyError:
        raise GameError("چنین ساختمانی نیست.") from None
    level = city.levels.get(b.id, 0)
    lines = [f"{b.emoji} {bold(b.name)}", "", b.about, ""]
    lines.append(f"🏗️ سطح فعلی: {fa(level)}" if level else "🏗️ هنوز ساخته نشده")
    if level:
        lines.append(_effect(b, level))
    rows = []
    reason = ""
    now = c.services.ctx.now()
    working = next((w for w in city.builds if w.kind == b.id), None)
    if working is not None:
        left = working.ready_at - now
        price = d.rush_crystals(left)
        lines += ["", f"⏳ {bold('در حال ارتقا به سطح ' + fa(working.level))}", f"🕐 {duration(left)} مانده", _effect(b, working.level)]
        rows.append([c.btn(f"💎 تکمیل فوری · {fa(price)} کریستال", "cityrushq", "build", working.id, style="success")])
        rows.append(c.back("citybuild"))
        return Screen("\n".join(lines), rows)
    if level >= (d.MAX_CASTLE if b.id == "castle" else b.max_level):
        reason = "به بالاترین سطح رسیده است."
    elif b.id != "castle" and level == 0 and city.castle < b.needs:
        reason = f"برای ساختنش قلعه باید به سطح {fa(b.needs)} برسد."
    elif b.id != "castle" and level >= city.castle:
        reason = "سطحش از قلعه بالاتر نمی‌رود؛ اول قلعه را ارتقا دهید."
    elif level == 0 and city.slots_used >= city.slots_total:
        reason = "جایگاه خالی ندارید؛ قلعه را ارتقا دهید."
    if reason:
        lines += ["", f"🔒 {reason}"]
    else:
        cost = d.build_cost(b, level)
        lines += ["", f"⬆️ {bold('هزینه‌ی سطح ' + fa(level + 1))}", _effect(b, level + 1), f"🕐 مدت ساخت: {duration(d.build_seconds(b, level))}"]
        ok = True
        for r in ("gold", "wood", "stone", "iron"):
            if cost[r]:
                have = city.amount(r)
                ok = ok and have >= cost[r]
                lines.append(f"{d.RES_INFO[r][0]} {d.RES_INFO[r][1]}: {fa(cost[r])} (دارید {fa(have)})")
        if city.builds:
            lines += ["", "🔨 سازندگان مشغول کار دیگری هستند؛ از «صف کارها» تسریعش کنید."]
        elif ok:
            rows.append([c.btn(f"✅ {'ارتقا به سطح ' + fa(level + 1) if level else 'ساخت'}", "citybok", b.id, style="success")])
        else:
            lines += ["", "💸 منابع شهر کافی نیست."]
            rows.append([c.btn("🛒 خرید بسته‌ی منابع", "prem", "city", style="success")])
    rows.append(c.back("citybuild"))
    return Screen("\n".join(lines), rows)


@screen("citybok")
async def city_build_do(c: Ctx) -> Screen:
    _, level, seconds = await c.services.city.build(c.player, c.a)
    shown = await city_building(c)
    shown.toast = f"🏗️ ساخت {d.get_building(c.a).name} (سطح {fa(level)}) شروع شد · {duration(seconds)}"
    return shown


# --- people and food ---------------------------------------------------------------------------------------------
@screen("citypeople")
async def city_people(c: Ctx) -> Screen:
    city = await _city(c)
    prod, eaten = city.rates()
    mood = "شاد و آرام" if city.happiness >= 70 else "ناراضی" if city.happiness >= 30 else "در آستانه‌ی شورش"
    lines = [
        f"👥 {bold('جمعیت و مردم')}",
        "",
        f"🏘️ جمعیت کل: {fa(int(city.pop))} از {fa(city.pop_cap)}",
        f"⚒️ جمعیت شاغل: {fa(city.employed)}",
        f"🛌 جمعیت بیکار: {fa(city.unemployed)}",
        f"🎖️ قابل سربازگیری: {fa(city.recruitable)}",
        f"🗡️ سرباز و در آموزش: {fa(city.army + city.in_training)}",
        "",
        f"😊 رضایت: {bar(round(city.happiness), 100, 10)} {fa(round(city.happiness))}٪ ({mood})",
    ]
    if city.happiness < 30:
        lines += ["", "⚠️ مردم گرسنه‌اند؛ تولید نصف شده و شورش در راه است. غذا برسانید!"]
    elif prod["food"] < eaten:
        lines += ["", "⚠️ مصرف غذا از تولید بیشتر است؛ مزرعه را ارتقا دهید."]
    else:
        lines += ["", "جمعیت با غذای کافی کم‌کم بیشتر می‌شود."]
    return Screen("\n".join(lines), [c.back("city")])


@screen("citystock")
async def city_stock(c: Ctx) -> Screen:
    city = await _city(c)
    now = c.services.ctx.now()
    boost = 2.0 if city.boost_until > now else 1.0
    prod, eaten = city.rates(boost)
    cap = city.storage
    lines = [f"🌾 {bold('منابع و آذوقه')}", "", f"📦 ظرفیت انبار: {fa(cap)} (سکه: {fa(cap * 2)})", ""]
    for r in d.RES:
        emoji, name = d.RES_INFO[r]
        net = prod[r] - (eaten if r == "food" else 0)
        sign = "+" if net >= 0 else "-"
        lines.append(f"{emoji} {name}: {fa(city.amount(r))} ({sign}{fa(abs(round(net)))} در ساعت)")
    lines += [
        "",
        f"🍞 مصرف غذا: {fa(round(eaten))} در ساعت (مردم و سربازان)",
    ]
    if boost > 1:
        lines.append(f"🚀 بوست دو برابر فعال است؛ تولید شهر دو برابر می‌شود ({duration(city.boost_until - now)} مانده)")
    net_food = prod["food"] - eaten
    if net_food < 0:
        lines.append(f"⏳ غذا تا {duration(int(city.res['food'] / -net_food * 3600))} دیگر تمام می‌شود")
    lines += ["", "غذا و منابع هر ساعت به خزانه می‌رسند، حتی وقتی شما نیستید."]
    return Screen("\n".join(lines), [c.back("city")])


# --- army ----------------------------------------------------------------------------------------------------------
@screen("citytroops")
async def city_troops(c: Ctx) -> Screen:
    city, now = await _city(c), c.services.ctx.now()
    lines = [
        f"⚔️ {bold('ارتش و سربازان')}",
        "",
        f"📊 قدرت ارتش: {fa(city.army_power)}",
        f"🧳 ظرفیت: {fa(city.space_used)} از {fa(city.capacity)}",
        "",
    ]
    for t in d.TROOPS:
        have = city.troops.get(t.id, 0)
        if have:
            lines.append(f"{t.emoji} {t.name}: {fa(have)}")
    if not city.army:
        lines.append("هنوز سربازی ندارید.")
    if city.training:
        lines += ["", f"⏳ {bold('در حال آموزش')}"]
        for batch in city.training:
            t = d.get_troop(batch.kind)
            lines.append(f"{t.emoji} {fa(batch.qty)} {t.name} · {duration(batch.ready_at - now)} دیگر")
    lines += ["", "برای تربیت، نوع نیرو را بزنید 👇"]
    rows = keyboards.grid([c.btn(f"{t.emoji} {t.name}", "citytr", t.id) for t in d.TROOPS], 2)
    for batch in city.training:
        t = d.get_troop(batch.kind)
        rows.append([c.btn(f"💎 تکمیل فوری {t.name} · {fa(d.rush_crystals(batch.ready_at - now))} کریستال", "cityrushq", "train", batch.id)])
    rows.append(c.back("city"))
    return Screen("\n".join(lines), rows)


@screen("citytr")
async def city_train(c: Ctx) -> Screen:
    city = await _city(c)
    try:
        t = d.get_troop(c.a)
    except KeyError:
        raise GameError("چنین نیرویی نیست.") from None
    level = city.levels.get(t.building, 0)
    g, f, w, i = t.cost
    cost = [f"{d.RES_INFO[r][0]} {d.RES_INFO[r][1]}: {fa(v)}" for r, v in (("gold", g), ("food", f), ("wood", w), ("iron", i)) if v]
    lines = [
        f"{t.emoji} {bold(t.name)}", "", t.about, "",
        f"⚔️ قدرت حمله: {fa(t.atk)}",
        f"🛡️ قدرت دفاع: {fa(t.defense)}",
        f"❤️ جان: {fa(t.hp)}",
        f"🐎 سرعت: {fa(t.speed)}",
        f"🧳 ظرفیت اشغال ارتش: {fa(t.cap)}",
        "💰 هزینه‌ی هر نفر:",
        *cost,
        f"⏳ آموزش هر نفر: {fa(t.train_seconds)} ثانیه",
        f"🍞 مصرف غذا: {fa(t.upkeep)} در ساعت",
        "",
        f"🎖️ قابل سربازگیری: {fa(city.recruitable)}",
        f"🧳 جای خالی ارتش: {fa(city.capacity - city.space_used)}",
    ]
    rows = []
    if level < t.needs:
        lines += ["", f"🔒 {d.get_building(t.building).name} باید به سطح {fa(t.needs)} برسد (الان {fa(level)})."]
    else:
        rows = keyboards.grid([c.btn(f"➕ {fa(n)} نفر", "citytrq", t.id, n) for n in (10, 50, 100, 500)], 2)
        best = _max_train(city, t)
        if best:
            rows.append([c.btn(f"🔝 بیشترین توان ({fa(best)} نفر)", "citytrq", t.id, best, style="primary")])
        rows.append([c.btn("🛒 خرید بسته‌ی منابع", "prem", "city")])
    rows.append(c.back("citytroops"))
    return Screen("\n".join(lines), rows)


def _max_train(city: City, t: d.Troop) -> int:
    """The most soldiers of a kind the city can afford and house right now."""
    g, f, w, i = t.cost
    costs = {"gold": g, "food": f, "wood": w, "iron": i}
    limits = [city.amount(r) // v for r, v in costs.items() if v]
    limits += [city.recruitable, (city.capacity - city.space_used) // t.cap]
    return max(0, min(limits))


@screen("citytrq")
async def city_train_ask(c: Ctx) -> Screen:
    city = await _city(c)
    qty, t = _int(c.b), d.get_troop(c.a)
    g, f, w, i = t.cost
    total = {r: v * qty for r, v in (("gold", g), ("food", f), ("wood", w), ("iron", i)) if v}
    seconds = max(30, round(qty * t.train_seconds / (1 + 0.1 * (city.levels.get(t.building, 1) - 1))))
    lines = [f"{t.emoji} {bold('تأیید تربیت ' + fa(qty) + ' ' + t.name)}", ""]
    ok = True
    for r, v in total.items():
        have = city.amount(r)
        ok = ok and have >= v
        lines.append(f"{d.RES_INFO[r][0]} {d.RES_INFO[r][1]}: {fa(v)} (دارید {fa(have)})")
    lines += ["", f"⏳ مدت آموزش: {duration(seconds)}"]
    if not ok:
        lines += ["", "💸 منابع شهر کافی نیست."]
        return Screen("\n".join(lines), [c.back("citytr", "🔙 بازگشت", t.id)])
    lines += ["", "سربازگیری شود؟"]
    return Screen("\n".join(lines), [[c.btn("✅ بله، تربیت کن", "citytrok", t.id, qty, style="success"), c.btn("↩️ نه", "citytr", t.id)]])


@screen("citytrok")
async def city_train_do(c: Ctx) -> Screen:
    _, batch = await c.services.city.train(c.player, c.a, _int(c.b))
    shown = await city_troops(c)
    t = d.get_troop(batch.kind)
    shown.toast = f"{t.emoji} {fa(batch.qty)} {t.name} به آموزشگاه رفتند"
    return shown


# --- defence ----------------------------------------------------------------------------------------------------------
@screen("citydef")
async def city_defence(c: Ctx) -> Screen:
    city, now = await _city(c), c.services.ctx.now()
    lines = [
        f"🛡️ {bold('دفاع شهر')}",
        "",
        f"🧱 قدرت دفاعی: {fa(city.defense_power)}",
        f"🧱 دیوار: سطح {fa(city.levels.get('wall', 0))}",
        f"🗼 برج نگهبانی: سطح {fa(city.levels.get('tower', 0))}",
        f"🏥 بیمارستان: سطح {fa(city.levels.get('hospital', 0))}",
        _sign(city, now),
        "",
        f"🪤 {bold('تله‌ها')} (هر تله «شارژ» است و در حمله مصرف می‌شود)",
    ]
    for trap in d.TRAPS:
        lines.append(f"{trap.emoji} {trap.name}: {fa(city.traps.get(trap.id, 0))} شارژ")
    lines += ["", f"هر تله تا {fa(d.trap_limit(city.castle))} شارژ نگه‌داری می‌شود. سربازان شهر هم در برابر مهاجم می‌جنگند."]
    rows = keyboards.grid([c.btn(f"{t.emoji} {t.name}", "citytrap", t.id) for t in d.TRAPS], 2)
    rows.append([c.btn("🔰 خرید سپر دفاعی", "cityshield")])
    rows.append(c.back("city"))
    return Screen("\n".join(lines), rows)


@screen("citytrap")
async def city_trap(c: Ctx) -> Screen:
    city = await _city(c)
    trap = d.get_trap(c.a)
    g, w, s, i = trap.cost
    total = {r: v * d.TRAP_BATCH for r, v in (("gold", g), ("wood", w), ("stone", s), ("iron", i)) if v}
    lines = [f"{trap.emoji} {bold(trap.name)}", "", f"💥 آسیب هر شارژ: {fa(trap.damage)}", f"📦 هر خرید: {fa(d.TRAP_BATCH)} شارژ", ""]
    ok = city.castle >= 2 and city.traps.get(trap.id, 0) + d.TRAP_BATCH <= d.trap_limit(city.castle)
    for r, v in total.items():
        have = city.amount(r)
        ok = ok and have >= v
        lines.append(f"{d.RES_INFO[r][0]} {d.RES_INFO[r][1]}: {fa(v)} (دارید {fa(have)})")
    rows = []
    if city.castle < 2:
        lines += ["", "🔒 ساخت تله از قلعه‌ی سطح ۲ ممکن است."]
    elif ok:
        rows.append([c.btn(f"✅ خرید {fa(d.TRAP_BATCH)} شارژ", "citytrapok", trap.id, style="success")])
    else:
        lines += ["", "💸 منابع کافی نیست یا به سقف رسیده‌اید."]
    rows.append(c.back("citydef"))
    return Screen("\n".join(lines), rows)


@screen("citytrapok")
async def city_trap_do(c: Ctx) -> Screen:
    await c.services.city.buy_trap(c.player, c.a)
    shown = await city_trap(c)
    shown.toast = f"{d.get_trap(c.a).emoji} تله آماده شد"
    return shown


@screen("cityshield")
async def city_shield(c: Ctx) -> Screen:
    city, now, p = await _city(c), c.services.ctx.now(), c.player
    lines = [
        f"🔰 {bold('سپر دفاعی')}", "",
        "در مدت سپر هیچ‌کس نمی‌تواند به شهر شما حمله کند؛ شما همچنان می‌توانید حمله کنید و تولید ادامه دارد.", "",
        _sign(city, now), f"💎 کریستال شما: {fa(p.crystal)}",
    ]
    rows = [[c.btn(f"🔰 {fa(h)} ساعته · {fa(cr)} کریستال", "cityshieldq", h) for h, cr in d.SHIELD_OPTIONS]]
    rows.append(c.back("citydef"))
    return Screen("\n".join(lines), rows)


@screen("cityshieldq")
async def city_shield_ask(c: Ctx) -> Screen:
    hours = _int(c.a)
    crystals = dict(d.SHIELD_OPTIONS).get(hours)
    if crystals is None:
        raise GameError("این سپر وجود ندارد.")
    p = await c.refresh()
    lines = [
        f"🔰 {bold('تأیید خرید سپر')}", "",
        f"مدت: {fa(hours)} ساعت", f"💎 بها: {bold(fa(crystals))} کریستال", "",
        f"کریستال شما: {fa(p.crystal)} ← {fa(max(0, p.crystal - crystals))}",
    ]
    if p.crystal < crystals:
        return Screen("\n".join(lines + ["", f"💸 {fa(crystals - p.crystal)} کریستال کم دارید."]), [c.back("cityshield")])
    return Screen("\n".join(lines + ["", "خریداری شود؟"]), [[c.btn("✅ بله", "cityshieldok", hours, style="success"), c.btn("↩️ نه", "cityshield")]])


@screen("cityshieldok")
async def city_shield_do(c: Ctx) -> Screen:
    hours = _int(c.a)
    await c.services.city.buy_shield(c.player, hours)
    await c.refresh()
    shown = await city_shield(c)
    shown.toast = f"🔰 سپر {fa(hours)} ساعته فعال شد"
    return shown


# --- attacking --------------------------------------------------------------------------------------------------------------
@screen("cityatk")
async def city_attack(c: Ctx) -> Screen:
    city = await _city(c)
    text = "\n".join([
        f"⚔️ {bold('لشکرکشی و حمله')}",
        "",
        "فرمانروا، آماده‌ای تا به سرزمین دشمن لشکرکشی کنی؟",
        "",
        "برای شروع، یک حریف متناسب با قدرت شهر تو پیدا می‌کنیم.",
        "",
        f"⚔️ قدرت ارتش: {fa(city.army_power)}",
        f"🏛️ سطح قلعه: {fa(city.castle)}",
        f"🗡️ سربازان آماده: {fa(city.army)}",
        f"📅 حمله‌ی امروز: حداکثر {fa(d.DAILY_ATTACKS)} (جستجو رایگان است)",
    ])
    return Screen(text, [[c.btn("🔍 جستجوی حریف", "citysearch", style="danger")], c.back("city")])


def _target_card(t: Target, header: str, now: int) -> str:
    x = t.city
    lines = [
        f"🏰 {bold(header)}", "",
        f"{x.flag} {bold('شهر ' + x.name)}",
        f"👑 فرمانروا: {x.owner_name}" + (f" · خاندان: {x.clan}" if x.clan else ""),
        "",
        f"🏛️ سطح قلعه: {fa(x.castle)}",
        f"👥 جمعیت: {fa(int(x.pop))}",
        f"🧱 قدرت دفاع: {fa(x.defense_power)}",
        f"⚔️ قدرت ارتش: {fa(x.army_power)}",
        "",
        f"🎁 {bold('غنائم قابل دریافت')} (حداکثر)",
        *[_res_line(r, t.loot[r]) for r in d.RES],
    ]
    if t.inactive_days > 3:
        lines += ["", f"💤 این شهر {fa(t.inactive_days)} روز است ساکت مانده؛ غنائمش کمتر است."]
    return "\n".join(lines)


@screen("citysearch")
async def city_search(c: Ctx) -> Screen:
    t = await c.services.city.search(c.player)
    rows = [
        [c.btn("⚔️ حمله به شهر", "cityprep", style="danger"), c.btn("🔄 جستجوی مجدد", "citysearch")],
        c.back("cityatk"),
    ]
    return Screen(_target_card(t, "شهر دشمن پیدا شد!", c.services.ctx.now()), rows)


@screen("cityprep")
async def city_prepare(c: Ctx) -> Screen:
    city = await _city(c)
    found = await c.services.city.current_target(c.player)
    if found is None:
        raise GameError("اول یک حریف پیدا کنید.")
    target, chosen = found
    lines = [
        f"⚔️ {bold('آماده‌سازی حمله به ' + target.city.name)}", "",
        "ترکیب لشکر را بچینید؛ تا تأیید نهایی هیچ سربازی از دست نمی‌رود.", "",
    ]
    rows = []
    power = units = 0
    for t in d.TROOPS:
        have = city.troops.get(t.id, 0)
        if not have:
            continue
        sent = chosen.get(t.id, 0)
        step = 10 if have >= 20 else 1
        units += sent
        power += sent * d.unit_power(t)
        lines.append(f"{t.emoji} {t.name}: {fa(sent)} از {fa(have)}")
        rows.append([
            c.btn("➖", "cityadj", t.id, f"m{step}"),
            c.btn(f"{t.emoji} {fa(sent)}/{fa(have)}", "cityadj", t.id, "p0"),
            c.btn("➕", "cityadj", t.id, f"p{step}"),
        ])
    if not rows:
        lines.append("سربازی در شهر ندارید.")
    supplies = units * 3
    lines += [
        "",
        f"🧮 جمع لشکر: {fa(units)} نفر · قدرت {fa(power)}",
        f"🍞 آذوقه‌ی سفر: {fa(supplies)} (دارید {fa(city.amount('food'))})",
        f"🧱 قدرت دفاع دشمن: {fa(target.city.defense_power)}",
    ]
    commander = min(15, c.player.level * 0.2)
    lines.append(f"🎖️ فرمانده‌ی لشکر: {c.player.name} (+{fa(round(commander))}٪ قدرت)")
    rows.append([c.btn("🧳 همه‌ی نیروها", "cityall"), c.btn("🧹 پاک کردن", "cityclear")])
    if units and city.amount("food") >= supplies:
        rows.append([c.btn("✅ تأیید نهایی و حمله", "citygo", style="danger")])
    elif units:
        lines += ["", "⚠️ آذوقه‌ی سفر کافی نیست."]
    rows.append(c.back("citysearch", "🔙 حریف دیگر"))
    return Screen("\n".join(lines), rows)


@screen("cityadj")
async def city_adjust(c: Ctx) -> Screen:
    delta = _parse_delta(c.b)
    if delta:
        await c.services.city.adjust(c.player, c.a, delta)
    return await city_prepare(c)


@screen("cityall")
async def city_all(c: Ctx) -> Screen:
    await c.services.city.adjust(c.player, None, 0, everyone=True)
    return await city_prepare(c)


@screen("cityclear")
async def city_clear(c: Ctx) -> Screen:
    await c.services.city.adjust(c.player, None, 0, clear=True)
    return await city_prepare(c)


def _loot_lines(loot: dict[str, int]) -> list[str]:
    got = [_res_line(r, v) for r, v in loot.items() if v]
    return got or ["غنیمتی به دست نیامد."]


def _troop_lines(units: dict[str, int]) -> list[str]:
    return [f"{d.get_troop(k).emoji} {d.get_troop(k).name}: {fa(v)}" for k, v in units.items() if v] or ["هیچ"]


@screen("citygo")
async def city_go(c: Ctx) -> Screen:
    found = await c.services.city.current_target(c.player)
    name = found[0].city.name if found else "دشمن"
    await c.show(f"⚔️ {bold('لشکر به راه افتاد…')}\n\nپرچم‌ها بالا رفتند و طبل‌ها به صدا درآمدند، به سوی شهر {name}!")
    result = await c.services.city.attack(c.player)
    for i in range(0, len(result.log), 2):
        await c.show(f"⚔️ {bold('گزارش نبرد – شهر ' + result.defender_city)}\n\nنبرد در جریان…\n\n" + "\n".join(result.log[: i + 2]))
    text = _result_text(result, c.services.ctx.now())
    if result.defender_uid and c.message is not None:
        with contextlib.suppress(BaleAPIError):
            await c.message.bot.send_message(
                result.defender_uid, _attacked_text(result),
                buttons=[[keyboards.panel_button("📜 دیدن گزارش و انتقام", "cityrep", result.defender_uid, str(result.attack_id))]],
            )
    rows = [
        [c.btn("🔍 حریف تازه", "citysearch", style="danger"), c.btn("📜 گزارش‌ها", "cityreports")],
        c.back("city"),
    ]
    return Screen(text, rows)


def _attacked_text(r) -> str:  # noqa: ANN001 - AttackResult
    lines = [
        f"⚠️ {bold('شهر شما مورد حمله قرار گرفت!')}", "",
        f"🗡️ لشکر {r.attacker_name} به شهر {r.defender_city} تاخت.",
        _stars(r.stars),
        f"📊 میزان تخریب: {fa(round(r.destruction * 100))}٪",
    ]
    taken = [_res_line(k, v) for k, v in r.loot.items() if v]
    if taken:
        lines += ["", bold("منابع ازدست‌رفته"), *taken]
    lines += ["", f"🔰 سپر دفاعی تازه: {duration(r.shield)}" if r.shield else "⚠️ این حمله سپر دفاعی به شما نداد"]
    return "\n".join(lines)


def _result_text(r, now: int) -> str:  # noqa: ANN001 - AttackResult
    verdict = {
        0: "💥 حمله ناکام ماند؛ دیوارها پایداری کردند.",
        1: "🎯 پیروزی محدود!",
        2: "🏅 پیروزی قابل توجه!",
        3: "🏆 پیروزی کامل! شهر در هم کوبیده شد.",
    }[r.stars]
    lines = [
        f"⚔️ {bold('گزارش نبرد – شهر ' + r.defender_city)}", "", *r.log, "",
        verdict,
        _stars(r.stars),
        f"📊 میزان تخریب: {fa(round(r.destruction * 100))}٪",
        f"🏆 جام: {'+' if r.trophies >= 0 else '-'}{fa(abs(r.trophies))}",
        "",
        f"🎁 {bold('غنائم')}", *_loot_lines(r.loot), "",
        f"🩸 {bold('تلفات لشکر شما')}", *_troop_lines(r.lost),
    ]
    if r.xp:
        lines += ["", f"⭐ {fa(r.xp)} تجربه برای فرمانده"]
    return "\n".join(lines)


# --- reports -----------------------------------------------------------------------------------------------------------------------
@screen("cityreports")
async def city_reports(c: Ctx) -> Screen:
    rows_db = await c.services.city.reports(c.player)
    lines = [f"📜 {bold('گزارش جنگ‌ها')}", ""]
    rows = []
    if not rows_db:
        lines.append("هنوز نبردی در کار نبوده است.")
    for r in rows_db:
        mine = r["attacker_pid"] == c.player.id
        other = r["defender_name"] if mine else r["attacker_name"]
        tag = "⚔️ حمله به" if mine else ("🆕 حمله‌ی" if not r["seen"] else "🛡️ حمله‌ی")
        rows.append([c.btn(f"{tag} {other} · {r['stars']}⭐", "cityrep", r["id"])])
    rows.append(c.back("city"))
    return Screen("\n".join(lines), rows)


@screen("cityrep")
async def city_report(c: Ctx) -> Screen:
    row = await c.services.city.report(c.player, _int(c.a))
    data = json.loads(row["data"])
    mine = row["attacker_pid"] == c.player.id
    if mine:
        head = f"⚔️ {bold('گزارش حمله‌ی شما به شهر ' + row['defender_name'])}"
        lines = [head, "", *data["log"], "", _stars(row["stars"]), f"📊 میزان تخریب: {fa(round(row['destruction'] * 100))}٪",
                 "", f"🎁 {bold('غنائم')}", *_loot_lines(data["loot"]), "", f"🩸 {bold('تلفات لشکر شما')}", *_troop_lines(data["att_lost"])]
    else:
        won = row["stars"] == 0
        lines = [
            f"📜 {bold('گزارش حمله به شهر ' + row['defender_name'])}", "",
            f"🗡️ مهاجم: {row['attacker_name']}",
            f"📊 میزان تخریب: {fa(round(row['destruction'] * 100))}٪",
            f"🏁 نتیجه: {'شما دفاع کردید و مهاجم ناکام ماند' if won else 'شکست مدافع'}",
            "", f"🎁 {bold('منابع ازدست‌رفته')}", *_loot_lines(data["loot"]),
            "", f"🩸 {bold('سربازان ازدست‌رفته')}", *_troop_lines(data["def_lost"]),
            "", f"🔰 سپر دفاعی: {duration(row['shield']) if row['shield'] else 'بدون سپر'}",
            f"🏆 جام: {'+' if row['def_trophies'] >= 0 else '-'}{fa(abs(row['def_trophies']))}",
        ]
    rows = []
    if not mine:
        rows.append([c.btn("🔥 انتقام", "cityrevenge", row["id"], style="danger")])
    rows.append(c.back("cityreports"))
    return Screen("\n".join(lines), rows)


@screen("cityrevenge")
async def city_revenge(c: Ctx) -> Screen:
    target = await c.services.city.revenge(c.player, _int(c.a))
    rows = [[c.btn("⚔️ حمله به شهر", "cityprep", style="danger")], c.back("cityreports")]
    return Screen(_target_card(target, "انتقام!", c.services.ctx.now()), rows)


# --- ranking and map ------------------------------------------------------------------------------------------------------------------
@screen("cityleague")
async def city_league(c: Ctx) -> Screen:
    top, rank, mine = await c.services.city.ranking(c.player)
    lines = [f"🏆 {bold('لیگ و رتبه‌بندی')}", ""]
    if mine is not None:
        emoji, name = d.league_of(mine.trophies)
        lines += [f"{emoji} لیگ شما: {name} · {fa(mine.trophies)} جام", f"🎯 رتبه‌ی شما: {fa(rank or 0)}", ""]
    lines.append(f"👑 {bold('برترین شهرها')}")
    for i, x in enumerate(top):
        lines.append(f"{fa(i + 1)}. {x.flag} {x.name} — {fa(x.trophies)} جام")
    if not top:
        lines.append("هنوز شهری نیست.")
    lines += ["", bold("لیگ‌ها")]
    lines += [f"{e} {n} — از {fa(floor)} جام" for floor, e, n in d.LEAGUES]
    return Screen("\n".join(lines), [c.back("city")])


@screen("citymap")
async def city_map(c: Ctx) -> Screen:
    near = await c.services.city.neighbours(await c.refresh())
    now = c.services.ctx.now()
    lines = [f"🗺️ {bold('نقشه جهان')}", "", "شهرهایی که قدرتی نزدیک به شما دارند:", ""]
    for x in near:
        lines.append(f"{x.flag} {x.name} · قلعه {fa(x.castle)} · دفاع {fa(x.defense_power)}" + (" · سپردار" if x.shielded(now) else ""))
    if not near:
        lines.append("هنوز شهر دیگری بنا نشده است.")
    lines += ["", "برای حمله، از «حمله به شهرها» جستجو بزنید؛ شهرهای سپردار را نمی‌شود هدف گرفت."]
    rows = [[c.btn("🗡️ حمله به شهرها", "cityatk", style="danger")], c.back("city")]
    return Screen("\n".join(lines), rows)



# --- the realm talks to its ruler on its own -------------------------------------------------------------------------------
async def processor(bot, services: Services, interval: float = 120.0) -> None:  # noqa: ANN001
    """Every couple of minutes: send the hunger, full-storage, finished-training and ended-shield messages that are due."""
    while True:
        try:
            for alert in await services.city.collect_alerts():
                with contextlib.suppress(BaleAPIError):
                    await bot.send_message(
                        alert.uid, alert.text, buttons=[[keyboards.panel_button("🏰 رفتن به فرمانروایی", "city", alert.uid)]]
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("city alerts failed")
        await asyncio.sleep(interval)


# --- the queue and crystals ---------------------------------------------------------------------------------------------------------
@screen("cityqueue")
async def city_queue(c: Ctx) -> Screen:
    city, now = await _city(c), c.services.ctx.now()
    lines = [f"⏱️ {bold('صف کارها')}", LINE, f"🏗️ {bold('ساخت‌وساز')}"]
    rows = []
    for w in city.builds:
        b = d.get_building(w.kind)
        lines.append(f"{b.emoji} {b.name} ← سطح {fa(w.level)} · {duration(w.ready_at - now)} مانده")
        rows.append([c.btn(f"💎 تکمیل {b.name} · {fa(d.rush_crystals(w.ready_at - now))} کریستال", "cityrushq", "build", w.id)])
    if not city.builds:
        lines.append("سازندگان بیکارند؛ از «ساختمان‌ها» کاری بسپارید.")
    lines += ["", f"⚔️ {bold('آموزش سربازان')}"]
    for w in city.training:
        t = d.get_troop(w.kind)
        lines.append(f"{t.emoji} {fa(w.qty)} {t.name} · {duration(w.ready_at - now)} مانده")
        rows.append([c.btn(f"💎 تکمیل {t.name} · {fa(d.rush_crystals(w.ready_at - now))} کریستال", "cityrushq", "train", w.id)])
    if not city.training:
        lines.append("آموزشگاه خالی است.")
    total = c.services.city.rush_price(city, now)
    lines += ["", f"💎 کریستال شما: {fa(c.player.crystal)}", "هر ۱۰ دقیقه کار، یک کریستال است."]
    if total:
        rows.insert(0, [c.btn(f"⚡ تکمیل همه‌ی کارها · {fa(total)} کریستال", "cityrushq", "all", 0, style="success")])
    rows.append(c.back("city"))
    return Screen("\n".join(lines), rows)


@screen("cityrushq")
async def city_rush_ask(c: Ctx) -> Screen:
    city, now, p = await _city(c), c.services.ctx.now(), await c.refresh()
    what, item = c.a, _int(c.b or "0")
    price = c.services.city.rush_price(city, now, what, item)
    if price == 0:
        raise GameError("این کار همین حالا تمام شده یا در صف نیست.")
    names = {"all": "همه‌ی کارهای صف", "build": "ساخت‌وساز", "train": "آموزش سربازان"}
    lines = [
        f"💎 {bold('تأیید تکمیل فوری')}", "",
        f"کار: {names[what]}",
        f"💎 بها: {bold(fa(price))} کریستال",
        "",
        f"کریستال شما: {fa(p.crystal)} ← {fa(max(0, p.crystal - price))}",
    ]
    if p.crystal < price:
        return Screen("\n".join(lines + ["", f"💸 {fa(price - p.crystal)} کریستال کم دارید."]), [c.back("cityqueue")])
    return Screen("\n".join(lines + ["", "همین لحظه تمام شود؟"]), [[c.btn("✅ بله، تمامش کن", "cityrushok", what, item, style="success"), c.btn("↩️ نه", "cityqueue")]])


@screen("cityrushok")
async def city_rush_do(c: Ctx) -> Screen:
    _, price = await c.services.city.rush(c.player, c.a, _int(c.b or "0"))
    await c.refresh()
    shown = await city_queue(c)
    shown.toast, shown.alert = f"⚡ با {fa(price)} کریستال همین لحظه تمام شد!", True
    return shown


# --- settings -----------------------------------------------------------------------------------------------------------------------------
@screen("citycfg")
async def city_settings(c: Ctx) -> Screen:
    city = await _city(c)
    text = "\n".join([
        f"⚙️ {bold('تنظیمات شهر')}", LINE,
        f"{city.flag} شهر {city.name}",
        f"🔔 پیام‌های خودکار: {'روشن' if city.alerts else 'خاموش'}",
        "گرسنگی، پر شدن انبار، پایان ساخت و آموزش و پایان سپر را خودم خبر می‌دهم.",
        "هشدار حمله دشمن همیشه می‌آید.",
    ])
    rows = [
        [c.btn("🔕 خاموش کردن پیام‌ها" if city.alerts else "🔔 روشن کردن پیام‌ها", "citycfgal", "0" if city.alerts else "1")],
        [c.btn("🚩 تغییر پرچم شهر", "citycfgflag")],
        [c.btn("🧭 خلاصه‌ی وضعیت", "citymine")],
        c.back("city"),
    ]
    return Screen(text, rows)


@screen("citycfgal")
async def city_alerts_toggle(c: Ctx) -> Screen:
    await c.services.city.set_alerts(c.player, c.a == "1")
    shown = await city_settings(c)
    shown.toast = "🔔 پیام‌های خودکار روشن شد" if c.a == "1" else "🔕 پیام‌های خودکار خاموش شد"
    return shown


@screen("citycfgflag")
async def city_flag_menu(c: Ctx) -> Screen:
    city = await _city(c)
    rows = keyboards.grid([c.btn(f"{e} {n}", "citycfgflagset", i) for i, (e, n) in enumerate(d.FLAGS)], 3)
    rows.append(c.back("citycfg"))
    return Screen(f"🚩 {bold('پرچم شهر')}\n\nپرچم فعلی: {city.flag}\nیک پرچم تازه برگزینید (رایگان) 👇", rows)


@screen("citycfgflagset")
async def city_flag_set(c: Ctx) -> Screen:
    index = _int(c.a)
    if not 0 <= index < len(d.FLAGS):
        raise GameError("این پرچم وجود ندارد.")
    await c.services.city.set_flag(c.player, d.FLAGS[index][0])
    shown = await city_settings(c)
    shown.toast = f"{d.FLAGS[index][0]} پرچم شهر عوض شد"
    return shown
