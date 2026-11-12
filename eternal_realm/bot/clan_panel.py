"""Clan (خاندان) screens: found or join one, see and manage members, give ranks, fill the treasury."""

from __future__ import annotations

import contextlib
from dataclasses import replace

from baleropy import F, Router
from baleropy.exceptions import SkipHandler
from baleropy.fsm import FSMContext, State, StatesGroup
from baleropy.types import CallbackQuery, Message
from baleropy.types.markup import _build_inline_markup

from ..game.services.clans import DONATION_STEPS, ROLES, ClanView, Withdrawal, role_power
from ..shared.errors import GameError
from ..shared.text import bold, duration, fa, to_int
from . import keyboards
from .callbacks import ClanCb
from .panel import PER_PAGE, Ctx, Screen, _int, _is_group, _nav, _page, screen
from .services import Services

router = Router(name="clans")
LINE = "─" * 12
FINE_STEPS = (500, 5_000)


class ClanFlow(StatesGroup):
    photo = State()
    amount = State()


#: the picture waiting for the leader's «yes»: player id -> Bale file id
_photos: dict[int, str] = {}


def fine_text(fine: int) -> str:
    return f"{fa(fine)} سکه" if fine else "ندارد"


def _role_label(role: str) -> str:
    emoji, title, _ = ROLES[role]
    return f"{emoji} {title}"


def clan_text(view: ClanView, mention: bool = False) -> str:
    door = "باز (هر کسی می‌تواند بپیوندد)" if view.open else "بسته (فقط با دعوت)"
    lines = [
        f"🏯 {bold('خاندان ' + view.name)}",
        "",
        f"👑 مالک: {view.leader_mention if mention else view.leader}",
        f"⭐ سطح خاندان: {fa(view.level)}",
        f"👥 اعضا: {fa(view.size)} از {fa(view.capacity)}",
        f"💪 قدرت (جمع سطح اعضا): {fa(view.power)}",
        f"🪙 خزانه: {fa(view.treasury)} سکه",
        f"🚪 در خاندان: {door}",
        f"🎓 حداقل سطح عضویت: {fa(view.min_level)}",
        f"⚖️ جریمه‌ی خیانت (خروج): {fine_text(view.exit_fine)}",
    ]
    return "\n".join(lines)


# --- home of the clan ---------------------------------------------------------------------------
@screen("clan")
async def clan(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        price = c.services.ctx.balance.clan_create_gold
        text = (
            f"🏯 {bold('خاندان')}\n\n"
            "قهرمانان کنار هم می‌مانند، به خزانه‌ی مشترک کمک می‌کنند و خاندان را بالا می‌برند.\n\n"
            f"🏗️ ساخت: بنویسید «ساخت خاندان نام‌دلخواه»\n💰 هزینه: {bold(fa(price))} سکه\n\n"
            "👇 یا به یک خاندان باز بپیوندید"
        )
        rows = [
            [c.btn("🔎 فهرست خاندان‌ها", "clanlist", "0", style="primary")],
            [c.btn("🏆 برترین خاندان‌ها", "clantop")],
            c.back("home"),
        ]
        return Screen(text, rows)
    rows = [
        [c.btn("👥 اعضا", "clanmembers", "0", style="primary"), c.btn("💰 کمک به خزانه", "clandonate")],
        [c.btn("⚔️ جنگ خاندان‌ها", "cwar", style="danger"), c.btn("🏅 لیگ هفتگی", "clanwar")],
        [c.btn("🏆 برترین خاندان‌ها", "clantop")],
    ]
    shop_row = [c.btn("🛒 فروشگاه خاندان", "clanshop")]
    if role_power(mine.my_role or "member") >= 2:
        shop_row.append(c.btn("⚙️ تنظیمات خاندان", "clanset"))
    rows.append(shop_row)
    rows.append([c.btn("🚪 خروج از خاندان", "clanleaveq", style="danger")])
    if not c.is_group:  # in a group the clan card ends with the exit button; there is nothing to go «back» to
        rows.append(c.back("home"))
    role = _role_label(mine.my_role or "member")
    khan = await c.services.clans.khan_points(c.player.id)
    text = clan_text(mine, c.is_group) + f"\n\n{role}: مقام شما\n🎖️ خان‌پوینت شما: {fa(khan)}"
    return Screen(text, rows, photo=mine.photo or None)


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
        f"🎖️ مقام: {ROLES[m['role']][1]}\n"
        f"⭐ سطح: {fa(m['level'])}\n"
        f"🪙 کمک به خزانه: {fa(m['donated'])} سکه"
    )
    rows = [[c.btn("👤 پروفایل کامل", "profile", pid, "cm")]]
    mypower = role_power(mine.my_role or "member")
    if pid != c.player.id and mypower >= 2 and role_power(m["role"]) < mypower:
        for role, (emoji, title, power) in ROLES.items():
            if role != "leader" and power < mypower and role != m["role"]:
                rows.append([c.btn(f"{emoji} مقام {title}", "clanrole", pid, role)])
        rows.append([c.btn("🚫 اخراج از خاندان", "clankq", pid, style="danger")])
    if pid != c.player.id and mine.my_role == "leader":
        rows.append([c.btn("👑 واگذاری مالکیت", "clanxq", pid)])
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
        f"👑 {bold('واگذاری مالکیت به ' + m['name'])}\n\n"
        "او مالک خاندان می‌شود و شما قائم‌مقام می‌مانید. این کار را فقط مالک تازه می‌تواند برگرداند."
    )
    return Screen(text, [[c.btn("👑 بله، واگذار کن", "clanxfer", c.a, style="danger"), c.btn("↩️ نه", "clanmember", c.a)]])


@screen("clanxfer")
async def clan_transfer(c: Ctx) -> Screen:
    name = await c.services.clans.transfer(c.player, _int(c.a))
    shown = await clan(c)
    shown.toast = f"👑 مالکیت به {name} رسید"
    shown.alert = True
    return shown


# --- management ------------------------------------------------------------------------------------
@screen("clanset")
async def clan_settings(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None or role_power(mine.my_role or "member") < 2:
        raise GameError("مدیریت خاندان کار مالک و قائم‌مقام است.")
    door = "بسته کردن در (فقط دعوت)" if mine.open else "باز کردن در (ورود آزاد)"
    leader = mine.my_role == "leader"
    text = [
        f"⚙️ {bold('مدیریت خاندان')}",
        "",
        f"🚪 در خاندان الان {'باز' if mine.open else 'بسته'} است.",
        f"🎓 حداقل سطح عضویت: {fa(mine.min_level)}",
        f"⚖️ جریمه‌ی خیانت: {fine_text(mine.exit_fine)}",
        f"🖼️ عکس خاندان: {'دارد' if mine.photo else 'ندارد'}",
        "",
        "برای دعوت یک نفر، روی پیامش در گروه ریپلای کنید و بنویسید «دعوت خاندان».",
    ]
    if not leader:
        text += ["", "تنظیم عکس، جریمه و سطح عضویت فقط با مالک است."]
    rows = [[c.btn("🚪 " + door, "clandoor", "0" if mine.open else "1")]]
    if leader:
        rows += [
            [c.btn(f"🎓 سطح مورد نیاز عضویت: {fa(mine.min_level)}", "noop")],
            [c.btn("➖", "clanlvl", "dn"), c.btn("➕", "clanlvl", "up")],
            [c.btn(f"⚖️ جریمه‌ی خیانت: {fine_text(mine.exit_fine)}", "noop")],
            [
                c.btn(f"➖ {fa(FINE_STEPS[1])}", "clanfine", -FINE_STEPS[1]),
                c.btn(f"➖ {fa(FINE_STEPS[0])}", "clanfine", -FINE_STEPS[0]),
                c.btn(f"➕ {fa(FINE_STEPS[0])}", "clanfine", FINE_STEPS[0]),
                c.btn(f"➕ {fa(FINE_STEPS[1])}", "clanfine", FINE_STEPS[1]),
            ],
            [c.btn("🖼️ عکس خاندان", "clanphoto")],
            [c.btn("💥 منحل کردن خاندان", "clandisq", style="danger")],
        ]
    rows.append(c.back("clan"))
    return Screen("\n".join(text), rows)


@screen("clanlvl")
async def clan_level(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    now = await c.services.clans.set_min_level(c.player, mine.min_level + (1 if c.a == "up" else -1))
    shown = await clan_settings(c)
    shown.toast = f"🎓 حداقل سطح عضویت شد {fa(now)}"
    return shown


@screen("clanfine")
async def clan_fine(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    now = await c.services.clans.set_fine(c.player, mine.exit_fine + _int(c.a))
    shown = await clan_settings(c)
    shown.toast = f"⚖️ جریمه‌ی خیانت شد {fine_text(now)}"
    return shown


# --- the clan picture ------------------------------------------------------------------------------
@screen("clanphoto")
async def clan_photo(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None or mine.my_role != "leader":
        raise GameError("عکس خاندان را فقط مالک می‌تواند تنظیم کند.")
    price = c.services.ctx.balance.clan_photo_gold
    text = (
        f"🖼️ {bold('عکس خاندان')}\n\n"
        "با عکس، هر وقت اعضا «خاندان» را بزنند، عکس همراه اطلاعات خاندان و دکمه‌ها نشان داده می‌شود.\n\n"
        f"💰 هزینه‌ی گذاشتن یا عوض کردن عکس: {bold(fa(price))} سکه (هر بار)\n"
        "🗑️ برداشتن عکس رایگان است."
    )
    rows = [[c.btn(f"📤 {'عوض کردن' if mine.photo else 'گذاشتن'} عکس · {fa(price)} سکه", "clanphotoask", style="primary")]]
    if mine.photo:
        rows.append([c.btn("🗑️ برداشتن عکس", "clanphotodelq", style="danger")])
    rows.append(c.back("clanset"))
    return Screen(text, rows, photo=mine.photo or None)


@screen("clanphotoask")
async def clan_photo_ask(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None or mine.my_role != "leader":
        raise GameError("عکس خاندان را فقط مالک می‌تواند تنظیم کند.")
    if c.state is None:
        raise GameError("برای فرستادن عکس از پیوی یا همان گروه شروع کنید.")
    await c.state.set_state(ClanFlow.photo)
    text = f"📤 {bold('عکس خاندان را بفرستید')}\n\nیک عکس بفرستید؛ بعد از دیدن پیش‌نمایش، تأیید می‌کنید و هزینه کم می‌شود."
    return Screen(text, [[c.btn("❌ انصراف", "clanphoto")]])


@screen("clanphotook")
async def clan_photo_ok(c: Ctx) -> Screen:
    file_id = _photos.pop(c.player.platform_user_id, "")
    if not file_id:
        raise GameError("این پیش‌نمایش دیگر معتبر نیست؛ دوباره عکس را بفرستید.")
    price = await c.services.clans.set_photo(c.player, file_id)
    mine = await c.services.clans.of(c.player.id)
    assert mine is not None
    shown = await clan_settings(c)
    shown.text = f"✅ {bold('عکس خاندان تنظیم شد')}\n\n💰 {fa(price)} سکه از کیف شما رفت.\n\n{shown.text}"
    shown.toast = "🖼️ عکس خاندان تنظیم شد"
    return shown


@screen("clanphotono")
async def clan_photo_no(c: Ctx) -> Screen:
    _photos.pop(c.player.platform_user_id, None)
    return await clan_settings(c)


@screen("clanphotodelq")
async def clan_photo_del_ask(c: Ctx) -> Screen:
    text = f"🗑️ {bold('برداشتن عکس خاندان')}\n\nعکس برداشته می‌شود و پولی که قبلاً داده‌اید برنمی‌گردد. مطمئنید؟"
    return Screen(text, [[c.btn("🗑️ بله، بردار", "clanphotodel", style="danger"), c.btn("↩️ نه", "clanphoto")]])


@screen("clanphotodel")
async def clan_photo_del(c: Ctx) -> Screen:
    await c.services.clans.remove_photo(c.player)
    shown = await clan_settings(c)
    shown.toast = "🗑️ عکس خاندان برداشته شد"
    return shown


@router.message(ClanFlow.photo, F.photo)
async def got_clan_photo(message: Message, state: FSMContext, services: Services) -> None:
    user = message.from_user
    assert user is not None
    player = await services.players.require(user.id)
    mine = await services.clans.of(player.id)
    await state.clear()
    if mine is None or mine.my_role != "leader":
        raise GameError("عکس خاندان را فقط مالک می‌تواند تنظیم کند.")
    file_id = message.photo[-1].file_id  # type: ignore[index]
    _photos[user.id] = file_id
    price = services.ctx.balance.clan_photo_gold
    text = (
        f"🖼️ {bold('پیش‌نمایش عکس خاندان')}\n\n"
        f"💰 هزینه: {bold(fa(price))} سکه\n"
        f"کیسه‌ی شما: {fa(player.gold)} ← {fa(max(0, player.gold - price))} سکه\n\n"
        "این عکس برای خاندان گذاشته شود؟"
    )
    rows = [[
        keyboards.panel_button("✅ بله، بگذار", "clanphotook", user.id),
        keyboards.panel_button("❌ نه", "clanphotono", user.id),
    ]]
    await message.bot.send_photo(message.chat.id, file_id, text, message.message_id, _build_inline_markup(rows))


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
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    fine = 0 if mine.my_role == "leader" else mine.exit_fine
    p = await c.refresh()
    lines = [f"🚪 {bold('خروج از خاندان')}", ""]
    if fine:
        lines += [
            f"⚖️ این خاندان برای خروج {bold('جریمه‌ی خیانت')} دارد: {bold(fa(fine))} سکه.",
            "جریمه از کیف شما کم می‌شود و به خزانه‌ی خاندان می‌رود.",
            "",
            f"کیسه‌ی شما: {fa(p.gold)} ← {fa(max(0, p.gold - fine))} سکه",
            "",
        ]
        if p.gold < fine:
            lines.append(f"💸 برای خروج {fa(fine - p.gold)} سکه کم دارید.")
            return Screen("\n".join(lines), [c.back("clan")])
    lines.append("مطمئن هستید؟ برای برگشتن باید دوباره بپیوندید (یا دعوت شوید).")
    return Screen("\n".join(lines), [[c.btn("🚪 بله، خارج شو", "clanleave", style="danger"), c.btn("↩️ نه", "clan")]])


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
    donors = sorted((m for m in await c.services.clans.members(mine.id) if m["donated"] > 0), key=lambda m: -m["donated"])[:5]
    board = "".join(f"\n{('🥇', '🥈', '🥉', '🏅', '🏅')[i]} {m['name']} — {fa(m['donated'])} سکه" for i, m in enumerate(donors))
    text = (
        f"💰 {bold('خزانه‌ی خاندان')}\n\n"
        f"🪙 موجودی خزانه: {fa(mine.treasury)} سکه\n"
        f"⭐ سطح خاندان: {fa(mine.level)}\n"
        f"🎯 برای سطح بعد: {fa(max(0, need - mine.donated))} سکه‌ی دیگر\n\n"
        f"👛 کیف شما: {fa(c.player.gold)} سکه\n\n"
        + (f"🏆 {bold('برترین اهداکنندگان')}{board}\n\n" if board else "")
        + "هر سطح، جای بیشتری برای عضو تازه باز می‌کند. چقدر کمک می‌کنید؟"
    )
    rows = keyboards.grid([c.btn(f"🪙 {fa(n)}", "clangiveq", n) for n in DONATION_STEPS], 2)
    if not c.is_group:  # the amount is typed, which only works in the private chat
        rows.append([c.btn("📤 برداشت از خزانه", "clanwd")])
    if mine.my_role == "leader":
        waiting = len(await c.services.clans.pending_withdrawals(c.player))
        if waiting:
            rows.append([c.btn(f"📥 درخواست‌های برداشت ({fa(waiting)})", "clanwdlist", style="primary")])
    rows.append(c.back("clan"))
    return Screen(text, rows)


# --- withdrawing from the treasury: a member asks, the owner answers ------------------------------------------
async def _tell(bot, user_id: int, text: str, rows=None) -> None:  # noqa: ANN001, ANN202 - Bot
    """Message a player in the private chat; one who never opened it cannot be told, and that is all."""
    if not user_id:
        return
    with contextlib.suppress(Exception):
        await bot.send_message(user_id, text, buttons=rows) if rows else await bot.send_message(user_id, text)


def _ask_owner(w: Withdrawal) -> tuple[str, list]:
    text = (
        f"📥 {bold('درخواست برداشت از خزانه')}\n\n"
        f"🙋 {bold(w.player_name)} (سطح {fa(w.player_level)}) از خزانه‌ی خاندان {bold(w.clan_name)} "
        f"{bold(fa(w.amount))} سکه می‌خواهد.\n"
        f"🪙 موجودی خزانه: {fa(w.treasury)} سکه\n\n"
        "تأیید کنید تا سکه به او داده شود و از خزانه کم شود؛ یا رد کنید."
    )
    rows = [[
        keyboards.panel_button("✅ تأیید", "clanwdok", w.leader_user_id, str(w.id)),
        keyboards.panel_button("❌ رد", "clanwdno", w.leader_user_id, str(w.id)),
    ]]
    return text, rows


@screen("clanwd")
async def clan_withdraw(c: Ctx) -> Screen:
    mine = await c.services.clans.of(c.player.id)
    if mine is None:
        raise GameError("شما عضو هیچ خاندانی نیستید.")
    waiting = await c.services.clans.my_withdrawal(c.player)
    if waiting is not None:
        text = (
            f"⏳ {bold('درخواست شما منتظر مالک است')}\n\n"
            f"مبلغ: {bold(fa(waiting.amount))} سکه\n"
            "وقتی مالک جواب بدهد، همین‌جا خبر می‌گیرید. می‌توانید آن را لغو کنید."
        )
        return Screen(text, [[c.btn("🗑️ لغو درخواست", "clanwdcancel", waiting.id, style="danger")], c.back("clandonate")])
    if c.state is None or c.is_group:
        raise GameError("برای نوشتن مقدار، در پیوی ربات به همین بخش بیایید.")
    await c.state.set_state(ClanFlow.amount)
    owner = mine.my_role == "leader"
    text = (
        f"📤 {bold('برداشت از خزانه')}\n\n"
        f"🪙 موجودی خزانه: {fa(mine.treasury)} سکه\n\n"
        "چند سکه لازم دارید؟ فقط یک عدد بنویسید؛ مثلاً: ۵۰۰۰\n"
        + ("به‌عنوان مالک، سکه همان لحظه به کیفتان می‌آید." if owner else "درخواستتان برای مالک خاندان می‌رود؛ اگر تأیید کند سکه به کیفتان می‌آید.")
    )
    return Screen(text, [[c.btn("❌ انصراف", "clandonate")]])


@router.message(ClanFlow.amount, F.text)
async def got_withdraw_amount(message: Message, state: FSMContext, services: Services) -> None:
    amount = to_int((message.text or "").strip())
    if amount is None:
        if _is_group(message):
            raise SkipHandler  # ordinary chat or a game word: let the command router see it
        raise GameError("فقط یک عدد بنویسید؛ مثلاً: ۵۰۰۰")
    user = message.from_user
    assert user is not None
    player = await services.players.require(user.id)
    made = await services.clans.request_withdrawal(player, amount)
    await state.clear()
    back = [[keyboards.panel_button("💰 خزانه‌ی خاندان", "clandonate", user.id)]]
    if made.instant:
        await message.answer(
            f"✅ {bold(fa(amount))} سکه از خزانه‌ی خاندان برداشته شد و به کیف شما رفت.\n🪙 خزانه: {fa(made.treasury - amount)} سکه",
            buttons=back,
        )
        return
    await message.answer(
        f"📨 {bold('درخواست برداشت فرستاده شد')}\n\n{bold(fa(amount))} سکه از خزانه‌ی خاندان.\n"
        "وقتی مالک جواب بدهد، همین‌جا خبر می‌گیرید.",
        buttons=back,
    )
    text, rows = _ask_owner(made)
    await _tell(message.bot, made.leader_user_id, text, rows)


@screen("clanwdcancel")
async def clan_withdraw_cancel(c: Ctx) -> Screen:
    await c.services.clans.cancel_withdrawal(c.player, _int(c.a))
    shown = await clan_donate(c)
    shown.toast = "🗑️ درخواست برداشت لغو شد"
    return shown


@screen("clanwdlist")
async def clan_withdraw_list(c: Ctx) -> Screen:
    waiting = await c.services.clans.pending_withdrawals(c.player)
    if not waiting:
        return Screen(f"📥 {bold('درخواست‌های برداشت')}\n\nدرخواستی منتظر شما نیست.", [c.back("clandonate")])
    lines = [f"📥 {bold('درخواست‌های برداشت')}", "", f"🪙 موجودی خزانه: {fa(waiting[0].treasury)} سکه", ""]
    rows = []
    for w in waiting:
        lines.append(f"🙋 {bold(w.player_name)} (سطح {fa(w.player_level)}) — {bold(fa(w.amount))} سکه")
        rows.append([
            c.btn(f"✅ {w.player_name} · {fa(w.amount)}", "clanwdok", w.id, style="success"),
            c.btn("❌ رد", "clanwdno", w.id, style="danger"),
        ])
    rows.append(c.back("clandonate"))
    return Screen("\n".join(lines), rows)


async def _answer(c: Ctx, approve: bool) -> Screen:
    w = await c.services.clans.decide_withdrawal(c.player, _int(c.a), approve)
    bot = c.message.bot if c.message is not None else None
    if w.left:
        toast = f"{w.player_name} دیگر در خاندان نیست؛ درخواستش بسته شد."
    elif approve:
        toast = f"✅ {fa(w.amount)} سکه به {w.player_name} داده شد"
        if bot is not None:
            await _tell(
                bot, w.member_user_id,
                f"✅ {bold('درخواست برداشت شما تأیید شد')}\n\n{bold(fa(w.amount))} سکه از خزانه‌ی خاندان {bold(w.clan_name)} به کیف شما رفت.",
            )
    else:
        toast = f"❌ درخواست {w.player_name} رد شد"
        if bot is not None:
            await _tell(
                bot, w.member_user_id,
                f"❌ {bold('درخواست برداشت شما رد شد')}\n\nمالک خاندان {bold(w.clan_name)} درخواست برداشت {fa(w.amount)} سکه را رد کرد.",
            )
    shown = await clan_withdraw_list(c)
    shown.toast = toast
    return shown


@screen("clanwdok")
async def clan_withdraw_ok(c: Ctx) -> Screen:
    return await _answer(c, True)


@screen("clanwdno")
async def clan_withdraw_no(c: Ctx) -> Screen:
    return await _answer(c, False)


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
        f"{c.who(c.player)} نخستین مالک این خاندان شد و {bold(fa(price))} سکه از کیفش رفت.\n\n"
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
        rows.append([c.btn(label, "clanjoinq", view.id, style="success" if view.open else None)])
    rows.append(c.back("clanlist", "🔙 بازگشت", "0"))
    return Screen(clan_text(view, c.is_group), rows, photo=view.photo or None)


@screen("clanjoinq")
async def clan_join_ask(c: Ctx) -> Screen:
    view = await c.services.clans.get(_int(c.a))
    if view is None:
        raise GameError("این خاندان دیگر وجود ندارد.")
    if not view.open:
        raise GameError("درهای این خاندان بسته است؛ فقط با دعوت مالک یا قائم‌مقام می‌شود وارد شد.")
    p = await c.refresh()
    lines = [f"🏯 {bold('پیوستن به خاندان ' + view.name)}", "", f"🎓 حداقل سطح عضویت: {fa(view.min_level)} (سطح شما: {fa(p.level)})"]
    if view.exit_fine:
        lines += [
            f"⚖️ {bold('جریمه‌ی خیانت')}: {bold(fa(view.exit_fine))} سکه",
            "اگر بعداً بخواهید از این خاندان خارج شوید، باید این مبلغ را به خزانه‌اش بپردازید.",
        ]
    else:
        lines.append("⚖️ جریمه‌ی خیانت: ندارد؛ هر وقت خواستید می‌توانید آزادانه بروید.")
    rows = [c.back("clanview", "🔙 بازگشت", view.id)]
    if p.level < view.min_level:
        lines += ["", f"🔒 هنوز به سطح {fa(view.min_level)} نرسیده‌اید."]
    else:
        lines += ["", "با این شرایط می‌پیوندید؟"]
        rows = [[c.btn("✅ بله، می‌پیوندم", "clanjoin", view.id, style="success"), c.btn("↩️ نه", "clanview", view.id)]]
    return Screen("\n".join(lines), rows)


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
        f"🏅 {bold('لیگ هفتگی خاندان‌ها')}",
        "",
        "هر هفته خاندان‌ها بر سر جایگاه نخست رقابت می‌کنند. امتیاز از برد دوئل (۱۰ امتیاز)، باس‌های گروهی "
        "(بر اساس سهم هر عضو) و ستاره‌های «جنگ خاندان‌ها» به خاندانتان می‌رسد.",
        "",
        f"⏳ تا پایان این هفته: {duration(view.seconds_left)}",
        "",
    ]
    if not view.week_rows:
        lines.append("این هفته هنوز کسی امتیاز نگرفته. اولین باشید!")
    for i, row in enumerate(view.week_rows):
        place = medals[i] if i < 3 else f"{fa(i + 1)}."
        you = " ← خاندان شما" if row.mine else ""
        lines.append(f"{place} {row.name} — {fa(row.points)} امتیاز{you}")
    rows = []
    if view.prize:
        lines += [f"🎁 خاندان شما هفته‌ی پیش جایگاه {fa(view.last_place)} را گرفت! جایزه‌ی شما {fa(view.prize)} سکه است."]
        rows.append([c.btn(f"🎁 دریافت {fa(view.prize)} سکه", "clanprize", style="success")])
    rows.append([c.btn("⚔️ جنگ خاندان‌ها", "cwar")])
    rows.append(c.back("clan"))
    return Screen("\n".join(lines).strip(), rows)


@screen("clanprize")
async def clan_prize(c: Ctx) -> Screen:
    gold = await c.services.clans.claim_war(c.player)
    shown = await clan_war(c)
    shown.toast, shown.alert = f"🎁 {fa(gold)} سکه، کریستال و بوست ۲۴ ساعته‌ی جایزه‌ی لیگ به کیفتان رسید!", True
    return shown


# --- the clan shop: Khan points for valuable goods ---------------------------------------------------
@screen("clanshop")
async def clan_shop(c: Ctx) -> Screen:
    offers, points = await c.services.clans.shop(c.player)
    lines = [
        f"🛒 {bold('فروشگاه خاندان')}",
        "",
        f"🎖️ خان‌پوینت شما: {bold(fa(points))}",
        "خان‌پوینت را از جنگ خاندان‌ها، دوئل با اعضای خاندان‌های دیگر و جایزه‌ی لیگ هفتگی می‌گیرید.",
        "کالاها هر روز عوض می‌شوند و هر کالا را روزی یک بار می‌توانید بخرید.",
        "",
    ]
    rows = []
    for offer, bought in offers:
        if bought:
            lines.append(f"✅ {offer.title} — خریده شد")
        else:
            lines.append(f"{offer.title} — {fa(offer.price)} خان‌پوینت")
            rows.append([c.btn(f"{offer.title} · {fa(offer.price)} 🎖️", "clanshopq", offer.id,
                               style="success" if points >= offer.price else None)])
    rows.append(c.back("clan"))
    return Screen("\n".join(lines), rows)


@screen("clanshopq")
async def clan_shop_ask(c: Ctx) -> Screen:
    from ..game.data.khan_shop import get_offer

    offers, points = await c.services.clans.shop(c.player)
    if c.a not in {o.id for o, bought in offers if not bought}:
        raise GameError("این کالا را امروز خریده‌اید یا در فروشگاه نیست.")
    offer = get_offer(c.a)
    lines = [
        f"🛒 {bold('تأیید خرید')}",
        "",
        f"{offer.title}",
        f"💰 بها: {bold(fa(offer.price))} خان‌پوینت",
        "",
        f"خان‌پوینت شما: {fa(points)} ← {fa(max(0, points - offer.price))}",
    ]
    if points < offer.price:
        lines += ["", f"🔒 {fa(offer.price - points)} خان‌پوینت کم دارید."]
        return Screen("\n".join(lines), [c.back("clanshop")])
    lines += ["", "خریداری شود؟"]
    return Screen("\n".join(lines), [[c.btn("✅ بله، بخر", "clanshopbuy", offer.id, style="success"), c.btn("↩️ نه", "clanshop")]])


@screen("clanshopbuy")
async def clan_shop_buy(c: Ctx) -> Screen:
    offer = await c.services.clans.buy(c.player, c.a)
    shown = await clan_shop(c)
    shown.toast, shown.alert = f"🛒 {offer.title} به کیف شما رسید!", True
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
