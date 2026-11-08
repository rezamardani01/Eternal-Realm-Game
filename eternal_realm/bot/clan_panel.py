"""Clan (خاندان) screens: found or join one, see and manage members, give ranks, fill the treasury."""

from __future__ import annotations

from dataclasses import replace

from baleropy import Router
from baleropy.types import CallbackQuery

from ..game.services.clans import DONATION_STEPS, ROLES, ClanView, role_power
from ..shared.errors import GameError
from ..shared.text import bold, duration, fa
from . import keyboards
from .callbacks import ClanCb
from .panel import PER_PAGE, Ctx, Screen, _int, _nav, _page, screen
from .services import Services

router = Router(name="clans")
LINE = "─" * 12


def _role_label(role: str) -> str:
    emoji, title, _ = ROLES[role]
    return f"{emoji} {title}"


def clan_text(view: ClanView, mention: bool = False) -> str:
    door = "باز (هر کسی می‌تواند بپیوندد)" if view.open else "بسته (فقط با دعوت)"
    lines = [
        f"🏯 {bold('خاندان ' + view.name)}",
        "",
        f"👑 رهبر: {view.leader_mention if mention else view.leader}",
        f"⭐ سطح خاندان: {fa(view.level)}",
        f"👥 اعضا: {fa(view.size)} از {fa(view.capacity)}",
        f"💪 قدرت (جمع سطح اعضا): {fa(view.power)}",
        f"🪙 خزانه: {fa(view.treasury)} سکه",
        f"🚪 در خاندان: {door}",
    ]
    return "\n\n".join(lines)


# --- home of the clan ---------------------------------------------------------------------------
@screen("clan")
async def clan(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        price = c.services.ctx.balance.clan_create_gold
        text = (
            f"🏯 {bold('خاندان')}\n\n"
            "خاندان یعنی گروهی از قهرمانان که با هم می‌مانند، به خزانه‌ی مشترک کمک می‌کنند و سطح خاندان را بالا می‌برند.\n\n"
            f"برای ساختن خاندان خودتان بنویسید:\n«ساخت خاندان نام‌دلخواه»\nهزینه: {bold(fa(price))} سکه\n\n"
            "یا به یکی از خاندان‌های باز بپیوندید 👇"
        )
        rows = [
            [c.btn("🔎 فهرست خاندان‌ها", "clanlist", "0", style="primary")],
            [c.btn("🏆 برترین خاندان‌ها", "clantop")],
            c.back("home"),
        ]
        return Screen(text, rows)
    rows = [
        [c.btn("👥 اعضا", "clanmembers", "0", style="primary"), c.btn("💰 کمک به خزانه", "clandonate")],
        [c.btn("🏆 برترین خاندان‌ها", "clantop"), c.btn("⚔️ جنگ خاندان‌ها", "clanwar")],
    ]
    if role_power(mine.my_role or "member") >= 2:
        rows.append([c.btn("⚙️ مدیریت خاندان", "clanset")])
    rows.append([c.btn("🚪 خروج از خاندان", "clanleaveq")])
    rows.append(c.back("home"))
    role = _role_label(mine.my_role or "member")
    return Screen(clan_text(mine, c.is_group) + f"\n\n{role}: مقام شما", rows)


# --- members ---------------------------------------------------------------------------------------
@screen("clanmembers")
async def clan_members(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    people = await c.services.clans.members(mine.id)
    chunk, has_prev, has_next = _page(people, _int(c.a or "0"))
    rows = [
        [c.btn(f"{ROLES[m['role']][0]} {m['name']} · سطح {fa(m['level'])}", "clanmember", m["player_id"])]
        for m in chunk
    ]
    nav = _nav(c, "clanmembers", _int(c.a or "0"), has_prev, has_next)
    if nav:
        rows.append(nav)
    rows.append(c.back("clan"))
    text = (
        f"👥 {bold('اعضای خاندان ' + mine.name)}\n\n"
        f"{fa(mine.size)} عضو از {fa(mine.capacity)}.\n\n"
        "روی هر نفر بزنید تا مقامش را ببینید و مدیریتش کنید 👇"
    )
    return Screen(text, rows)


async def _member_row(c: Ctx, player_id: int):  # noqa: ANN202
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    for m in await c.services.clans.members(mine.id):
        if m["player_id"] == player_id:
            return mine, m
    raise GameError("این فرمانده دیگر عضو خاندان شما نیست.")


@screen("clanmember")
async def clan_member(c: Ctx) -> Screen:
    pid = _int(c.a)
    mine, m = await _member_row(c, pid)
    text = (
        f"{ROLES[m['role']][0]} {bold(m['name']) if not c.is_group else '[' + m['name'] + '](uid:' + str(m['platform_user_id']) + ')'}\n\n"
        f"🎖️ مقام: {ROLES[m['role']][1]}\n\n"
        f"⭐ سطح: {fa(m['level'])}\n\n"
        f"🪙 کمک به خزانه: {fa(m['donated'])} سکه"
    )
    rows = []
    mypower = role_power(mine.my_role or "member")
    if pid != c.player.id and mypower >= 2 and role_power(m["role"]) < mypower:
        for role, (emoji, title, power) in ROLES.items():
            if role != "leader" and power < mypower and role != m["role"]:
                rows.append([c.btn(f"{emoji} مقام {title}", "clanrole", pid, role)])
        rows.append([c.btn("🚫 اخراج از خاندان", "clankq", pid, style="danger")])
    if pid != c.player.id and mine.my_role == "leader":
        rows.append([c.btn("👑 واگذاری رهبری", "clanxq", pid)])
    rows.append(c.back("clanmembers", "🔙 بازگشت", "0"))
    return Screen(text, rows)


@screen("clanrole")
async def clan_role(c: Ctx) -> Screen:
    title = await c.services.clans.set_role(c.player, _int(c.a), c.b)
    shown = await clan_member(c)
    shown.toast = f"🎖️ مقام «{title}» داده شد"
    return shown


@screen("clankq")
async def clan_kick_ask(c: Ctx) -> Screen:
    _, m = await _member_row(c, _int(c.a))
    text = f"🚫 {bold('اخراج ' + m['name'])}\n\nمطمئن هستید؟ او از خاندان بیرون می‌رود و باید دوباره به آن بپیوندد."
    return Screen(text, [[c.btn("🚫 بله، اخراج", "clankick", c.a, style="danger"), c.btn("↩️ نه", "clanmember", c.a)]])


@screen("clankick")
async def clan_kick(c: Ctx) -> Screen:
    name = await c.services.clans.kick(c.player, _int(c.a))
    shown = await clan_members(replace(c, a="0"))
    shown.toast = f"🚫 {name} از خاندان اخراج شد"
    return shown


@screen("clanxq")
async def clan_transfer_ask(c: Ctx) -> Screen:
    _, m = await _member_row(c, _int(c.a))
    text = (
        f"👑 {bold('واگذاری رهبری به ' + m['name'])}\n\n"
        "او رهبر خاندان می‌شود و شما معاون می‌مانید. این کار را فقط رهبر تازه می‌تواند برگرداند."
    )
    return Screen(text, [[c.btn("👑 بله، واگذار کن", "clanxfer", c.a, style="danger"), c.btn("↩️ نه", "clanmember", c.a)]])


@screen("clanxfer")
async def clan_transfer(c: Ctx) -> Screen:
    name = await c.services.clans.transfer(c.player, _int(c.a))
    shown = await clan(c)
    shown.toast = f"👑 رهبری به {name} رسید"
    shown.alert = True
    return shown


# --- management ------------------------------------------------------------------------------------
@screen("clanset")
async def clan_settings(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None or role_power(mine.my_role or "member") < 2:
        raise GameError("مدیریت خاندان کار رهبر و معاون است.")
    door = "بسته کردن در (فقط دعوت)" if mine.open else "باز کردن در (ورود آزاد)"
    text = (
        f"⚙️ {bold('مدیریت خاندان')}\n\n"
        f"در خاندان الان {'باز' if mine.open else 'بسته'} است.\n\n"
        "برای دعوت یک نفر، روی پیامش در گروه ریپلای کنید و بنویسید «دعوت خاندان»."
    )
    rows = [[c.btn("🚪 " + door, "clandoor", "0" if mine.open else "1")]]
    if mine.my_role == "leader":
        rows.append([c.btn("💥 منحل کردن خاندان", "clandisq", style="danger")])
    rows.append(c.back("clan"))
    return Screen(text, rows)


@screen("clandoor")
async def clan_door(c: Ctx) -> Screen:
    await c.services.clans.set_open(c.player, c.a == "1")
    shown = await clan_settings(c)
    shown.toast = "🚪 در خاندان تغییر کرد"
    return shown


@screen("clandisq")
async def clan_disband_ask(c: Ctx) -> Screen:
    text = f"💥 {bold('منحل کردن خاندان')}\n\nهمه‌ی اعضا بیرون می‌روند و خزانه از بین می‌رود. این کار برگشت ندارد. مطمئن هستید؟"
    return Screen(text, [[c.btn("💥 بله، منحل شود", "clandisband", style="danger"), c.btn("↩️ نه", "clanset")]])


@screen("clandisband")
async def clan_disband(c: Ctx) -> Screen:
    await c.services.clans.disband(c.player)
    shown = await clan(c)
    shown.toast, shown.alert = "💥 خاندان منحل شد", True
    return shown


@screen("clanleaveq")
async def clan_leave_ask(c: Ctx) -> Screen:
    text = f"🚪 {bold('خروج از خاندان')}\n\nمطمئن هستید؟ برای برگشتن باید دوباره بپیوندید (یا دعوت شوید)."
    return Screen(text, [[c.btn("🚪 بله، خارج شو", "clanleave", style="danger"), c.btn("↩️ نه", "clan")]])


@screen("clanleave")
async def clan_leave(c: Ctx) -> Screen:
    result = await c.services.clans.leave(c.player)
    shown = await clan(c)
    shown.toast = "💥 خاندان بسته شد" if result == "disbanded" else "🚪 از خاندان خارج شدید"
    return shown


# --- treasury --------------------------------------------------------------------------------------
@screen("clandonate")
async def clan_donate(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    need = next((n for n in (1000 * lv * lv for lv in range(1, 60)) if n > mine.donated), mine.donated)
    text = (
        f"💰 {bold('خزانه‌ی خاندان')}\n\n"
        f"🪙 موجودی خزانه: {fa(mine.treasury)} سکه\n\n"
        f"⭐ سطح خاندان: {fa(mine.level)}\n\n"
        f"🎯 برای سطح بعد: {fa(max(0, need - mine.donated))} سکه‌ی دیگر\n\n"
        f"👛 کیف شما: {fa(c.player.gold)} سکه\n\n"
        "هر سطح، جای بیشتری برای عضو تازه باز می‌کند. چقدر کمک می‌کنید؟"
    )
    rows = keyboards.grid([c.btn(f"🪙 {fa(n)}", "clangiveq", n) for n in DONATION_STEPS], 2)
    rows.append(c.back("clan"))
    return Screen(text, rows)


@screen("clangiveq")
async def clan_give_ask(c: Ctx) -> Screen:
    amount = _int(c.a)
    p = await c.refresh()
    mine = await c.services.clans.of(p.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    if p.gold < amount:
        text = (
            f"💸 {bold('موجودی کافی نیست')}\n\nکمک: {fa(amount)} 🪙\nموجودی شما: {fa(p.gold)} 🪙\n"
            f"کمبود: {bold(fa(amount - p.gold))} 🪙"
        )
        return Screen(text, [c.back("clandonate")])
    text = (
        f"💰 {bold('تأیید کمک به خزانه')}\n\n"
        f"مبلغ: {bold(fa(amount))} سکه\n\n"
        f"کیسه‌ی شما: {fa(p.gold)} ← {fa(p.gold - amount)} سکه\n\n"
        f"خزانه‌ی خاندان: {fa(mine.treasury)} ← {fa(mine.treasury + amount)} سکه\n\n"
        "این پول به خزانه می‌رود و پس گرفته نمی‌شود. مطمئنید؟"
    )
    return Screen(text, [[c.btn("✅ بله، کمک کن", "clangive", amount, style="success"), c.btn("↩️ نه", "clandonate")]])


@screen("clancreate")
async def clan_create_do(c: Ctx) -> Screen:
    view = await c.services.clans.create(c.player, c.a)
    price = c.services.ctx.balance.clan_create_gold
    text = (
        f"🏯 {bold('خاندان ' + view.name + ' ساخته شد!')}\n\n"
        f"{c.who(c.player)} نخستین رهبر این خاندان شد و {bold(fa(price))} سکه از کیفش رفت.\n\n"
        "حالا دوستانتان را دعوت کنید (روی پیامشان ریپلای کنید و «دعوت خاندان» بنویسید)."
    )
    return Screen(text, [[c.btn("🏯 پنل خاندان", "clan")]])


@screen("clangive")
async def clan_give(c: Ctx) -> Screen:
    amount = _int(c.a)
    await c.services.clans.donate(c.player, amount)
    await c.refresh()
    shown = await clan_donate(c)
    shown.toast = f"💰 {fa(amount)} سکه به خزانه رفت. سپاس!"
    return shown


# --- browsing other clans -----------------------------------------------------------------------------
@screen("clanlist")
async def clan_list(c: Ctx) -> Screen:
    page = _int(c.a or "0")
    clans, has_next = await c.services.clans.listing(page, PER_PAGE)
    if not clans:
        return Screen(f"🔎 {bold('فهرست خاندان‌ها')}\n\nهنوز خاندانی ساخته نشده. اولین باشید!", [c.back("clan")])
    rows = [
        [c.btn(f"🏯 {v.name} · سطح {fa(v.level)} · {fa(v.size)}/{fa(v.capacity)}", "clanview", v.id)]
        for v in clans
    ]
    nav = _nav(c, "clanlist", page, page > 0, has_next)
    if nav:
        rows.append(nav)
    rows.append(c.back("clan"))
    return Screen(f"🔎 {bold('فهرست خاندان‌ها')}\n\nیکی را انتخاب کنید تا ببینید و بپیوندید 👇", rows)


@screen("clanview")
async def clan_view(c: Ctx) -> Screen:
    view = await c.services.clans.get(_int(c.a))
    if view is None:
        raise GameError("این خاندان دیگر وجود ندارد.")
    rows = []
    if await c.services.clans.of(c.player.id) is None:
        label = "✅ پیوستن" if view.open else "🔒 درِ خاندان بسته است"
        rows.append([c.btn(label, "clanjoin", view.id, style="success" if view.open else None)])
    rows.append(c.back("clanlist", "🔙 بازگشت", "0"))
    return Screen(clan_text(view, c.is_group), rows)


@screen("clanjoin")
async def clan_join(c: Ctx) -> Screen:
    view = await c.services.clans.join(c.player, _int(c.a))
    shown = await clan(c)
    shown.toast, shown.alert = f"🏯 به خاندان {view.name} پیوستید!", True
    return shown


@screen("clantop")
async def clan_top(c: Ctx) -> Screen:
    clans, _ = await c.services.clans.listing(0, 10)
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 {bold('برترین خاندان‌ها')}", ""]
    if not clans:
        lines.append("هنوز خاندانی ساخته نشده.")
    for i, v in enumerate(clans):
        place = medals[i] if i < 3 else f"{fa(i + 1)}."
        lines += [f"{place} {v.name} · سطح {fa(v.level)} · قدرت {fa(v.power)} · {fa(v.size)} عضو", ""]
    return Screen("\n".join(lines).strip(), [c.back("clan")])


# --- the weekly clan war -------------------------------------------------------------------------------
@screen("clanwar")
async def clan_war(c: Ctx) -> Screen:
    view = await c.services.clans.war(c.player)
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        f"⚔️ {bold('جنگ خاندان‌ها')}",
        "",
        "هر هفته خاندان‌ها با هم رقابت می‌کنند. امتیاز از برد دوئل (۱۰ امتیاز) و از باس‌های گروهی "
        "(بر اساس سهم هر عضو) به خاندانتان می‌رسد.",
        "",
        f"⏳ تا پایان این هفته: {duration(view.seconds_left)}",
        "",
    ]
    if not view.week_rows:
        lines.append("این هفته هنوز کسی امتیاز نگرفته. اولین باشید!")
    for i, row in enumerate(view.week_rows):
        place = medals[i] if i < 3 else f"{fa(i + 1)}."
        you = " ← خاندان شما" if row.mine else ""
        lines += [f"{place} {row.name} — {fa(row.points)} امتیاز{you}", ""]
    rows = []
    if view.prize:
        lines += [f"🎁 خاندان شما هفته‌ی پیش جایگاه {fa(view.last_place)} را گرفت! جایزه‌ی شما {fa(view.prize)} سکه است."]
        rows.append([c.btn(f"🎁 دریافت {fa(view.prize)} سکه", "clanprize", style="success")])
    rows.append(c.back("clan"))
    return Screen("\n".join(lines).strip(), rows)


@screen("clanprize")
async def clan_prize(c: Ctx) -> Screen:
    gold = await c.services.clans.claim_war(c.player)
    shown = await clan_war(c)
    shown.toast, shown.alert = f"🎁 {fa(gold)} سکه به کیفتان رسید!", True
    return shown


# --- invitations by button -----------------------------------------------------------------------------
@router.callback_query(ClanCb.filter())
async def on_clan_button(query: CallbackQuery, callback_data: ClanCb, services: Services) -> None:
    if query.from_user.id != callback_data.arg:
        await query.answer("این دعوت برای شما نیست 🙂", show_alert=True)
        return
    player = await services.players.require(query.from_user.id)
    view = await services.clans.join(player, callback_data.id, invited=True)
    if query.message is not None:
        await query.message.edit_text(f"🏯 {bold('به خاندان خوش آمدید')}\n\n{player.mention} به خاندان {view.name} پیوست!")
    await query.answer("🏯 پیوستید!")
