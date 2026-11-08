"""The management panel in glass buttons. The owner (or an admin) writes «پنل مدیریت» and manages everything here:
players, groups, clans, sales, broadcasts, the forced channel membership and the audit log.

Anything that needs typing (a name to search, an amount, a message) uses a one-step text prompt (``AdminFlow``).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import replace

from baleropy import Router
from baleropy.exceptions import BaleAPIError, SkipHandler
from baleropy.fsm import FSMContext, State, StatesGroup
from baleropy.types import FSInputFile, Message

from ..db.repos import players as player_repo
from ..game.data.items import find_item
from ..game.data.pets import PETS
from ..game.services.events import KINDS, EventAction
from ..shared.errors import GameError
from ..shared.jalali import describe
from ..shared.text import bold, fa, headline, to_int
from . import events as events_ui
from . import keyboards
from .commands.owner import OWNER_COMMANDS
from .maintenance import make_backup
from .commands.registry import REGISTRY
from .panel import Ctx, Screen, _nav, screen
from .services import Services

log = logging.getLogger("eternal_realm.admin")
PER = 6

EVENT_NAMES = {
    "mystery_chest": "🎁 صندوقچه‌ی اسرارآمیز", "merchant": "🧳 تاجر دوره‌گرد", "double_xp": "✨ تجربه‌ی دوبرابر",
    "hidden_boss": "🌑 باس مخفی", "hidden_chest": "🗝️ صندوقچه‌ی مخفی", "invasion": "🚨 تهاجم هیولاها", "meteor": "☄️ شهاب‌سنگ",
    "gold_rain": "🌧️ باران سکه", "spring": "💧 چشمه‌ی برکت", "wheel": "🎡 چرخ شانس", "egg": "🥚 تخم اژدها",
}


class AdminFlow(StatesGroup):
    waiting = State()


#: the broadcast text waiting for the admin's «yes» (the panel clears the prompt state on every tap)
_drafts: dict[int, str] = {}
#: the message the admin wants to forward to every group: (chat id, message id)
_forwards: dict[int, tuple[int, int]] = {}
#: the text for the private-message broadcast to all players
_dm_drafts: dict[int, str] = {}
#: the gift for every player waiting for the admin's «yes»
_gifts: dict[int, dict[str, int]] = {}


def fmt(ts: int | None) -> str:
    if not ts:
        return "—"
    date, _, clock = describe(int(ts))
    return f"{date} {clock}"


def _chat_id(text: str) -> int:
    """Group ids are negative, which ``to_int`` does not read."""
    try:
        return int(text)
    except ValueError:
        raise GameError("این گروه پیدا نشد.") from None


def _guard(c: Ctx) -> None:
    if not c.services.ctx.settings.is_admin(c.owner):
        raise GameError("این بخش فقط برای مدیران است.")


def _back(c: Ctx, screen_: str = "adm", label: str = "🔙 بازگشت", a: object = "", b: object = "") -> list:
    return c.back(screen_, label, a, b)


def _player_line(r) -> str:  # noqa: ANN001
    flags = ("🚫" if r["banned"] else "") + ("💠" if r["vip_until"] else "")
    return f"{r['display_name']} · سطح {fa(r['level'])}{(' ' + flags) if flags else ''}"


# --- home ---------------------------------------------------------------------------------------
@screen("adm")
async def home(c: Ctx) -> Screen:
    _guard(c)
    now = c.services.ctx.now()
    day = (now + 12600) // 86400
    async with c.services.ctx.db.read() as tx:
        one = tx.scalar
        players = await one("SELECT COUNT(*) FROM players", (), 0)
        new_today = await one("SELECT COUNT(*) FROM players WHERE (created_at + 12600) / 86400 = ?", (day,), 0)
        active = await one("SELECT COUNT(DISTINCT player_id) FROM transactions WHERE created_at >= ?", (now - 86400,), 0)
        vip = await one("SELECT COUNT(*) FROM players WHERE vip_until > ?", (now,), 0)
        banned = await one("SELECT COUNT(*) FROM players WHERE banned = 1", (), 0)
        groups = await one("SELECT COUNT(*) FROM groups WHERE enabled = 1", (), 0)
        clans = await one("SELECT COUNT(*) FROM clans", (), 0)
        orders = await one("SELECT COUNT(*) FROM orders WHERE status = 'delivered'", (), 0)
        revenue = await one("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status = 'delivered'", (), 0)
        gold = await one("SELECT COALESCE(SUM(gold), 0) FROM players", (), 0)
        crystal = await one("SELECT COALESCE(SUM(crystal), 0) FROM players", (), 0)
        bosses = await one("SELECT COUNT(*) FROM bosses WHERE status = 'active'", (), 0)
        duels = await one("SELECT COUNT(*) FROM duels WHERE status = 'active'", (), 0)
    text = (
        f"🛠️ {bold('پنل مدیریت قلمرو')}\n\n"
        f"👥 بازیکنان: {bold(fa(players))} (+{fa(new_today)} امروز) · فعال ۲۴ ساعت: {fa(active)}\n"
        f"💠 VIP: {fa(vip)} · 🚫 مسدود: {fa(banned)}\n"
        f"🏢 گروه‌های فعال: {fa(groups)} · 🏯 خاندان‌ها: {fa(clans)}\n"
        f"💰 فروش: {fa(orders)} سفارش · {bold(fa(revenue // 10))} تومان\n"
        f"🪙 سکه در گردش: {fa(gold)} · 💎 کریستال: {fa(crystal)}\n"
        f"🐉 باس زنده: {fa(bosses)} · ⚔️ دوئل جاری: {fa(duels)}\n\n"
        "یک بخش را انتخاب کنید 👇"
    )
    rows = [
        [c.btn("👥 بازیکنان", "admp"), c.btn("🏢 گروه‌ها", "admg")],
        [c.btn("🏯 خاندان‌ها", "admcl"), c.btn("💰 فروش", "admo")],
        [c.btn("📣 همگانی", "admbc"), c.btn("🎁 هدیه‌ی همگانی", "admgf")],
        [c.btn("🔒 عضویت اجباری", "admm"), c.btn("🚧 حالت تعمیر", "admmn")],
        [c.btn("💾 پشتیبان‌گیری", "admbk"), c.btn("🔗 دکمه‌های منو", "admlk")],
        [c.btn("📜 گزارش مدیریت", "adma"), c.btn("🛠️ دستورات مالک", "admc")],
        [c.btn("🔄 بروزرسانی", "adm", style="primary")],
    ]
    return Screen(text, rows)


@screen("admc")
async def owner_commands(c: Ctx) -> Screen:
    _guard(c)
    return Screen(f"🛠️ {bold('دستورات مالک')}\n\n{OWNER_COMMANDS}", [_back(c)])


# --- players ------------------------------------------------------------------------------------
@screen("admp")
async def players_hub(c: Ctx) -> Screen:
    _guard(c)
    text = f"👥 {bold('مدیریت بازیکنان')}\n\nبازیکن را جستجو کنید یا از فهرست‌ها انتخاب کنید 👇"
    rows = [
        [c.btn("🔎 جستجو با نام یا شناسه", "admask", "find", style="primary")],
        [c.btn("🏆 برترین‌ها", "admpl", 0, "top"), c.btn("🆕 تازه‌ترین‌ها", "admpl", 0, "new")],
        [c.btn("💠 VIPها", "admpl", 0, "vip"), c.btn("🚫 مسدودشده‌ها", "admpl", 0, "ban")],
        _back(c),
    ]
    return Screen(text, rows)


_LISTS = {
    "top": ("🏆 برترین بازیکنان", "banned = 0", "level DESC, xp DESC"),
    "new": ("🆕 تازه‌ترین بازیکنان", "1 = 1", "id DESC"),
    "vip": ("💠 بازیکنان VIP", "vip_until > {now}", "vip_until DESC"),
    "ban": ("🚫 مسدودشده‌ها", "banned = 1", "id DESC"),
}


async def _player_list(c: Ctx, title: str, where: str, args: tuple, order: str, kind: str, page: int) -> Screen:
    async with c.services.ctx.db.read() as tx:
        total = await tx.scalar(f"SELECT COUNT(*) FROM players WHERE {where}", args, 0)  # noqa: S608
        rows_ = await tx.fetchall(
            f"SELECT * FROM players WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", (*args, PER, page * PER),  # noqa: S608
        )
    text = f"{title}\n\n" + (f"{fa(total)} بازیکن · صفحه‌ی {fa(page + 1)}\nیکی را انتخاب کنید 👇" if rows_ else "موردی پیدا نشد.")
    buttons = [[c.btn(_player_line(r), "admpc", r["id"])] for r in rows_]
    if nav := _nav(c, "admpl", page, page > 0, (page + 1) * PER < total, kind):
        buttons.append(nav)
    buttons.append(_back(c, "admp"))
    return Screen(text, buttons)


@screen("admpl")
async def players_list(c: Ctx) -> Screen:
    _guard(c)
    kind = c.b if c.b in _LISTS else "top"
    page = max(0, to_int(c.a or "0") or 0)
    title, where, order = _LISTS[kind]
    return await _player_list(c, title, where.format(now=c.services.ctx.now()), (), order, kind, page)


async def _card_player(c: Ctx, pid: int):  # noqa: ANN202
    async with c.services.ctx.db.read() as tx:
        player = await player_repo.get(tx, pid)
    if player is None:
        raise GameError("این بازیکن دیگر وجود ندارد.")
    return player


def _card_text(c: Ctx, p, note: str = "") -> str:  # noqa: ANN001
    now = c.services.ctx.now()
    lines = [
        f"👤 {bold(p.name)}" + (f" — {p.honor}" if p.honor else ""),
        f"{p.race.emoji} {p.race.name} · {p.char_class.emoji} {p.char_class.name} · سطح {fa(p.level)}",
        f"🪙 {fa(p.gold)} · 💎 {fa(p.crystal)}",
        f"🏆 {fa(p.wins)} پیروزی · 💀 {fa(p.losses)} شکست",
        f"🆔 شناسه‌ی بله: {p.platform_user_id}" + (f" · @{p.username}" if p.username else ""),
        f"📅 ثبت‌نام: {fmt(p.created_at)}",
    ]
    if p.vip_until > now:
        lines.append(f"💠 VIP تا {fmt(p.vip_until)}")
    if p.banned:
        lines.append("🚫 این بازیکن مسدود است")
    if note:
        lines = [note, ""] + lines
    return "\n".join(lines)


async def _card(c: Ctx, pid: int, note: str = "") -> Screen:
    p = await _card_player(c, pid)
    rows = [
        [c.btn("🪙 سکه", "admask", "gold", p.id), c.btn("💎 کریستال", "admask", "crystal", p.id)],
        [c.btn("🎒 آیتم", "admask", "item", p.id), c.btn("⭐ سطح", "admask", "level", p.id)],
        [c.btn("💠 VIP", "admask", "vip", p.id), c.btn("🎟️ بلیط طلایی", "admtk", p.id)],
        [c.btn("🐱 حیوان", "admpet", p.id), c.btn("🏷️ عنوان", "admask", "title", p.id)],
        [c.btn("⚡ انرژی پر", "admen", p.id), c.btn("⏱️ ریست زمان‌ها", "admcd", p.id)],
        [c.btn("✉️ پیام به او", "admask", "pmsg", p.id), c.btn("✏️ تغییر نام", "admask", "rename", p.id)],
        [c.btn("✅ رفع مسدودی" if p.banned else "🚫 مسدود کردن", "admban", p.id, style="success" if p.banned else "danger")],
        _back(c, "admp"),
    ]
    return Screen(_card_text(c, p, note), rows)


@screen("admpc")
async def player_card(c: Ctx) -> Screen:
    _guard(c)
    return await _card(c, to_int(c.a) or 0)


@screen("admtk")
async def toggle_ticket(c: Ctx) -> Screen:
    _guard(c)
    pid = to_int(c.a) or 0
    changed = await c.services.admin.grant_ticket(c.owner, pid, True)
    if not changed:  # they have it: take it back
        await c.services.admin.grant_ticket(c.owner, pid, False)
    return await _card(c, pid, "🎟️ بلیط طلایی داده شد ✅" if changed else "🎟️ بلیط طلایی پس گرفته شد")


@screen("admpet")
async def pet_choose(c: Ctx) -> Screen:
    _guard(c)
    pid = to_int(c.a or "") or 0
    if c.b:
        pet = next((p for p in PETS if p.id == c.b), None)
        if pet is None:
            raise GameError("این حیوان وجود ندارد.")
        gave = await c.services.admin.grant_pet(c.owner, pid, pet.id, True)
        if not gave:
            await c.services.admin.grant_pet(c.owner, pid, pet.id, False)
        return await _card(c, pid, f"{pet.emoji} {pet.name} " + ("داده شد ✅" if gave else "پس گرفته شد"))
    rows = [[c.btn(f"{p.emoji} {p.name}", "admpet", pid, p.id)] for p in PETS]
    rows.append(_back(c, "admpc", "🔙 بازگشت", pid))
    return Screen(f"🐱 {bold('حیوان خانگی')}\n\nیکی را بزنید: اگر ندارد داده می‌شود و اگر دارد پس گرفته می‌شود 👇", rows)


@screen("admen")
async def refill(c: Ctx) -> Screen:
    _guard(c)
    pid = to_int(c.a) or 0
    await c.services.admin.refill_energy(c.owner, pid)
    return await _card(c, pid, "⚡ انرژی کامل شد ✅")


@screen("admcd")
async def reset_cooldowns(c: Ctx) -> Screen:
    _guard(c)
    pid = to_int(c.a) or 0
    await c.services.admin.reset_cooldowns(c.owner, pid)
    return await _card(c, pid, "⏱️ زمان‌های انتظار پاک شد ✅")


@screen("admban")
async def ban_ask(c: Ctx) -> Screen:
    _guard(c)
    p = await _card_player(c, to_int(c.a) or 0)
    verb = "رفع مسدودی" if p.banned else "مسدود کردن"
    text = f"{'✅' if p.banned else '🚫'} {bold('تأیید ' + verb)}\n\n{p.name} را {verb} می‌کنید. مطمئنید؟"
    return Screen(text, [[c.btn("✅ بله", "admbanok", p.id, style="danger"), c.btn("↩️ نه", "admpc", p.id)]])


@screen("admbanok")
async def ban_do(c: Ctx) -> Screen:
    _guard(c)
    p = await _card_player(c, to_int(c.a) or 0)
    if c.services.ctx.settings.is_admin(p.platform_user_id):
        raise GameError("مدیران را نمی‌شود مسدود کرد.")
    await c.services.admin.set_ban(c.owner, p.name, not p.banned)
    return await _card(c, p.id, "✅ مسدودی برداشته شد" if p.banned else "🚫 بازیکن مسدود شد")


# --- text prompts ------------------------------------------------------------------------------------
PROMPTS = {
    "find": ("🔎 جستجوی بازیکن", "نام یا بخشی از نام، یوزرنیم یا شناسه‌ی بله‌ی بازیکن را بنویسید.\nمثال: آرش"),
    "gold": ("🪙 سکه", "تعداد سکه را بنویسید (عدد منفی کم می‌کند).\nمثال: 3000"),
    "crystal": ("💎 کریستال", "تعداد کریستال را بنویسید (عدد منفی کم می‌کند).\nمثال: 200"),
    "item": ("🎒 آیتم", "نام آیتم و تعداد را بنویسید.\nمثال: سنگ آهن 399"),
    "level": ("⭐ سطح", "سطح تازه را بنویسید.\nمثال: 40"),
    "vip": ("💠 VIP", "تعداد روز را بنویسید (عدد منفی کم می‌کند).\nمثال: 30"),
    "title": ("🏷️ عنوان", "عنوان تازه را بنویسید (برای پاک کردن بنویسید: -)."),
    "gmsg": ("✉️ پیام به گروه", "متن پیام را بنویسید (۳ تا ۱۰۰۰ حرف)."),
    "bcast": ("📣 پیام همگانی", "متن پیام را بنویسید؛ بعد از دیدن پیش‌نمایش تأیید می‌کنید (۳ تا ۱۰۰۰ حرف)."),
    "fwd": ("📩 فوروارد همگانی", "یک پیام را برای من فوروارد کنید یا بفرستید (متن، عکس، فایل، هر چیزی)؛ همان پیام برای همه‌ی گروه‌های فعال فرستاده می‌شود."),
    "dm": ("📨 پیام به همه‌ی بازیکنان", "متن پیام را بنویسید؛ در پیوی همه‌ی بازیکنان فرستاده می‌شود (۳ تا ۱۰۰۰ حرف)."),
    "gift_gold": ("🪙 سکه برای همه", "تعداد سکه برای هر بازیکن را بنویسید (تا ۱٬۰۰۰٬۰۰۰).\nمثال: 500"),
    "gift_crystal": ("💎 کریستال برای همه", "تعداد کریستال برای هر بازیکن را بنویسید (تا ۱۰٬۰۰۰).\nمثال: 20"),
    "gift_vip": ("💠 VIP برای همه", "تعداد روز VIP برای هر بازیکن را بنویسید (تا ۳۶۵).\nمثال: 7"),
    "mntext": ("🚧 متن حالت تعمیر", "متنی را بنویسید که در زمان تعمیر به بازیکنان نشان داده می‌شود (تا ۳۰۰ حرف)."),
    "pmsg": ("✉️ پیام به بازیکن", "متن پیام را بنویسید؛ در پیوی همین بازیکن فرستاده می‌شود."),
    "rename": ("✏️ تغییر نام قهرمان", "نام تازه را بنویسید (۲ تا ۱۶ حرف، بدون تکراری بودن)."),
    "lk_gt": ("👥 متن دکمه‌ی گروه", "متن تازه‌ی دکمه را بنویسید (تا ۲۸ حرف).\nمثال: 👥 گروه رسمی ما"),
    "lk_gu": ("👥 لینک دکمه‌ی گروه", "لینک گروه را بنویسید (https://... یا @username). برای پنهان کردن دکمه بنویسید: -"),
    "lk_ct": ("📣 متن دکمه‌ی کانال", "متن تازه‌ی دکمه را بنویسید (تا ۲۸ حرف).\nمثال: 📣 کانال رسمی ما"),
    "lk_cu": ("📣 لینک دکمه‌ی کانال", "لینک کانال را بنویسید (https://... یا @username). برای پنهان کردن دکمه بنویسید: -"),
    "chan": ("➕ افزودن کانال", "شناسه‌ی کانال را بنویسید و در صورت دلخواه عنوان.\nمثال: @mychannel کانال رسمی"),
}
_BACK_OF = {
    "find": ("admp", ""), "gmsg": ("admg", ""), "bcast": ("admbc", ""), "chan": ("admm", ""),
    "fwd": ("admbc", ""), "dm": ("admbc", ""), "gift_gold": ("admgf", ""), "gift_crystal": ("admgf", ""),
    "gift_vip": ("admgf", ""), "mntext": ("admmn", ""),
    "lk_gt": ("admlk", ""), "lk_gu": ("admlk", ""), "lk_ct": ("admlk", ""), "lk_cu": ("admlk", ""),
}


@screen("admask")
async def ask(c: Ctx) -> Screen:
    _guard(c)
    op = c.a
    if op not in PROMPTS:
        raise GameError("این گزینه وجود ندارد.")
    if c.state is None:
        raise GameError("برای ورودی متنی از پیوی یا همان گروه شروع کنید.")
    target = c.b
    await c.state.set_state(AdminFlow.waiting)
    await c.state.update_data(op=op, target=target)
    title, hint = PROMPTS[op]
    if op in _BACK_OF:
        undo = c.btn("❌ انصراف", _BACK_OF[op][0])
    elif op == "gmsg":
        undo = c.btn("❌ انصراف", "admgc", target)
    else:
        undo = c.btn("❌ انصراف", "admpc", target)
    return Screen(f"{title}\n\n{hint}\n\n✍️ حالا پیام خود را بفرستید.", [[undo]])


router = Router(name="admin-flow")


async def _result(message: Message, services: Services, text: str, rows: list) -> None:
    await message.answer(headline(text), buttons=rows)


@router.message(AdminFlow.waiting)
async def got_input(message: Message, state: FSMContext, services: Services) -> None:
    user = message.from_user
    assert user is not None
    text = (message.text or message.caption or "").strip()
    is_group = str(getattr(message.chat.type, "value", message.chat.type)) != "private"
    if is_group and message.text and REGISTRY.resolve(text) is not None:
        raise SkipHandler  # a game word, not the answer
    settings = services.ctx.settings
    if not settings.is_admin(user.id):
        await state.clear()
        raise SkipHandler
    data = await state.get_data()
    await state.clear()
    op, target = str(data.get("op")), str(data.get("target") or "")
    admin = services.admin
    uid = user.id
    back_card = [[keyboards.panel_button("🔙 کارت بازیکن", "admpc", uid, target)]] if target.isdigit() else []

    async def done(note: str, rows: list | None = None) -> None:
        await _result(message, services, note, rows if rows is not None else (back_card or [[keyboards.panel_button("🛠️ پنل مدیریت", "adm", uid)]]))

    pid = int(target) if target.lstrip("-").isdigit() and op not in ("gmsg",) else 0
    if op != "fwd" and not message.text:
        raise GameError("برای این کار باید متن بنویسید.")
    if op == "find":
        await _search(message, services, uid, text)
    elif op in ("gold", "crystal"):
        amount = to_int(text)
        if amount is None or amount == 0 or abs(amount) > 100_000_000:
            raise GameError("یک عدد درست بنویسید؛ مثلاً 3000")
        p = await admin.give_currency_id(uid, pid, **{op: amount})
        icon = "🪙 سکه" if op == "gold" else "💎 کریستال"
        await done(f"✅ {fa(amount)} {icon} به {bold(p.name)} اضافه شد." if amount > 0 else f"✅ {fa(-amount)} {icon} از {bold(p.name)} کم شد.")
    elif op == "item":
        words = text.split()
        qty = 1
        if words and (n := to_int(words[-1])) is not None:
            qty, words = n, words[:-1]
        item = find_item(" ".join(words))
        if item is None:
            raise GameError("آیتمی با این نام پیدا نشد؛ نام دقیق فارسی را بنویسید. مثال: سنگ آهن 5")
        p = await admin.give_item_id(uid, pid, item, qty)
        await done(f"✅ {item.label} ×{fa(qty)} به {bold(p.name)} داده شد.")
    elif op == "level":
        level = to_int(text)
        if level is None:
            raise GameError("سطح را با عدد بنویسید؛ مثلاً 40")
        p = await admin.set_level_id(uid, pid, level)
        await done(f"✅ سطح {bold(p.name)} شد {fa(level)}.")
    elif op == "vip":
        days = to_int(text)
        if days is None or days == 0:
            raise GameError("تعداد روز را با عدد بنویسید؛ مثلاً 30")
        until = await admin.set_vip(uid, pid, days)
        await done("✅ VIP برداشته شد." if until == 0 else f"✅ VIP تا {fmt(until)} فعال است.")
    elif op == "title":
        await admin.set_title(uid, pid, "" if text == "-" else text)
        await done("✅ عنوان پاک شد." if text == "-" else f"✅ عنوان شد «{text[:40]}».")
    elif op == "gmsg":
        chat_id = int(target)
        if not 3 <= len(text) <= 1000:
            raise GameError("متن پیام باید بین ۳ تا ۱۰۰۰ حرف باشد.")
        try:
            await message.bot.send_message(chat_id, text)
        except BaleAPIError as exc:
            raise GameError("ارسال به این گروه ممکن نشد؛ شاید ربات از گروه حذف شده است.") from exc
        await admin.log_action(uid, "group_message", str(chat_id))
        await done("✅ پیام به گروه رسید.", [[keyboards.panel_button("🔙 کارت گروه", "admgc", uid, target)]])
    elif op == "bcast":
        if not 3 <= len(text) <= 1000:
            raise GameError("متن پیام باید بین ۳ تا ۱۰۰۰ حرف باشد.")
        _drafts[uid] = text
        ids = await admin.group_ids()
        await done(
            f"📣 {bold('پیش‌نمایش پیام همگانی')}\n\n{text}\n\n— — —\nبه {fa(len(ids))} گروه فعال فرستاده می‌شود. تأیید می‌کنید؟",
            [[keyboards.panel_button("✅ ارسال به همه", "admbcok", uid), keyboards.panel_button("❌ انصراف", "admbc", uid)]],
        )
    elif op == "fwd":
        _forwards[uid] = (message.chat.id, message.message_id)
        ids = await admin.group_ids()
        await done(
            f"📩 {bold('فوروارد همگانی')}\n\nهمین پیام به {fa(len(ids))} گروه فعال می‌رسد.\n"
            "«فوروارد» با نام فرستنده می‌رود و «کپی» بدون نام فرستنده. کدام؟",
            [
                [keyboards.panel_button("↪️ فوروارد", "admfwok", uid, "fwd"), keyboards.panel_button("📋 کپی بدون برچسب", "admfwok", uid, "copy")],
                [keyboards.panel_button("❌ انصراف", "admbc", uid)],
            ],
        )
    elif op == "dm":
        if not 3 <= len(text) <= 1000:
            raise GameError("متن پیام باید بین ۳ تا ۱۰۰۰ حرف باشد.")
        _dm_drafts[uid] = text
        count = len(await admin.player_ids())
        await done(
            f"📨 {bold('پیش‌نمایش پیام به بازیکنان')}\n\n{text}\n\n— — —\nدر پیوی {fa(count)} بازیکن فرستاده می‌شود. تأیید می‌کنید؟",
            [[keyboards.panel_button("✅ ارسال به همه", "admdmok", uid), keyboards.panel_button("❌ انصراف", "admbc", uid)]],
        )
    elif op in ("gift_gold", "gift_crystal", "gift_vip"):
        amount = to_int(text)
        if amount is None or amount <= 0:
            raise GameError("یک عدد درست بنویسید؛ مثلاً 500")
        key = {"gift_gold": "gold", "gift_crystal": "crystal", "gift_vip": "vip_days"}[op]
        limit = {"gold": 1_000_000, "crystal": 10_000, "vip_days": 365}[key]
        if amount > limit:
            raise GameError(f"حداکثر {fa(limit)} است.")
        _gifts[uid] = {key: amount}
        count = len(await admin.player_ids())
        what = {"gold": f"🪙 {fa(amount)} سکه", "crystal": f"💎 {fa(amount)} کریستال", "vip_days": f"💠 {fa(amount)} روز VIP"}[key]
        await done(
            f"🎁 {bold('تأیید هدیه‌ی همگانی')}\n\nبه هر یک از {fa(count)} بازیکن {what} داده می‌شود.\nاین کار برگشت ندارد. مطمئنید؟",
            [[keyboards.panel_button("✅ بله، بده", "admgfok", uid), keyboards.panel_button("❌ انصراف", "admgf", uid)]],
        )
    elif op in ("lk_gt", "lk_gu", "lk_ct", "lk_cu"):
        which = "group" if op.startswith("lk_g") else "channel"
        if op.endswith("t"):
            await admin.set_link(uid, which, text=text)
        else:
            await admin.set_link(uid, which, url=text)
        await done("✅ دکمه ذخیره شد؛ در منوی اصلی پیوی دیده می‌شود.", [[keyboards.panel_button("🔗 دکمه‌های منو", "admlk", uid)]])
    elif op == "mntext":
        enabled, _ = await admin.maintenance()
        await admin.set_maintenance(uid, enabled, text)
        await done("✅ متن حالت تعمیر ذخیره شد.", [[keyboards.panel_button("🚧 حالت تعمیر", "admmn", uid)]])
    elif op == "pmsg":
        async with services.ctx.db.read() as tx:
            player = await player_repo.get(tx, pid)
        if player is None:
            raise GameError("این بازیکن دیگر وجود ندارد.")
        try:
            await message.bot.send_message(player.platform_user_id, headline(f"✉️ {bold('پیام از مدیریت قلمرو')}\n\n{text}"))
        except BaleAPIError as exc:
            raise GameError("پیام نرسید؛ شاید بازیکن ربات را بسته است.") from exc
        await admin.log_action(uid, "player_message", player.name)
        await done(f"✅ پیام برای {bold(player.name)} رسید.")
    elif op == "rename":
        name = await services.players.name_available(text)
        player = await admin.rename_id(uid, pid, name)
        await done(f"✅ نام {bold(player.name)} شد {bold(name)}.")
    elif op == "chan":
        chat, _, title = text.partition(" ")
        enabled, channels = await services.membership.settings()
        listing = [c.as_dict() for c in channels] + [{"chat": chat.strip(), "title": title.strip(), "link": ""}]
        await services.membership.save(enabled, listing)
        await admin.log_action(uid, "membership", f"add {chat}")
        await done("✅ کانال اضافه شد.", [[keyboards.panel_button("🔒 عضویت اجباری", "admm", uid)]])
    else:
        await done("این گزینه دیگر معتبر نیست.")


async def _search(message: Message, services: Services, uid: int, text: str) -> None:
    q = text[:40]
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    async with services.ctx.db.read() as tx:
        rows_ = await tx.fetchall(
            "SELECT * FROM players WHERE display_name LIKE ? ESCAPE '\\' OR CAST(platform_user_id AS TEXT) = ?"
            " OR username LIKE ? ESCAPE '\\' ORDER BY level DESC LIMIT 8", (like, q, like),
        )
    if not rows_:
        await _result(message, services, f"🔎 بازیکنی با «{q}» پیدا نشد.",
                      [[keyboards.panel_button("🔎 جستجوی دوباره", "admask", uid, "find")], [keyboards.panel_button("🔙 بازیکنان", "admp", uid)]])
        return
    buttons = [[keyboards.panel_button(_player_line(r), "admpc", uid, str(r["id"]))] for r in rows_]
    buttons.append([keyboards.panel_button("🔙 بازیکنان", "admp", uid)])
    await _result(message, services, f"🔎 {bold('نتیجه‌ی جستجو')}\n\nیکی را انتخاب کنید 👇", buttons)


# --- groups -----------------------------------------------------------------------------------
@screen("admg")
async def groups(c: Ctx) -> Screen:
    _guard(c)
    page = max(0, to_int(c.a or "0") or 0)
    async with c.services.ctx.db.read() as tx:
        total = await tx.scalar("SELECT COUNT(*) FROM groups", (), 0)
        rows_ = await tx.fetchall(
            "SELECT chat_id, title, enabled FROM groups ORDER BY last_seen DESC LIMIT ? OFFSET ?", (PER, page * PER)
        )
    text = f"🏢 {bold('گروه‌ها')}\n\n{fa(total)} گروه ثبت شده است." + ("" if rows_ else "\nهنوز گروهی نیست.")
    rows = [[c.btn(f"{'🟢' if r['enabled'] else '🔴'} {r['title'] or r['chat_id']}", "admgc", r["chat_id"])] for r in rows_]
    if nav := _nav(c, "admg", page, page > 0, (page + 1) * PER < total):
        rows.append(nav)
    rows.append(_back(c))
    return Screen(text, rows)


async def _group_card(c: Ctx, chat_id: int, note: str = "") -> Screen:
    async with c.services.ctx.db.read() as tx:
        g = await tx.fetchone("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        members = await tx.scalar("SELECT COUNT(*) FROM group_members WHERE chat_id = ?", (chat_id,), 0)
    if g is None:
        raise GameError("گروه پیدا نشد.")
    on = bool(g["enabled"])
    lines = ([note, ""] if note else []) + [
        f"🏢 {bold(g['title'] or str(chat_id))}",
        f"{'🟢 فعال' if on else '🔴 غیرفعال'} · 👥 {fa(members)} بازیکن",
        f"آخرین فعالیت: {fmt(g['last_seen'])}",
        f"ثبت: {fmt(g['created_at'])}",
    ]
    rows = [
        [c.btn("🔴 غیرفعال کردن" if on else "🟢 فعال کردن", "admgt", chat_id, style="danger" if on else "success")],
        [c.btn("✉️ پیام به گروه", "admask", "gmsg", chat_id), c.btn("🎲 ساخت رویداد", "admge", chat_id)],
        [c.btn("🚪 ترک گروه", "admgl", chat_id, style="danger")],
        _back(c, "admg"),
    ]
    return Screen("\n".join(lines), rows)


@screen("admgc")
async def group_card(c: Ctx) -> Screen:
    _guard(c)
    return await _group_card(c, _chat_id(c.a))


@screen("admgt")
async def group_toggle(c: Ctx) -> Screen:
    _guard(c)
    chat_id = _chat_id(c.a)
    async with c.services.ctx.db.read() as tx:
        g = await tx.fetchone("SELECT enabled FROM groups WHERE chat_id = ?", (chat_id,))
    if g is None:
        raise GameError("گروه پیدا نشد.")
    await c.services.admin.set_group_enabled(c.owner, chat_id, not g["enabled"])
    return await _group_card(c, chat_id, "🔴 گروه غیرفعال شد" if g["enabled"] else "🟢 گروه فعال شد")


@screen("admgl")
async def group_leave_ask(c: Ctx) -> Screen:
    _guard(c)
    chat_id = _chat_id(c.a)
    text = f"🚪 {bold('ترک گروه')}\n\nربات از این گروه بیرون می‌رود و گروه غیرفعال می‌شود. مطمئنید؟"
    return Screen(text, [[c.btn("✅ بله، ترک کن", "admglok", chat_id, style="danger"), c.btn("↩️ نه", "admgc", chat_id)]])


@screen("admglok")
async def group_leave(c: Ctx) -> Screen:
    _guard(c)
    chat_id = _chat_id(c.a)
    if c.message is None:
        raise GameError("ربات در دسترس نیست.")
    with contextlib.suppress(BaleAPIError):
        await c.message.bot.leave_chat(chat_id)
    with contextlib.suppress(GameError):
        await c.services.admin.set_group_enabled(c.owner, chat_id, False)
    await c.services.admin.log_action(c.owner, "leave_group", str(chat_id))
    shown = await groups(replace(c, a="0", b=""))
    shown.toast = "🚪 ربات از گروه خارج شد"
    return shown


@screen("admge")
async def group_event(c: Ctx) -> Screen:
    _guard(c)
    chat_id = _chat_id(c.a)
    if c.b:
        kind = None if c.b == "random" else c.b
        if kind is not None and kind not in KINDS:
            raise GameError("نوع رویداد درست نیست.")
        if c.message is None:
            raise GameError("ربات برای ارسال در دسترس نیست.")
        view = await c.services.events.spawn(chat_id, kind, force=True)
        if view is None:
            raise GameError("الان نمی‌شود رویداد ساخت (باس زنده است یا شرایطش آماده نیست).")
        await events_ui.announce(c.message.bot, c.services, EventAction("spawned", view))
        await c.services.admin.log_action(c.owner, "group_event", f"{chat_id} {view.kind}")
        return await _group_card(c, chat_id, f"🎲 رویداد «{EVENT_NAMES.get(view.kind, view.kind)}» ساخته شد ✅")
    rows = [[c.btn("🎲 تصادفی", "admge", chat_id, "random", style="primary")]]
    rows += keyboards.grid([c.btn(name, "admge", chat_id, kind) for kind, name in EVENT_NAMES.items()], 2)
    rows.append(_back(c, "admgc", "🔙 بازگشت", chat_id))
    return Screen(f"🎲 {bold('ساخت رویداد')}\n\nنوع رویداد را انتخاب کنید؛ فوراً در گروه ساخته می‌شود 👇", rows)


# --- clans, sales, audit ----------------------------------------------------------------------------------
@screen("admcl")
async def clans(c: Ctx) -> Screen:
    _guard(c)
    async with c.services.ctx.db.read() as tx:
        rows_ = await tx.fetchall(
            "SELECT c.name, c.open, c.treasury, p.display_name AS leader,"
            " (SELECT COUNT(*) FROM clan_members m WHERE m.clan_id = c.id) AS members"
            " FROM clans c JOIN players p ON p.id = c.leader_id ORDER BY members DESC, c.donated DESC LIMIT 12"
        )
    lines = [f"🏯 {bold('خاندان‌ها')}", ""]
    if rows_:
        for r in rows_:
            lines.append(f"🏰 {bold(r['name'])} · رهبر {r['leader']} · {fa(r['members'])} عضو · خزانه {fa(r['treasury'])}"
                         + ("" if r["open"] else " · 🔒"))
    else:
        lines.append("هنوز خاندانی ساخته نشده است.")
    return Screen("\n".join(lines), [_back(c)])


@screen("admo")
async def orders(c: Ctx) -> Screen:
    _guard(c)
    async with c.services.ctx.db.read() as tx:
        n = await tx.scalar("SELECT COUNT(*) FROM orders WHERE status = 'delivered'", (), 0)
        revenue = await tx.scalar("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status = 'delivered'", (), 0)
        rows_ = await tx.fetchall(
            "SELECT o.pack_id, o.amount, o.status, o.created_at, p.display_name AS name FROM orders o"
            " JOIN players p ON p.id = o.player_id ORDER BY o.id DESC LIMIT 10"
        )
    lines = [f"💰 {bold('فروش')}", "", f"سفارش موفق: {bold(fa(n))} · مجموع: {bold(fa(revenue // 10))} تومان", ""]
    if rows_:
        lines.append(bold("آخرین سفارش‌ها"))
        for r in rows_:
            mark = "✅" if r["status"] == "delivered" else "⏳"
            lines.append(f"{mark} {r['name']} · {r['pack_id']} · {fa(r['amount'] // 10)} ت · {fmt(r['created_at'])}")
    else:
        lines.append("هنوز سفارشی ثبت نشده است.")
    return Screen("\n".join(lines), [_back(c)])


@screen("adma")
async def audit(c: Ctx) -> Screen:
    _guard(c)
    async with c.services.ctx.db.read() as tx:
        rows_ = await tx.fetchall("SELECT admin_id, action, detail, created_at FROM admin_log ORDER BY id DESC LIMIT 12")
    lines = [f"📜 {bold('گزارش مدیریت')}", ""]
    if rows_:
        for r in rows_:
            lines.append(f"• {fmt(r['created_at'])} — {r['action']}" + (f"\n  {r['detail']}" if r["detail"] else ""))
    else:
        lines.append("هنوز چیزی ثبت نشده است.")
    return Screen("\n".join(lines), [_back(c)])


# --- broadcast ---------------------------------------------------------------------------------------------
@screen("admbc")
async def broadcast(c: Ctx) -> Screen:
    _guard(c)
    groups_n = len(await c.services.admin.group_ids())
    players_n = len(await c.services.admin.player_ids())
    text = (
        f"📣 {bold('پیام همگانی')}\n\n"
        f"🏢 گروه‌های فعال: {fa(groups_n)}\n"
        f"👥 بازیکنان: {fa(players_n)}\n\n"
        "یکی را انتخاب کنید؛ پیش‌نمایش و تأیید دارد 👇"
    )
    rows = [
        [c.btn("✍️ ارسال همگانی به گروه‌ها", "admask", "bcast", style="primary")],
        [c.btn("📩 فوروارد همگانی به گروه‌ها", "admask", "fwd")],
        [c.btn("📨 پیام به همه‌ی بازیکنان (پیوی)", "admask", "dm")],
        [c.btn("🎲 رویداد در همه‌ی گروه‌ها", "admbe")],
        _back(c),
    ]
    return Screen(text, rows)


@screen("admbcok")
async def broadcast_send(c: Ctx) -> Screen:
    _guard(c)
    text = _drafts.pop(c.owner, "")
    if not text:
        raise GameError("پیامی برای ارسال نیست؛ دوباره بنویسید.")
    if c.message is None:
        raise GameError("ربات برای ارسال در دسترس نیست.")
    bot = c.message.bot
    sent = failed = 0
    for chat_id in await c.services.admin.group_ids():
        try:
            await bot.send_message(chat_id, text)
            sent += 1
        except BaleAPIError:
            failed += 1
        await asyncio.sleep(0.15)
    await c.services.admin.log_action(c.owner, "broadcast", f"bot sent={sent} failed={failed}")
    return Screen(f"✅ {bold('پیام همگانی فرستاده شد')}\n\nموفق: {fa(sent)}\nناموفق: {fa(failed)}", [_back(c, "admbc")])


@screen("admfwok")
async def forward_send(c: Ctx) -> Screen:
    _guard(c)
    source = _forwards.pop(c.owner, None)
    if source is None:
        raise GameError("پیامی برای فوروارد نیست؛ دوباره از «فوروارد همگانی» شروع کنید.")
    if c.message is None:
        raise GameError("ربات برای ارسال در دسترس نیست.")
    bot = c.message.bot
    sent = failed = 0
    for chat_id in await c.services.admin.group_ids():
        try:
            if c.a == "copy":
                await bot.copy_message(chat_id, source[0], source[1])
            else:
                await bot.forward_message(chat_id, source[0], source[1])
            sent += 1
        except BaleAPIError:
            failed += 1
        await asyncio.sleep(0.15)
    await c.services.admin.log_action(c.owner, "forward_all", f"{c.a} sent={sent} failed={failed}")
    return Screen(f"✅ {bold('فوروارد همگانی انجام شد')}\n\nموفق: {fa(sent)}\nناموفق: {fa(failed)}", [_back(c, "admbc")])


async def _dm_all(bot, services: Services, admin_id: int, text: str) -> None:  # noqa: ANN001
    sent = failed = 0
    for uid in await services.admin.player_ids():
        try:
            await bot.send_message(uid, headline(f"📢 {text}"))
            sent += 1
        except BaleAPIError:
            failed += 1
        await asyncio.sleep(0.1)
    await services.admin.log_action(admin_id, "dm_all", f"sent={sent} failed={failed}")
    with contextlib.suppress(BaleAPIError):
        await bot.send_message(admin_id, headline(f"✅ {bold('پیام به بازیکنان تمام شد')}\n\nموفق: {fa(sent)}\nناموفق: {fa(failed)}"))


@screen("admdmok")
async def dm_send(c: Ctx) -> Screen:
    _guard(c)
    text = _dm_drafts.pop(c.owner, "")
    if not text:
        raise GameError("پیامی برای ارسال نیست؛ دوباره بنویسید.")
    if c.message is None:
        raise GameError("ربات برای ارسال در دسترس نیست.")
    task = asyncio.create_task(_dm_all(c.message.bot, c.services, c.owner, text), name="dm-broadcast")
    _background.add(task)
    task.add_done_callback(_background.discard)
    count = len(await c.services.admin.player_ids())
    return Screen(f"📨 {bold('ارسال شروع شد')}\n\nپیام در پیوی {fa(count)} بازیکن فرستاده می‌شود؛ وقتی تمام شد خبرتان می‌کنم.", [_back(c, "admbc")])


_background: set[asyncio.Task] = set()


@screen("admbe")
async def broadcast_event(c: Ctx) -> Screen:
    _guard(c)
    if c.a:
        kind = None if c.a == "random" else c.a
        if kind is not None and kind not in KINDS:
            raise GameError("نوع رویداد درست نیست.")
        if c.message is None:
            raise GameError("ربات برای ارسال در دسترس نیست.")
        made = 0
        for chat_id in await c.services.admin.group_ids():
            view = await c.services.events.spawn(chat_id, kind, force=True)
            if view is not None:
                await events_ui.announce(c.message.bot, c.services, EventAction("spawned", view))
                made += 1
            await asyncio.sleep(0.15)
        await c.services.admin.log_action(c.owner, "event_all", f"{c.a} groups={made}")
        return Screen(f"🎲 {bold('رویداد ساخته شد')}\n\nدر {fa(made)} گروه رویداد شروع شد.", [_back(c, "admbc")])
    rows = [[c.btn("🎲 تصادفی", "admbe", "random", style="primary")]]
    rows += keyboards.grid([c.btn(name, "admbe", kind) for kind, name in EVENT_NAMES.items()], 2)
    rows.append(_back(c, "admbc"))
    return Screen(f"🎲 {bold('رویداد در همه‌ی گروه‌ها')}\n\nنوع رویداد را انتخاب کنید؛ فوراً در همه‌ی گروه‌های فعال ساخته می‌شود 👇", rows)


# --- gifts for everybody ---------------------------------------------------------------------------------------
@screen("admgf")
async def gifts(c: Ctx) -> Screen:
    _guard(c)
    count = len(await c.services.admin.player_ids())
    text = f"🎁 {bold('هدیه‌ی همگانی')}\n\nبه همه‌ی {fa(count)} بازیکن (به‌جز مسدودها) هدیه بدهید؛ مثلاً جایزه‌ی یک رویداد.\nقبل از اجرا تأیید می‌گیرم 👇"
    rows = [
        [c.btn("🪙 سکه", "admask", "gift_gold"), c.btn("💎 کریستال", "admask", "gift_crystal")],
        [c.btn("💠 روز VIP", "admask", "gift_vip")],
        _back(c),
    ]
    return Screen(text, rows)


@screen("admgfok")
async def gifts_apply(c: Ctx) -> Screen:
    _guard(c)
    gift = _gifts.pop(c.owner, None)
    if not gift:
        raise GameError("هدیه‌ای برای ارسال نیست؛ دوباره شروع کنید.")
    count = await c.services.admin.give_all(c.owner, **gift)
    return Screen(f"✅ {bold('هدیه داده شد')}\n\nبه {fa(count)} بازیکن رسید.", [_back(c, "admgf")])


# --- maintenance mode and backup --------------------------------------------------------------------------------
@screen("admlk")
async def link_buttons(c: Ctx) -> Screen:
    _guard(c)
    shown = await c.services.admin.links()
    lines = [f"🔗 {bold('دکمه‌های لینک منوی اصلی')}", "", "این دو دکمه در منوی اصلی پیوی ربات، زیر دکمه‌ی «دعوت از دوستان» نشان داده می‌شوند.", ""]
    for key, label in (("group", "👥 گروه"), ("channel", "📣 کانال")):
        item = shown[key]
        lines += [f"{label}: «{item['text']}»", f"   لینک: {item['url'] or 'ندارد (دکمه پنهان است)'}", ""]
    rows = [
        [c.btn("✏️ متن دکمه‌ی گروه", "admask", "lk_gt"), c.btn("🔗 لینک گروه", "admask", "lk_gu")],
        [c.btn("✏️ متن دکمه‌ی کانال", "admask", "lk_ct"), c.btn("🔗 لینک کانال", "admask", "lk_cu")],
        _back(c),
    ]
    return Screen("\n".join(lines).strip(), rows)


@screen("admmn")
async def maintenance(c: Ctx) -> Screen:
    _guard(c)
    enabled, text = await c.services.admin.maintenance()
    lines = [
        f"🚧 {bold('حالت تعمیر')}",
        "",
        "وقتی روشن باشد فقط مدیران می‌توانند از ربات استفاده کنند و بقیه پیام تعمیر می‌بینند.",
        "",
        f"وضعیت: {'روشن 🚧' if enabled else 'خاموش ✅'}",
        f"پیام: {text or 'پیش‌فرض'}",
    ]
    rows = [
        [c.btn("✅ خاموش کردن" if enabled else "🚧 روشن کردن", "admmnt", style="success" if enabled else "danger")],
        [c.btn("✍️ تغییر متن پیام", "admask", "mntext")],
        _back(c),
    ]
    return Screen("\n".join(lines), rows)


@screen("admmnt")
async def maintenance_toggle(c: Ctx) -> Screen:
    _guard(c)
    enabled, _ = await c.services.admin.maintenance()
    await c.services.admin.set_maintenance(c.owner, not enabled)
    return await maintenance(c)


@screen("admbk")
async def backup(c: Ctx) -> Screen:
    _guard(c)
    if c.a == "send":
        if c.owner != c.services.ctx.settings.owner_id or c.message is None:
            raise GameError("فایل پشتیبان فقط برای مالک فرستاده می‌شود.")
        path = await make_backup(c.services.ctx.db)
        await c.message.bot.send_document(c.owner, FSInputFile(path), caption="💾 نسخه‌ی پشتیبان دیتابیس")
        await c.services.admin.log_action(c.owner, "backup_send", path.name)
        return Screen(f"💾 {bold('فایل پشتیبان فرستاده شد')}\n\nهمین الان در پیوی شما رسید.", [_back(c)])
    path = await make_backup(c.services.ctx.db)
    await c.services.admin.log_action(c.owner, "backup", path.name)
    size = path.stat().st_size // 1024
    rows = [[c.btn("📤 دریافت فایل", "admbk", "send")], _back(c)] if c.owner == c.services.ctx.settings.owner_id else [_back(c)]
    return Screen(f"💾 {bold('نسخه‌ی پشتیبان ساخته شد')}\n\n📁 {path.name}\n📦 {fa(size)} کیلوبایت\n\nنسخه‌های قدیمی خودکار پاک می‌شوند.", rows)


# --- forced membership ---------------------------------------------------------------------------------------
@screen("admm")
async def membership(c: Ctx, note: str = "") -> Screen:
    _guard(c)
    enabled, channels = await c.services.membership.settings()
    lines = ([note, ""] if note else []) + [
        f"🔒 {bold('عضویت اجباری')}",
        "",
        "بازیکنان باید قبل از بازی در این کانال‌ها عضو شوند. ربات باید در هر کانال ادمین باشد.",
        "",
        f"وضعیت: {'روشن ✅' if enabled else 'خاموش ⛔'}",
    ]
    rows = [[c.btn("🔕 خاموش کردن" if enabled else "🔔 روشن کردن", "admmt", style="danger" if enabled else "success")]]
    if channels:
        lines += ["", bold("کانال‌ها")]
    for i, ch in enumerate(channels):
        status = ""
        if c.message is not None:
            try:
                info = await c.services.membership.probe(c.message.bot, ch.chat)
                status = " ✅ ربات ادمین است" if info["bot_status"] in ("administrator", "creator") else " ⚠️ ربات ادمین نیست"
            except GameError:
                status = " ⚠️ کانال پیدا نشد"
        lines.append(f"📣 {ch.title or ch.chat} ({ch.chat}){status}")
        rows.append([c.btn(f"🔍 بررسی {ch.title or ch.chat}", "admmp", i), c.btn("❌ حذف", "admmr", i, style="danger")])
    if len(channels) < 5:
        rows.append([c.btn("➕ افزودن کانال", "admask", "chan", style="primary")])
    rows.append(_back(c))
    return Screen("\n".join(lines), rows)


@screen("admmt")
async def membership_toggle(c: Ctx) -> Screen:
    _guard(c)
    enabled, channels = await c.services.membership.settings()
    if not enabled and channels and c.message is not None:
        problems = await c.services.membership.verify(c.message.bot)
        if problems:
            raise GameError("⚠️ قبل از روشن کردن، ربات را در کانال‌ها ادمین کنید:\n" + "\n".join(problems))
    await c.services.membership.save(not enabled, [x.as_dict() for x in channels])
    await c.services.admin.log_action(c.owner, "membership", f"enabled={not enabled}")
    return await membership(c, "🔔 عضویت اجباری روشن شد" if not enabled else "🔕 عضویت اجباری خاموش شد")


@screen("admmr")
async def membership_remove(c: Ctx) -> Screen:
    _guard(c)
    enabled, channels = await c.services.membership.settings()
    index = to_int(c.a or "")
    if index is None or not 0 <= index < len(channels):
        raise GameError("این کانال دیگر نیست.")
    left = [x.as_dict() for i, x in enumerate(channels) if i != index]
    await c.services.membership.save(enabled and bool(left), left)
    await c.services.admin.log_action(c.owner, "membership", f"remove {channels[index].chat}")
    return await membership(c, "❌ کانال حذف شد")


@screen("admmp")
async def membership_probe(c: Ctx) -> Screen:
    _guard(c)
    _, channels = await c.services.membership.settings()
    index = to_int(c.a or "")
    if index is None or not 0 <= index < len(channels) or c.message is None:
        raise GameError("این کانال دیگر نیست.")
    info = await c.services.membership.probe(c.message.bot, channels[index].chat)
    ok = info["bot_status"] in ("administrator", "creator")
    note = f"🔍 {info['title'] or channels[index].chat}: " + ("ربات ادمین است ✅" if ok else f"ربات ادمین نیست ⚠️ ({info['bot_status']})")
    return await membership(c, note)
