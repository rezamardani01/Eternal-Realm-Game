"""War between two clans: declare it, answer it, storm the enemy keeps and read the scoreboard."""

from __future__ import annotations

from ..game.services.clan_wars import MAX_STARS, STAKES, AttackResult, WarView, star_text
from ..shared.errors import GameError
from ..shared.text import bar, bold, duration, fa
from . import keyboards
from .panel import PER_PAGE, Ctx, Screen, _int, _nav, _page, screen

LINE = "─" * 14
NOTES = {
    "us": "⭐ ستاره‌های خاندان شما: از هر دژ دشمن، بهترین حمله حساب می‌شود.",
    "them": "⭐ ستاره‌های دشمن: هر چه دژهای شما محکم‌تر، این عدد کمتر.",
    "stake": "🪙 گرو از خزانه‌ی هر دو خاندان برداشته شده و همه‌اش به خزانه‌ی برنده می‌رسد.",
    "left": "🗡️ حمله‌هایی که در این جنگ برایتان مانده. هر دژ را فقط یک بار می‌توانید بزنید.",
    "time": "⏳ با تمام شدن زمان (یا تمام شدن همه‌ی حمله‌ها) جنگ بسته و برنده اعلام می‌شود.",
    "star": "⭐ برد با ۶۰٪ جان = ۳ ستاره، با ۳۰٪ جان = ۲ ستاره، هر برد دیگر = ۱ ستاره.",
}


def _stake_text(stake: int) -> str:
    return f"{fa(stake)} سکه" if stake else "بدون گرو"


def _tug(mine: int, enemy: int, width: int = 12) -> str:
    """The rope between the two clans: filled from our side by our share of the stars."""
    return bar(mine, mine + enemy, width) if mine + enemy else "▱" * width


def _scoreboard(war: WarView) -> list[str]:
    return [
        f"🏯 {bold(war.mine.name)} — {fa(war.mine.stars)} ستاره",
        f"{_tug(war.mine.stars, war.enemy.stars)}",
        f"🏴 {bold(war.enemy.name)} — {fa(war.enemy.stars)} ستاره",
    ]


def _chips(c: Ctx, war: WarView) -> list:
    return [
        [c.btn(f"⭐ ما: {fa(war.mine.stars)}", "cwarnote", "us"), c.btn(f"⭐ دشمن: {fa(war.enemy.stars)}", "cwarnote", "them")],
        [
            c.btn(f"🗡️ {fa(war.mine.used)}/{fa(war.mine.total)}", "cwarnote", "left"),
            c.btn(f"⏳ {duration(war.seconds_left)}", "cwarnote", "time"),
            c.btn(f"🪙 {_stake_text(war.stake)}", "cwarnote", "stake"),
        ],
    ]


@screen("cwarnote")
async def war_note(c: Ctx) -> Screen:
    return Screen(None, toast=NOTES.get(c.a, NOTES["star"]), alert=True)


# --- the war room ---------------------------------------------------------------------------------
@screen("cwar")
async def war_room(c: Ctx) -> Screen:
    hub = await c.services.clan_wars.hub(c.player)
    b = c.services.ctx.balance
    won, lost, drawn = hub.record
    war = hub.war
    if war is None:
        lines = [
            f"⚔️ {bold('جنگ خاندان‌ها')}",
            "",
            f"🏯 خاندان {bold(hub.clan_name)}",
            f"📜 کارنامه: {fa(won)} پیروزی · {fa(lost)} شکست · {fa(drawn)} مساوی",
            f"🪙 خزانه: {fa(hub.treasury)} سکه",
            LINE,
            "شیپور جنگ را بنوازید و پرچم خاندان را بر دژ دشمن بکوبید:",
            f"🗡️ هر جنگاور {fa(b.clan_war_attacks)} حمله دارد؛ هر حمله تا {fa(MAX_STARS)} ستاره.",
            f"⏳ جنگ {duration(b.clan_war_hours * 3600)} طول می‌کشد.",
            "🪙 گروِ هر دو خزانه به خاندان برنده می‌رسد.",
            "🎖️ جنگاوران سکه، تجربه و خان‌پوینت می‌گیرند.",
        ]
        if hub.last is not None:
            mark = {"won": "🏆 پیروزی بر", "lost": "💔 شکست از", "draw": "🤝 مساوی با"}[hub.last.result]
            lines += ["", f"{mark} {hub.last.enemy.name} ({fa(hub.last.mine.stars)} به {fa(hub.last.enemy.stars)})"]
        rows = []
        if hub.can_manage:
            rows.append([c.btn("📯 اعلام جنگ", "cwarpick", "0", style="danger")])
        else:
            lines += ["", "اعلام جنگ با مالک و قائم‌مقام است؛ شمشیرتان را تیز نگه دارید!"]
        rows.append([c.btn("📜 جنگ‌های گذشته", "cwarlog"), c.btn("🏅 جنگاوران", "cwarboard")])
        rows.append([c.btn("🏆 لیگ هفتگی خاندان‌ها", "clanwar")])
        rows.append(c.back("clan"))
        return Screen("\n".join(lines), rows)

    if war.status == "pending":
        lines = [
            f"📯 {bold('اعلام جنگ')}",
            "",
            (f"خاندان {bold(war.enemy.name)} شما را به جنگ خوانده است!" if war.incoming
             else f"پیک شما به دژ خاندان {bold(war.enemy.name)} رسید؛ منتظر پاسخ هستیم."),
            "",
            f"🪙 گرو: {_stake_text(war.stake)}" + (" از خزانه‌ی هر خاندان" if war.stake else ""),
            f"⏳ مهلت پاسخ: {duration(war.seconds_left)}",
        ]
        rows = []
        if war.incoming:
            lines.append(f"🏦 خزانه‌ی شما: {fa(hub.treasury)} سکه")
            if hub.can_manage:
                rows.append([
                    c.btn("⚔️ می‌جنگیم!", "cwaryes", war.id, style="success"),
                    c.btn("🕊️ رد می‌کنیم", "cwarno", war.id, style="danger"),
                ])
            else:
                lines += ["", "پاسخ با مالک و قائم‌مقام است."]
        elif hub.can_manage:
            rows.append([c.btn("↩️ پس گرفتن اعلام جنگ", "cwarback", war.id, style="danger")])
        rows.append([c.btn("🔄 تازه‌سازی", "cwar")])
        rows.append(c.back("clan"))
        return Screen("\n".join(lines), rows)

    lines = [f"⚔️ {bold('میدان جنگ')}", "", *_scoreboard(war), LINE]
    if war.fighter:
        lines.append(
            f"🗡️ حمله‌های شما: {bold(fa(war.attacks_left))} از {fa(b.clan_war_attacks)}"
            if war.attacks_left else "✅ هر دو شمشیرتان را زده‌اید؛ حالا هم‌رزمان را تشویق کنید."
        )
    else:
        lines.append("👀 شما پس از آغاز این جنگ پیوسته‌اید و تماشاگرید.")
    lines.append(f"⏳ تا پایان جنگ: {duration(war.seconds_left)}")
    rows = _chips(c, war)
    if war.fighter and war.attacks_left:
        rows.append([c.btn("⚔️ حمله به دژهای دشمن", "cwartargets", "0", style="danger")])
    rows.append([c.btn("🏅 جنگاوران", "cwarboard"), c.btn("🔄 تازه‌سازی", "cwar")])
    rows.append(c.back("clan"))
    return Screen("\n".join(lines), rows)


# --- declaring ------------------------------------------------------------------------------------
@screen("cwarpick")
async def war_pick(c: Ctx) -> Screen:
    page = max(0, _int(c.a or "0"))
    rivals, has_next = await c.services.clan_wars.rivals(c.player, page, PER_PAGE)
    lines = [f"📯 {bold('کدام خاندان را به جنگ می‌خوانید؟')}", ""]
    rows = []
    if not rivals:
        lines.append("هنوز خاندان دیگری در قلمرو نیست که بشود با آن جنگید.")
    for r in rivals:
        if r.blocked:
            lines.append(f"🔒 {r.name}: {r.blocked}")
        else:
            rows.append([c.btn(f"🏴 {r.name} · سطح {fa(r.level)} · {fa(r.size)} عضو · قدرت {fa(r.power)}", "cwarstake", r.id)])
    if rows:
        lines.append("حریفتان را انتخاب کنید 👇")
    nav = _nav(c, "cwarpick", page, page > 0, has_next)
    if nav:
        rows.append(nav)
    rows.append(c.back("cwar"))
    return Screen("\n".join(lines), rows)


@screen("cwarstake")
async def war_stake(c: Ctx) -> Screen:
    rival, treasury = await c.services.clan_wars.rival(c.player, _int(c.a))
    if rival.blocked:
        raise GameError(f"به خاندان {rival.name} نمی‌شود اعلام جنگ کرد: {rival.blocked}.")
    lines = [
        f"🪙 {bold('گروِ جنگ با ' + rival.name)}",
        "",
        f"🏴 {rival.name} · سطح {fa(rival.level)} · {fa(rival.size)} عضو",
        f"🏦 خزانه‌ی شما: {fa(treasury)} سکه",
        "",
        "گرو همین حالا از خزانه برداشته می‌شود. اگر حریف بپذیرد او هم همین‌قدر می‌گذارد و همه‌اش به برنده می‌رسد؛ "
        "اگر نپذیرد، گرو برمی‌گردد.",
    ]
    stakes = [
        c.btn(f"🪙 {fa(s)} سکه" if s else "🎗️ فقط افتخار", "cwarq", rival.id, s) for s in STAKES if s <= treasury
    ]
    rows = keyboards.grid(stakes, 2)
    rows.append(c.back("cwarpick", "🔙 بازگشت", "0"))
    return Screen("\n".join(lines), rows)


@screen("cwarq")
async def war_ask(c: Ctx) -> Screen:
    rival, treasury = await c.services.clan_wars.rival(c.player, _int(c.a))
    stake, b = _int(c.b or "0"), c.services.ctx.balance
    lines = [
        f"📯 {bold('اعلام جنگ به ' + rival.name)}",
        "",
        f"🪙 گرو: {_stake_text(stake)}",
    ]
    if stake:
        lines.append(f"🏦 خزانه: {fa(treasury)} ← {fa(max(0, treasury - stake))} سکه")
    lines += [
        f"⏳ مهلت پاسخ حریف: {duration(b.clan_war_accept_hours * 3600)}",
        "",
        "پیک روانه شود؟",
    ]
    return Screen("\n".join(lines), [[
        c.btn("📯 بله، اعلام جنگ", "cwargo", rival.id, stake, style="danger"), c.btn("↩️ نه", "cwarstake", rival.id),
    ]])


@screen("cwargo")
async def war_declare(c: Ctx) -> Screen:
    war = await c.services.clan_wars.declare(c.player, _int(c.a), _int(c.b or "0"))
    await c.show(f"📯 {bold('شیپور جنگ')}\n\nپیک خاندان با پرچم سرخ به سوی دژ {war.enemy.name} می‌تازد...")
    shown = await war_room(c)
    shown.toast = f"📯 به خاندان {war.enemy.name} اعلام جنگ شد"
    return shown


@screen("cwaryes")
async def war_accept(c: Ctx) -> Screen:
    war = await c.services.clan_wars.answer(c.player, _int(c.a), True)
    assert war is not None
    await c.show(f"⚔️ {bold('جنگ آغاز شد')}\n\nدروازه‌ها بسته شد، طبل‌ها می‌کوبند و سپاه {war.mine.name} صف می‌کشد...")
    shown = await war_room(c)
    shown.toast, shown.alert = f"⚔️ جنگ با خاندان {war.enemy.name} آغاز شد!", True
    return shown


@screen("cwarno")
async def war_decline(c: Ctx) -> Screen:
    await c.services.clan_wars.answer(c.player, _int(c.a), False)
    shown = await war_room(c)
    shown.toast = "🕊️ اعلام جنگ رد شد"
    return shown


@screen("cwarback")
async def war_withdraw(c: Ctx) -> Screen:
    await c.services.clan_wars.withdraw(c.player, _int(c.a))
    shown = await war_room(c)
    shown.toast = "↩️ اعلام جنگ پس گرفته شد و گرو به خزانه برگشت"
    return shown


# --- fighting -------------------------------------------------------------------------------------
@screen("cwartargets")
async def war_targets(c: Ctx) -> Screen:
    war, targets = await c.services.clan_wars.targets(c.player)
    page = max(0, _int(c.a or "0"))
    chunk, has_prev, has_next = _page(targets, page)
    rows = []
    for t in chunk:
        mark = "✅" if t.mine is not None else "🏴" if t.best >= MAX_STARS else "🎯"
        rows.append([c.btn(f"{mark} {t.name} · سطح {fa(t.level)} · {star_text(t.best)}", "cwarhitq", t.player_id, page)])
    nav = _nav(c, "cwartargets", page, has_prev, has_next)
    if nav:
        rows.append(nav)
    rows.append(c.back("cwar"))
    lines = [
        f"🎯 {bold('دژهای خاندان ' + war.enemy.name)}",
        "",
        f"🗡️ حمله‌های شما: {bold(fa(war.attacks_left))}",
        "🎯 آماده‌ی حمله · ✅ شما زده‌اید · 🏴 کامل فتح شده",
        "",
        "ستاره‌های کنار هر نام، بهترین نتیجه‌ی خاندان شما روی آن دژ است. هدف را انتخاب کنید 👇",
    ]
    return Screen("\n".join(lines), rows)


@screen("cwarhitq")
async def war_attack_ask(c: Ctx) -> Screen:
    war, targets = await c.services.clan_wars.targets(c.player)
    target = next((t for t in targets if t.player_id == _int(c.a)), None)
    if target is None:
        raise GameError("این جنگاور دیگر در سپاه دشمن نیست؛ هدف دیگری انتخاب کنید.")
    back = c.back("cwartargets", "🔙 بازگشت", c.b or "0")
    lines = [
        f"🎯 {bold('دژ ' + target.name)}",
        "",
        f"⭐ سطح نگهبان: {fa(target.level)}",
        f"🏴 ستاره‌های گرفته‌شده: {star_text(target.best)}",
        f"🗡️ حمله‌های شما: {fa(war.attacks_left)}",
    ]
    if target.mine is not None:
        lines += ["", "شما یک بار به این دژ حمله کرده‌اید."]
        return Screen("\n".join(lines), [back])
    if target.best >= MAX_STARS:
        lines += ["", "این دژ کامل فتح شده؛ حمله‌تان را جای دیگری خرج کنید."]
        return Screen("\n".join(lines), [back])
    if not war.attacks_left:
        lines += ["", "حمله‌ای برایتان نمانده است."]
        return Screen("\n".join(lines), [back])
    lines += ["", "نبرد خودکار است و یک حمله مصرف می‌شود. یورش ببریم؟"]
    return Screen("\n".join(lines), [[c.btn("⚔️ یورش!", "cwarhit", target.player_id, style="danger"), *back]])


def attack_text(who: str, r: AttackResult) -> str:
    if r.won:
        head = f"🏆 {bold('دژ ' + r.target + ' فتح شد')}"
        story = f"{who} دروازه را شکست و پرچم خاندان را بر برج کوبید."
    elif r.draw:
        head = f"🤝 {bold('دژ ' + r.target + ' پابرجا ماند')}"
        story = f"{who} تا آخرین نفس جنگید ولی شب رسید و دروازه باز نشد."
    else:
        head = f"🛡️ {bold('دژ ' + r.target + ' پابرجا ماند')}"
        story = f"{who} پشت دیوارهای {r.target} از پا افتاد."
    lines = [
        head,
        "",
        story,
        "",
        f"🌟 ستاره‌ها: {star_text(r.stars)}",
        f"❤️ {r.attacker}: {bar(*r.hp)} {fa(r.hp[0])}",
        f"🏴 {r.target}: {bar(*r.foe_hp)} {fa(r.foe_hp[0])}",
        "",
    ]
    if r.gained:
        lines.append(f"📈 {fa(r.gained)} ستاره‌ی تازه برای خاندان!")
    elif r.stars:
        lines.append("📊 هم‌رزمانتان پیش‌تر همین‌قدر از این دژ گرفته بودند؛ ستاره‌ی تازه‌ای اضافه نشد.")
    if r.level_up:
        lines.append(f"🎉 رسیدید به سطح {fa(r.level_up.new_level)}")
    lines += [LINE, *_scoreboard(r.war)]
    if r.finished:
        lines += ["", "🏁 آخرین شمشیر زده شد و جنگ به پایان رسید!"]
    return "\n".join(lines)


@screen("cwarhit")
async def war_attack(c: Ctx) -> Screen:
    r = await c.services.clan_wars.attack(c.player, _int(c.a))
    who = c.who(c.player)
    await c.show(f"📯 {bold('یورش به دژ ' + r.target)}\n\n{who} شمشیر می‌کشد و به سوی دروازه می‌تازد...")
    if r.log:
        await c.show(f"⚔️ {bold('نبرد پای دیوار')}\n\n" + "\n".join(r.log[:3]))
    if len(r.log) > 6:
        await c.show(f"🔥 {bold('نفس‌های آخر')}\n\n" + "\n".join(r.log[-3:]))
    chips = [c.btn(f"🌟 {fa(r.stars)} ستاره", "cwarnote", "star")]
    if r.gold:
        chips.append(keyboards.panel_button(f"🪙 {fa(r.gold)} سکه", "note", c.owner, "gold"))
    chips.append(keyboards.panel_button(f"⭐ {fa(r.xp)} تجربه", "note", c.owner, "xp"))
    rows = keyboards.grid(chips, 3)
    if not r.finished and r.war.attacks_left:
        rows.append([c.btn(f"⚔️ حمله‌ی بعدی ({fa(r.war.attacks_left)})", "cwartargets", "0", style="danger")])
    rows.append([c.btn("🏯 میدان جنگ", "cwar"), c.btn("🏅 جنگاوران", "cwarboard")])
    return Screen(attack_text(who, r), rows)


# --- boards ---------------------------------------------------------------------------------------
@screen("cwarboard")
async def war_board(c: Ctx) -> Screen:
    war, champions = await c.services.clan_wars.champions(c.player)
    lines = [f"🏅 {bold('جنگاوران')}", ""]
    if war is None:
        lines.append("خاندان شما هنوز جنگی نکرده است.")
    else:
        lines += [f"جنگ با خاندان {war.enemy.name}" + (" (پایان‌یافته)" if war.status == "done" else ""), ""]
        if not champions:
            lines.append("هنوز کسی شمشیر نزده. اولین باشید!")
        medals = ["🥇", "🥈", "🥉"]
        for i, one in enumerate(champions[:12]):
            place = medals[i] if i < 3 else f"{fa(i + 1)}."
            side = "🏯" if one.ours else "🏴"
            lines.append(f"{place} {side} {one.name} — {fa(one.stars)} ستاره در {fa(one.attacks)} حمله")
        lines += ["", "🏯 خاندان شما · 🏴 دشمن"]
    return Screen("\n".join(lines), [c.back("cwar")])


@screen("cwarlog")
async def war_log(c: Ctx) -> Screen:
    wars = await c.services.clan_wars.history(c.player)
    lines = [f"📜 {bold('جنگ‌های گذشته')}", ""]
    if not wars:
        lines.append("هنوز جنگی در کارنامه‌ی خاندان نیست.")
    marks = {"won": "🏆", "lost": "💔", "draw": "🤝"}
    for w in wars:
        pot = f" · گرو {fa(w.stake)}" if w.stake else ""
        lines.append(f"{marks[w.result]} {w.enemy.name} — {fa(w.mine.stars)} به {fa(w.enemy.stars)}{pot}")
    return Screen("\n".join(lines), [c.back("cwar")])
