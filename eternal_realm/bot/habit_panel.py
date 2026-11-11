"""Screens of the habits that bring heroes back: the ranked season, friends, pop-up happenings, the week's missions."""

from __future__ import annotations

from ..game.data.items import get_item
from ..game.services import ladder
from ..game.services.missions import WEEK_PRIZES
from ..game.services.social import GIFT_ENERGY, MAX_FRIENDS, SocialService
from ..shared.errors import GameError
from ..shared.text import bar, bold, duration, fa
from .panel import PER_PAGE, Ctx, Screen, _int, _nav, _page, screen

LINE = "━━━━━━━━━━━━"
MEDALS = ("🥇", "🥈", "🥉")


# --- the ranked season ----------------------------------------------------------------------------------------------
@screen("rseason")
async def rseason(c: Ctx) -> Screen:
    standing = await c.services.ladder.standing(c.player.id)
    lines = [
        f"🏆 {bold('فصل رتبه‌بندی ' + fa(ladder.label(standing.number)))}", LINE,
        "هر تجربه‌ای که می‌گیرید امتیاز فصل است؛ ماجراجویی، شکار، نبرد و هر کار دیگر.",
        f"⏳ تا پایان فصل: {duration(standing.ends_in)}",
        "",
        f"🎁 {bold('جایزه‌ی ده نفر برتر')}",
        "🥇 ۳۰ کریستال + صندوقچه‌ی سلطنتی",
        "🥈 ۲۰ کریستال + صندوقچه‌ی سلطنتی",
        "🥉 ۱۵ کریستال + صندوقچه‌ی جادویی",
        "🎖️ رتبه‌ی ۴ تا ۱۰: کریستال و صندوقچه",
        "همه‌ی ده نفر یک عنوان ماندگار هم می‌گیرند.",
        "",
        f"📋 {bold('جدول فصل')}",
    ]
    if standing.top:
        lines += [
            f"{MEDALS[r.rank - 1] if r.rank <= 3 else '🔹'} {r.name} · سطح {fa(r.level)} — {fa(r.score)} امتیاز" for r in standing.top
        ]
    else:
        lines.append("هنوز کسی امتیاز نگرفته؛ اولین نفر باشید!")
    if standing.mine is not None:
        lines += ["", f"📍 رتبه‌ی شما: {fa(standing.mine.rank)} · {fa(standing.mine.score)} امتیاز"]
        if standing.top and standing.mine.rank > len(standing.top):
            gap = standing.top[-1].score - standing.mine.score
            lines.append(f"تا ده نفر برتر {fa(gap)} امتیاز مانده.")
    rows = [[c.btn("🔄 تازه‌سازی", "rseason")], c.back("fight")]
    return Screen("\n".join(lines), rows)


# --- friends ------------------------------------------------------------------------------------------------------------
@screen("friends")
async def friends(c: Ctx) -> Screen:
    if c.is_group:
        raise GameError("فهرست دوستان در پیوی ربات باز می‌شود.")
    page = max(0, _int(c.a or "0"))
    asking = await c.services.social.pending(c.player)
    mine = await c.services.social.friends(c.player)
    chunk, has_prev, has_next = _page(mine, page, PER_PAGE)
    lines = [
        f"👥 {bold('دوستان')}", LINE,
        f"{fa(len(mine))} از {fa(MAX_FRIENDS)} دوست. هر روز برای هر دوست {fa(GIFT_ENERGY)} انرژی می‌فرستید و او هم برای شما.",
        "برای دوست شدن، روی پیام کسی ریپلای کنید و «دوست» بنویسید.",
    ]
    rows = []
    for pid, name, level in asking[:3]:
        lines.append(f"📨 {name} (سطح {fa(level)}) می‌خواهد دوست شما شود")
        rows.append([c.btn(f"✅ {name}", "friendyes", pid, style="success"), c.btn("❌ رد", "friendno", pid)])
    if not mine:
        lines += ["", "هنوز دوستی ندارید؛ همراه‌ها ماجرا را شیرین‌تر می‌کنند."]
    for f in chunk:
        rows.append([c.btn(f"{'🎁' if not f.gifted_today else '✔️'} {f.name} · سطح {fa(f.level)}", "friend", f.player_id)])
    nav = _nav(c, "friends", page, has_prev, has_next)
    if nav:
        rows.append(nav)
    rows.append(c.back("home"))
    return Screen("\n".join(lines), rows)


@screen("friend")
async def friend(c: Ctx) -> Screen:
    fid = _int(c.a)
    found = next((f for f in await c.services.social.friends(c.player) if f.player_id == fid), None)
    if found is None:
        raise GameError("او در فهرست دوستان شما نیست.")
    lines = [
        f"👤 {bold(found.name)}", LINE,
        f"سطح {fa(found.level)} · {found.class_label}",
        f"♾️ {SocialService.maze_line(found)}",
        "",
        "✔️ امروز برایش انرژی فرستاده‌اید" if found.gifted_today else f"🎁 می‌توانید امروز {fa(GIFT_ENERGY)} انرژی برایش بفرستید",
    ]
    rows = []
    if not found.gifted_today:
        rows.append([c.btn(f"🎁 ارسال {fa(GIFT_ENERGY)} انرژی", "friendgift", fid, style="success")])
    rows.append([c.btn("🗑️ حذف از دوستان", "friendrm", fid)])
    rows.append(c.back("friends"))
    return Screen("\n".join(lines), rows)


@screen("friendgift")
async def friend_gift(c: Ctx) -> Screen:
    gained = await c.services.social.gift_energy(c.player, _int(c.a))
    shown = await friend(c)
    shown.toast = f"🎁 {fa(gained)} انرژی فرستادید" if gained else "🎁 هدیه رفت؛ نوار انرژی‌اش پر بود"
    return shown


@screen("friendyes")
async def friend_yes(c: Ctx) -> Screen:
    await c.services.social.respond(c.player, _int(c.a), True)
    shown = await friends(c)
    shown.toast = "🤝 دوست شدید!"
    return shown


@screen("friendno")
async def friend_no(c: Ctx) -> Screen:
    await c.services.social.respond(c.player, _int(c.a), False)
    return await friends(c)


@screen("friendrm")
async def friend_remove(c: Ctx) -> Screen:
    await c.services.social.remove(c.player, _int(c.a))
    shown = await friends(c)
    shown.toast = "از فهرست دوستان حذف شد"
    return shown


# --- pop-up happenings --------------------------------------------------------------------------------------------------
@screen("popup")
async def popup(c: Ctx) -> Screen:
    if c.is_group:
        raise GameError("این اتفاق در پیوی ربات است.")
    found = await c.services.popups.get(c.player, _int(c.a)) if c.a else await c.services.popups.latest(c.player)
    if found is None:
        return Screen(f"⌛ {bold('این اتفاق گذشت')}\n\nفرصتش تمام شده یا قبلاً درباره‌اش تصمیم گرفته‌اید. دفعه‌ی بعد زودتر برسید!", [c.back("home")])
    p = found.popup
    lines = [f"{p.emoji} {bold(p.title)}", LINE, p.text, "", f"⏳ فرصت: {duration(found.seconds_left)}", "چه می‌کنید؟ 👇"]
    rows = [[c.btn(choice.label, "popupgo", found.id, i)] for i, choice in enumerate(p.choices)]
    return Screen("\n".join(lines), rows)


@screen("popupgo")
async def popup_go(c: Ctx) -> Screen:
    result = await c.services.popups.choose(c.player, _int(c.a), _int(c.b))
    await c.refresh()
    lines = [f"{result.popup.emoji} {bold(result.popup.title)}", LINE, *result.lines]
    gains = []
    if result.gold:
        gains.append(f"🪙 {fa(result.gold)} سکه")
    if result.xp:
        gains.append(f"⭐ {fa(result.xp)} تجربه")
    if result.crystal:
        gains.append(f"💎 {fa(result.crystal)} کریستال")
    gains += [f"🎁 {get_item(i).name}" + (f" ×{fa(q)}" if q > 1 else "") for i, q in result.items.items()]
    if gains:
        lines += ["", f"🎁 {bold('دستاورد')}", *gains]
    return Screen("\n".join(lines), [c.back("home", "🏰 قلمرو")])


# --- the week's missions ------------------------------------------------------------------------------------------------
async def week_lines(c: Ctx) -> tuple[list[str], list]:
    """The «week» block of the missions screen and the button that collects its prize."""
    week = await c.services.missions.week(c.player)
    lines = [LINE, f"🗓️ {bold('جایزه‌ی هفته')}", f"{bar(week.days, 7, 7)} {fa(week.days)} از ۷ روز کامل"]
    for days, crystal, chest in WEEK_PRIZES[::-1]:
        mark = "✅" if week.days >= days else "▫️"
        lines.append(f"{mark} {fa(days)} روز: 💎 {fa(crystal)} + {get_item(chest).name}")
    lines.append(f"⏳ تا پایان هفته: {duration(week.seconds_left)}")
    rows = []
    if week.claimed:
        lines.append("🎁 جایزه‌ی این هفته را گرفته‌اید.")
    elif week.earned is not None:
        label = "🎁 دریافت جایزه‌ی هفته" if week.days >= 7 else f"🎁 دریافت جایزه‌ی فعلی ({fa(week.earned[0])} روز)"
        rows.append([c.btn(label, "msweek", style="success")])
        if week.next_prize is not None:
            lines.append(f"می‌توانید صبر کنید تا جایزه‌ی بزرگ‌تر ({fa(week.next_prize[0])} روز) را بگیرید؛ فقط یک بار در هفته می‌گیرید.")
    return lines, rows


@screen("msweek")
async def mission_week(c: Ctx) -> Screen:
    days, crystal, chest = await c.services.missions.claim_week(c.player)
    from .mission_panel import missions

    shown = await missions(c)
    shown.toast, shown.alert = f"🎁 {fa(days)} روز کامل! 💎 {fa(crystal)} کریستال و {get_item(chest).name}", True
    return shown


# --- keeping a streak -----------------------------------------------------------------------------------------------------
@screen("rescue")
async def rescue(c: Ctx) -> Screen:
    streak, can = c.services.players.streak_status(c.player)
    if not can:
        raise GameError("زنجیره‌ی شما الان نیاز به نجات ندارد.")
    cost = c.services.players.RESCUE_COST
    text = (
        f"🛟 {bold('نجات زنجیره')}\n\nیک روز گنجینه‌ی روزانه را از دست دادید و زنجیره‌ی {fa(streak)} روزه‌تان در خطر است.\n"
        f"با {fa(cost)} کریستال زنجیره را نگه می‌دارید و فردا ادامه‌اش می‌دهید.\n(هر ۱۴ روز یک بار)"
    )
    return Screen(text, [[c.btn(f"💎 بله، نجات بده · {fa(cost)}", "rescuedo", style="success"), c.btn("↩️ نه", "home")]])


@screen("rescuedo")
async def rescue_do(c: Ctx) -> Screen:
    streak = await c.services.players.rescue_streak(c.player.id)
    await c.refresh()
    text = f"🛟 {bold('زنجیره نجات پیدا کرد!')}\n\nزنجیره‌ی {fa(streak)} روزه‌تان سر جایش است؛ حالا گنجینه‌ی روزانه را بردارید 👇"
    return Screen(text, [[c.btn("🎁 گنجینه‌ی روزانه", "daily", style="success")], c.back("home")])

