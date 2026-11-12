"""«سفر قهرمان»: solo play in the private chat. Story, daily dungeons, solo bosses, the bot arena and events on the road."""

from __future__ import annotations

from ..game.data import maze as maze_data
from ..game.data import solo as data
from ..game.data import world as world_data
from ..game.engine.combat import Action, Fighter
from ..game.services.solo import SoloFight, SoloUpdate
from ..shared.errors import GameError
from ..shared.text import bar, bold, fa
from .panel import Ctx, Screen, _int, screen

LINE = "─" * 12


def _guard(c: Ctx) -> None:
    if c.is_group:
        raise GameError("سفر قهرمان در پیام خصوصی ربات باز می‌شود؛ آنجا بیایید.")


def _hp(f: Fighter) -> list[str]:
    percent = round(100 * max(f.hp, 0) / f.max_hp) if f.max_hp else 0
    return [f"{f.emoji} {bold(f.name)}", f"❤️ {bar(max(f.hp, 0), f.max_hp, 10)} {fa(percent)}٪ · {fa(max(f.hp, 0))}/{fa(f.max_hp)}"]


def _reward_lines(p) -> list[str]:  # noqa: ANN001 - Payout
    from ..game.data.items import get_item

    lines = []
    if p.gold:
        lines.append(f"🪙 {fa(p.gold)} سکه")
    if p.xp:
        lines.append(f"⭐ {fa(p.xp)} تجربه")
    if p.crystal:
        lines.append(f"💎 {fa(p.crystal)} کریستال")
    lines += [f"🎁 {get_item(i).name} ×{fa(q)}" for i, q in p.items.items()]
    return lines or ["چیزی عایدتان نشد"]


async def _energy_line(c: Ctx) -> str:
    p = await c.refresh()
    return f"⚡ انرژی شما: {fa(p.energy)} از {fa(c.services.characters.max_energy(p))}"


# --- the hub ---------------------------------------------------------------------------------------------------------------------------
@screen("trip")
async def trip(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.active(c.player.id)
    event = await c.services.solo.pending_event(c.player.id)
    run = await c.services.solo.maze_run(c.player.id)
    today = await c.services.solo.overview(c.player.id)

    def mark(section: str) -> str:
        return " (امروز انجام شد)" if today.get(f"today:use:{section}", 0) >= data.DAILY_USES else ""

    lines = [
        f"🧭 {bold('سفر قهرمان')}", LINE,
        "تنها هم می‌شود قهرمان بود؛ همه‌ی این بخش‌ها با قدرت و تجهیزات خودتان است و به هیچ بازیکن دیگری نیاز ندارد.",
        f"📅 هر بخش در روز {fa(data.DAILY_USES)} بار باز است.",
        "",
        f"📖 داستان{mark('story')}: ۲۰ مرحله با انتخاب راه؛ سکه، تجربه، صندوقچه و کریستال",
        f"🏚️ دخمه‌ها{mark('dungeon')}: هر روز سه دخمه‌ی پنج‌طبقه؛ طبقه‌به‌طبقه پاداش",
        f"🐉 باس‌ها{mark('boss')}: پنج باس با ترفند؛ کریستال و صندوقچه",
        f"🥊 میدان بات‌ها{mark('arena')}: تمرین در چهار سطح سختی",
        f"♾️ هزارتو{mark('maze')}: {fa(len(maze_data.CHAPTERS))} فصل و {fa(maze_data.FLOORS)} طبقه؛ هر طبقه یک ماجرا و تصمیم، و غول‌هایی که راه را بسته‌اند",
        f"🎲 گشت‌زنی{mark('wander')}: اتفاق‌های راه؛ گنج، راهزن، معما و تاجر مرموز",
        "🗼 برج بی‌پایان: هر طبقه یک نبرد، بی‌پایان و با رتبه‌ی جهانی",
        "🏕️ اعزام: قهرمان را بفرستید و در غیبتتان پاداش بگیرید",
        f"🌍 جهان زنده{mark('world')}: رویداد جهانی و تاریکی مناطق",
        LINE, await _energy_line(c),
    ]
    rows = []
    if fight is not None:
        lines += ["", f"⚔️ نبرد نیمه‌کاره: {fight.info.get('title', '')}"]
        rows.append([c.btn("⚔️ ادامه‌ی نبرد", "sfight", style="danger")])
    elif run is not None:
        lines += ["", f"♾️ هزارتوی نیمه‌کاره: طبقه‌ی {fa(run.floor)}"]
        rows.append([c.btn("♾️ ادامه‌ی هزارتو", "maze", style="success")])
    if event is not None:
        lines += ["", f"{event.emoji} اتفاقی در راه منتظر تصمیم شماست: {event.title}"]
        rows.append([c.btn(f"{event.emoji} تصمیم بگیرید", "wander", style="primary")])
    rows += [
        [c.btn("📖 داستان سرزمین فراموش‌شده", "story"), c.btn("🏚️ دخمه‌های روزانه", "dng")],
        [c.btn("🐉 باس‌های تک‌نفره", "sbosses"), c.btn("🥊 میدان بات‌ها", "arena")],
        [c.btn("♾️ هزارتوی ابدی", "maze", style="primary"), c.btn("🎲 گشت‌زنی", "wanderq")],
        [c.btn("🗼 برج بی‌پایان", "tower"), c.btn("🏕️ اعزام قهرمان", "expd")],
        [c.btn("🌍 جهان زنده", "world", style="primary")],
        c.back("home"),
    ]
    return Screen("\n".join(lines), rows)


# --- the fight itself -------------------------------------------------------------------------------------------------------------------
def _fight_screen(c: Ctx, fight: SoloFight, lines: list[str]) -> Screen:
    battle = fight.battle
    hero, foe = battle.fighters
    text = [f"⚔️ {bold(fight.info.get('title', 'نبرد'))}", LINE, *_hp(hero), "     ⚡ در برابر ⚡", *_hp(foe)]
    story = [f"• {line.strip()}" for line in lines if line.strip()][-5:]
    if story:
        text += ["", f"📜 {bold('آخرین حرکت‌ها')}", *story]
    warn = data.FOES[fight.info["foe"]].warn if fight.info.get("foe") in data.FOES else ""
    if warn and foe.skill_ready:
        text += ["", f"⚠️ {warn}؛ بهتر است دفاع کنید!"]
    text += ["", f"🎯 نوبت شماست · دور {fa(battle.round)} از {fa(battle.max_rounds)}"]
    wait = hero.skill_ready_in - 1
    skill = f"{hero.skill_emoji} {hero.skill_name}" + (f" ({fa(wait)})" if wait > 0 else "")
    rows = [
        [c.btn("⚔️ حمله", "sact", "attack", style="primary"), c.btn(skill, "sact", "skill", style="success" if wait <= 0 else None)],
        [c.btn("🛡️ دفاع", "sact", "defend"), c.btn("🏳️ فرار", "sfleeq", style="danger")],
    ]
    return Screen("\n".join(text), rows)


_RESULT_MARKS = ("پاداش", "پیروزی", "شکست خوردید", "گریختید", "نبرد تمام شد")


async def _stale(c: Ctx) -> Screen:
    """A tap on a fight button when the fight is already over (a double tap, a slow edit): never a dead end.

    If the message already shows the result nothing is touched; otherwise it is replaced by a short result with the way on.
    """
    shown = (getattr(c.message, "text", None) or getattr(c.message, "caption", None) or "") if c.message is not None else ""
    if any(mark in shown for mark in _RESULT_MARKS):
        return Screen(None, toast="این نبرد همین حالا تمام شد ✅")
    fight = await c.services.solo.last_finished(c.player.id)
    if fight is None:
        return Screen(f"🧭 {bold('نبرد تمام شده است')}", [c.back("trip", "🧭 سفر قهرمان")])
    won, fled = fight.status == "won", fight.status == "fled"
    head = "🏆 پیروزی!" if won else "🏳️ از نبرد گریختید" if fled else "💀 شکست خوردید"
    text = [head, bold(fight.info.get("title", "")), LINE, "نبرد تمام شد و نتیجه‌اش (پاداش و پیشرفت) ثبت شده است."]
    return Screen("\n".join(text), _next_rows(c, fight.kind, fight.info, won))


@screen("sfight")
async def fight_view(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.active(c.player.id)
    if fight is None:
        return await _stale(c)
    return _fight_screen(c, fight, [])


ACTIONS = {"attack": Action.ATTACK, "skill": Action.SKILL, "defend": Action.DEFEND}


@screen("sact")
async def fight_act(c: Ctx) -> Screen:
    _guard(c)
    c.recover_to = "sfight"
    action = ACTIONS.get(c.a)
    if action is None:
        raise GameError("این حرکت وجود ندارد.")
    if await c.services.solo.active(c.player.id) is None:
        return await _stale(c)
    update = await c.services.solo.act(c.player, action)
    return _after(c, update)


@screen("sfleeq")
async def flee_ask(c: Ctx) -> Screen:
    if await c.services.solo.active(c.player.id) is None:
        return await _stale(c)
    text = f"🏳️ {bold('فرار از نبرد')}\n\nاگر فرار کنید پاداشی نمی‌گیرید و انرژی برنمی‌گردد. مطمئنید؟"
    return Screen(text, [[c.btn("🏳️ بله، فرار", "sfleeok", style="danger"), c.btn("↩️ نه، می‌جنگم", "sfight")]])


@screen("sfleeok")
async def flee_do(c: Ctx) -> Screen:
    if await c.services.solo.active(c.player.id) is None:
        return await _stale(c)
    update = await c.services.solo.act(c.player, Action.SURRENDER)
    return _after(c, update)


def _after(c: Ctx, update: SoloUpdate) -> Screen:
    if not update.finished:
        return _fight_screen(c, update.fight, update.lines)
    info, kind = update.fight.info, update.fight.kind
    head = "🏆 پیروزی!" if update.won else "🏳️ از نبرد گریختید" if update.fled else "💀 شکست خوردید"
    text = [f"{head}", f"{bold(info.get('title', ''))}", LINE]
    story = [f"• {line.strip()}" for line in update.lines if line.strip()][-3:]
    if story:
        text += [f"📜 {bold('پایان نبرد')}", *story, ""]
    if update.won or update.payout.xp:
        text += [f"🎁 {bold('پاداش')}", *_reward_lines(update.payout)]
    if update.payout.level_up:
        text.append(f"🎉 به سطح {fa(update.payout.level_up.new)} رسیدید!")
    if update.won and update.payout.grade:
        text.append(f"🏅 درجه‌ی این مرحله: {data.GRADES[update.payout.grade]}")
    text += [f"✨ {n}" for n in update.payout.notes]
    if not update.won and not update.fled:
        text += ["", "شکست درس است؛ تجهیزاتتان را بهتر کنید و دوباره بیایید."]
    return Screen("\n".join(text), _next_rows(c, kind, info, update.won))


def _next_rows(c: Ctx, kind: str, info: dict, won: bool) -> list:
    """The buttons under a finished fight: go on, repeat, or back to the hub."""
    rows: list = []
    if kind == "arena":
        rows.append([c.btn("🥊 میدان", "arena")])
    elif kind == "story":
        nxt = info["stage"] + 1
        if won and nxt <= len(data.STAGES):
            rows.append([c.btn(f"➡️ مرحله‌ی بعد: {data.get_stage(nxt).title}", "stage", nxt, style="success")])
        rows.append([c.btn("📖 داستان", "story")])
    elif kind == "dungeon":
        if won and info["floor"] < data.FLOORS:
            rows.append([c.btn(f"⬇️ طبقه‌ی {fa(info['floor'] + 1)}", "dngnext", style="success"), c.btn("🚪 خروج با غنیمت", "dng")])
        else:
            rows.append([c.btn("🏚️ دخمه‌ها", "dng")])
    elif kind == "boss":
        rows.append([c.btn("🐉 باس‌ها", "sbosses")])
    elif kind == "world":
        rows.append([c.btn("🌍 جهان", "world")])
    elif kind == "tower":
        if won:
            rows.append([c.btn("⬆️ طبقه‌ی بعد", "towergo", style="success")])
        rows.append([c.btn("🗼 برج بی‌پایان", "tower")])
    elif kind == "academy":
        if not won:
            rows.append([c.btn("🔁 دوباره امتحان کن", "acfight", style="success")])
        rows.append([c.btn("🎓 برگرد به آکادمی", "aclesson", "fight", style="primary")])
        return rows
    elif kind == "maze":
        if won and info["floor"] < maze_data.chapter_end(info["floor"]):
            rows.append([c.btn("➡️ ادامه‌ی هزارتو", "maze", style="success")])
        else:
            rows.append([c.btn("♾️ هزارتوی ابدی", "maze")])
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return rows


def _start(c: Ctx, fight: SoloFight) -> Screen:
    return _fight_screen(c, fight, [f"نبرد آغاز شد: {fight.battle.fighters[1].name}"])


# --- the bot arena ----------------------------------------------------------------------------------------------------------------------
@screen("arena")
async def arena(c: Ctx) -> Screen:
    _guard(c)
    p = await c.refresh()
    done = (await c.services.solo.overview(p.id)).get("today:arena", 0)
    lines = [
        f"🥊 {bold('میدان بات‌ها')}", LINE,
        "حریفان ساخته‌ی ربات با مهارت‌های گوناگون؛ هر وقت خواستید می‌جنگید و سکه و تجربه می‌گیرید.",
        f"🏅 روزی یک نبرد در میدان باز است؛ سطح حریف را با دقت انتخاب کنید.",
        "",
        "🌱 تازه‌کار: حریفی ملایم برای گرم شدن",
        "⚔️ جنگجو: نبردی هم‌شأن",
        "🔥 قهرمان: حریفی سرسخت با پاداش بیشتر",
        "👑 افسانه‌ای: سخت‌ترین؛ پاداش دو و نیم برابر",
        "", f"📅 بردهای امروز: {fa(done)}", await _energy_line(c), "", "سطح حریف را انتخاب کنید 👇",
    ]
    rows = []
    for tier_id, name, _, reward, need in data.TIERS:
        locked = p.level < need
        label = f"{'🔒' if locked else '⚔️'} {name} · ×{fa(str(reward).replace('.0', ''))} پاداش" + (f" (سطح {fa(need)})" if locked else f" · {fa(data.ENERGY['arena'])}⚡")
        rows.append([c.btn(label, "arenago", tier_id, style=None if locked else "primary")])
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return Screen("\n".join(lines), rows)


@screen("arenago")
async def arena_go(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.start_arena(c.player, c.a)
    await c.refresh()
    return _start(c, fight)


# --- the story -----------------------------------------------------------------------------------------------------------------------------
@screen("story")
async def story(c: Ctx) -> Screen:
    _guard(c)
    p = await c.refresh()
    cleared = (await c.services.solo.overview(p.id)).get("story", 0)
    lines = [
        f"📖 {bold('داستان سرزمین فراموش‌شده')}", LINE,
        "تاریکی از شرق می‌خزد و کسی جز شما نمانده تا جلویش بایستد. در هر مرحله راهتان را انتخاب می‌کنید و نتیجه‌اش را می‌بینید.",
        "", "🎁 هر مرحله سکه و تجربه می‌دهد؛ باس هر فصل صندوقچه و پایان فصل کریستال.",
        "🏅 هر چه با جان بیشتر ببرید، درجه‌ی طلایی و کریستال بیشتر.",
        "", f"📈 پیشرفت: {fa(cleared)} از {fa(len(data.STAGES))} مرحله", await _energy_line(c), "",
    ]
    rows = []
    for number, (title, emoji, need, _) in data.CHAPTERS.items():
        stages = [s for s in data.STAGES if s.chapter == number]
        done = sum(1 for s in stages if s.number <= cleared)
        locked = p.level < need
        lines.append(f"{emoji} فصل {fa(number)}: {title} · {fa(done)}/{fa(len(stages))}" + (f" · از سطح {fa(need)}" if locked else ""))
        rows.append([c.btn(f"{'🔒' if locked else emoji} فصل {fa(number)} · {title}", "storych", number)])
    if cleared < len(data.STAGES):
        nxt = data.get_stage(cleared + 1)
        rows.insert(0, [c.btn(f"▶️ ادامه: {nxt.title}", "stage", nxt.number, style="success")])
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return Screen("\n".join(lines), rows)


@screen("storych")
async def story_chapter(c: Ctx) -> Screen:
    _guard(c)
    number = _int(c.a)
    if number not in data.CHAPTERS:
        raise GameError("این فصل وجود ندارد.")
    p = await c.refresh()
    cleared = (await c.services.solo.overview(p.id)).get("story", 0)
    title, emoji, need, _ = data.CHAPTERS[number]
    lines = [f"{emoji} {bold('فصل ' + fa(number) + ': ' + title)}", ""]
    rows = []
    progress = await c.services.solo.overview(p.id)
    for s in (x for x in data.STAGES if x.chapter == number):
        mark = "✅" if s.number <= cleared else "▶️" if s.number == cleared + 1 else "🔒"
        grade = progress.get(f"grade:{s.number}", 0)
        lines.append(
            f"{mark} مرحله‌ی {fa(s.number)}: {s.title}" + (" (باس فصل)" if s.boss else "")
            + (f" · درجه‌ی {data.GRADES[grade]}" if grade else "")
        )
        if s.number <= cleared + 1 and p.level >= need:
            rows.append([c.btn(f"{mark} {fa(s.number)}. {s.title}", "stage", s.number)])
    if p.level < need:
        lines += ["", f"🔒 این فصل از سطح {fa(need)} باز می‌شود (سطح شما {fa(p.level)})."]
    rows.append(c.back("story"))
    return Screen("\n".join(lines), rows)


@screen("stage")
async def stage_view(c: Ctx) -> Screen:
    _guard(c)
    number = _int(c.a)
    try:
        stage = data.get_stage(number)
    except KeyError:
        raise GameError("این مرحله وجود ندارد.") from None
    p = await c.refresh()
    cleared = (await c.services.solo.overview(p.id)).get("story", 0)
    if number > cleared + 1:
        raise GameError("اول مرحله‌های پیشین را به پایان برسانید.")
    foe = data.get_foe(stage.foe)
    chapter = data.CHAPTERS[stage.chapter]
    lines = [
        f"{stage.emoji} {bold('فصل ' + fa(stage.chapter) + ' · مرحله‌ی ' + fa(number) + ': ' + stage.title)}", LINE,
        stage.text, "",
        f"{foe.emoji} دشمن: {bold(foe.name)}" + (" (باس فصل)" if stage.boss else ""),
        await _energy_line(c), f"⚡ هزینه: {fa(data.ENERGY['story'])} انرژی",
        "", "چه می‌کنید؟ 👇",
    ]
    if number <= cleared:
        lines.insert(-2, "🔁 این مرحله را قبلاً گذرانده‌اید؛ پاداش تکرار یک‌سوم است.")
    if p.level < chapter[2]:
        lines += ["", f"🔒 فصل «{chapter[0]}» از سطح {fa(chapter[2])} باز می‌شود."]
        return Screen("\n".join(lines), [c.back("storych", "🔙 بازگشت", stage.chapter)])
    rows = [[c.btn(label, "stagego", number, way)] for way, label in stage.labels.items()]
    lines.insert(-1, "")
    for way, label in stage.labels.items():
        lines.insert(-1, f"• {label} — {data.STYLE_HINTS[way]}")
    rows.append(c.back("storych", "🔙 بازگشت", stage.chapter))
    return Screen("\n".join(lines), rows)


@screen("stagego")
async def stage_go(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.start_stage(c.player, _int(c.a), c.b)
    await c.refresh()
    return _start(c, fight)


# --- daily dungeons -------------------------------------------------------------------------------------------------------------------------
@screen("dng")
async def dungeons(c: Ctx) -> Screen:
    _guard(c)
    p = await c.refresh()
    now = c.services.ctx.now()
    progress = await c.services.solo.overview(p.id)
    today = data.todays_dungeons((now + 12600) // 86400)
    lines = [
        f"🏚️ {bold('دخمه‌های روزانه')}", LINE,
        f"هر روز سه دخمه‌ی تازه باز است. هر دخمه {fa(data.FLOORS)} طبقه دارد؛ طبقه‌ی آخر نگهبان قدرتمندی دارد و با هر طبقه پاداش می‌گیرید.",
        await _energy_line(c), "",
    ]
    rows = []
    run = progress.get("run", 0)
    if run:
        index, floor = divmod(run, 100)
        d = data.DUNGEONS[index - 1]
        if d in today and floor <= data.FLOORS:
            rows.append([c.btn(f"⬇️ ادامه‌ی {d.name} · طبقه‌ی {fa(floor)}", "dngnext", style="success")])
    for d in today:
        best = progress.get(f"dng:{d.id}", 0)
        lines.append(f"{d.emoji} {d.name} — {d.blurb} (رکورد شما: طبقه‌ی {fa(best)})")
        rows.append([c.btn(f"{d.emoji} {d.name}", "dngv", d.id)])
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return Screen("\n".join(lines), rows)


@screen("dngv")
async def dungeon_view(c: Ctx) -> Screen:
    _guard(c)
    try:
        d = data.get_dungeon(c.a)
    except KeyError:
        raise GameError("این دخمه وجود ندارد.") from None
    p = await c.refresh()
    best = (await c.services.solo.overview(p.id)).get(f"dng:{d.id}", 0)
    lines = [f"{d.emoji} {bold(d.name)}", LINE, d.blurb, "", f"🏅 رکورد شما: طبقه‌ی {fa(best)} از {fa(data.FLOORS)}"]
    for floor in range(1, data.FLOORS + 1):
        foe = data.get_foe(data.floor_foe(d, floor))
        lines.append(f"{foe.emoji} طبقه‌ی {fa(floor)}: {foe.name}" + (" (نگهبان)" if floor == data.FLOORS else ""))
    lines += ["", await _energy_line(c), f"⚡ ورود: {fa(data.ENERGY['dungeon'])} انرژی (همه‌ی طبقه‌ها)", "هر طبقه پاداش دارد و طبقه‌ی آخر یک صندوقچه هم می‌دهد."]
    return Screen("\n".join(lines), [[c.btn("🚪 ورود به دخمه", "dngenter", d.id, style="success")], c.back("dng")])


@screen("dngenter")
async def dungeon_enter(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.start_dungeon(c.player, c.a)
    await c.refresh()
    return _start(c, fight)


@screen("dngnext")
async def dungeon_next(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.next_floor(c.player)
    return _start(c, fight)


# --- solo bosses -------------------------------------------------------------------------------------------------------------------------------
@screen("sbosses")
async def solo_bosses(c: Ctx) -> Screen:
    _guard(c)
    p = await c.refresh()
    progress = await c.services.solo.overview(p.id)
    lines = [
        f"🐉 {bold('باس‌های تک‌نفره')}", LINE,
        "هر باس یک ترفند دارد؛ نشانه‌ها را بخوانید و درست پاسخ بدهید. پاداش ویژه‌ی هر باس روزی یک بار است.",
        await _energy_line(c), "",
    ]
    rows = []
    for boss in data.SOLO_BOSSES:
        foe = data.get_foe(boss.foe)
        locked = p.level < boss.min_level
        taken = progress.get(f"today:boss:{boss.foe}", 0)
        kills = progress.get(f"boss:{boss.foe}", 0)
        lines.append(
            f"{foe.emoji} {foe.name} · از سطح {fa(boss.min_level)} · ضربه‌ی ویژه: {foe.skill[0]}"
            + (f" · {fa(kills)} پیروزی" if kills else "") + (" · امروز زده‌اید" if taken else "")
        )
        rows.append([c.btn(f"{'🔒' if locked else foe.emoji} {foe.name}", "sbossv", boss.foe)])
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return Screen("\n".join(lines), rows)


@screen("sbossv")
async def solo_boss_view(c: Ctx) -> Screen:
    _guard(c)
    try:
        boss, foe = data.get_solo_boss(c.a), data.get_foe(c.a)
    except StopIteration:
        raise GameError("این باس وجود ندارد.") from None
    from ..game.data.items import get_item

    p = await c.refresh()
    name, emoji, kind, power, cooldown, effect = foe.skill
    lines = [
        f"{foe.emoji} {bold(foe.name)}", LINE,
        f"🎚️ از سطح {fa(boss.min_level)}",
        f"{emoji} ضربه‌ی ویژه: {name} (هر {fa(cooldown)} نوبت)",
        f"⚠️ {foe.warn}" if foe.warn else "",
        "", f"🎁 {bold('پاداش اولین پیروزی امروز')}",
        f"🪙 {fa(round(boss.gold * 1.0))} سکه (به‌اندازه‌ی سطح)", f"⭐ {fa(boss.xp)} تجربه (به‌اندازه‌ی سطح)",
        f"💎 {fa(boss.crystal)} کریستال", f"🎁 {get_item(boss.item[0]).name}", "",
        await _energy_line(c), f"⚡ هزینه: {fa(data.ENERGY['boss'])} انرژی",
    ]
    rows = []
    if p.level >= boss.min_level:
        rows.append([c.btn("⚔️ نبرد با باس", "sbossgo", boss.foe, style="danger")])
    else:
        lines += ["", f"🔒 هنوز به سطح {fa(boss.min_level)} نرسیده‌اید."]
    rows.append(c.back("sbosses"))
    return Screen("\n".join(x for x in lines if x is not None), rows)


@screen("sbossgo")
async def solo_boss_go(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.start_boss(c.player, c.a)
    await c.refresh()
    return _start(c, fight)


# --- events on the road ----------------------------------------------------------------------------------------------------------------------------
def _event_screen(c: Ctx, event: data.RoadEvent) -> Screen:
    text = f"{event.emoji} {bold(event.title)}\n{LINE}\n{event.text}\n\nچه می‌کنید؟ 👇"
    rows = [[c.btn(choice.label, "wch", i)] for i, choice in enumerate(event.choices)]
    return Screen(text, rows)


@screen("wander")
async def wander(c: Ctx) -> Screen:
    _guard(c)
    event = await c.services.solo.pending_event(c.player.id)
    if event is None:
        event = await c.services.solo.wander(c.player)
        await c.refresh()
    return _event_screen(c, event)


@screen("wch")
async def wander_choose(c: Ctx) -> Screen:
    _guard(c)
    result = await c.services.solo.decide(c.player, _int(c.a))
    if result.fight is not None:
        return _start(c, result.fight)
    lines = [f"🎲 {bold('سرانجام')}", LINE, *result.lines]
    reward = _reward_lines(result.payout) if (result.payout.gold or result.payout.xp or result.payout.crystal or result.payout.items) else []
    if reward:
        lines += ["", f"🎁 {bold('دستاورد')}", *reward]
    rows = [[c.btn(f"🎲 دوباره گشت بزن · {fa(data.ENERGY['wander'])}⚡", "wander")], c.back("trip", "🧭 سفر قهرمان")]
    return Screen("\n".join(lines), rows)



# --- the eternal maze ------------------------------------------------------------------------------------------------------------------------
@screen("maze")
async def maze(c: Ctx) -> Screen:
    _guard(c)
    run = await c.services.solo.maze_run(c.player.id)
    progress = await c.services.solo.overview(c.player.id)
    best = progress.get("maze:best", 0)
    if run is None:
        done = await c.services.solo.maze_chapters_done(c.player.id)
        total = len(maze_data.CHAPTERS)
        if done >= total:
            lines = [
                f"♾️ {bold('هزارتوی ابدی')}", LINE,
                f"🏆 هر {fa(total)} فصل هزارتو را فتح کرده‌اید.",
                "هزارتو برای هر قهرمان فقط یک بار باز است و دیگر درهایش بسته شد؛ این افسانه برای همیشه به نام شماست.",
                f"🏅 رکورد شما: طبقه‌ی {fa(best)}",
            ]
            return Screen("\n".join(lines), [c.back("trip", "🧭 سفر قهرمان")])
        title, icon = maze_data.CHAPTERS[done]
        first = done * maze_data.CHAPTER_FLOORS + 1
        last = first + maze_data.CHAPTER_FLOORS - 1
        lines = [
            f"♾️ {bold('هزارتوی ابدی')}", LINE,
            f"{icon} {bold('فصل ' + fa(done + 1) + ': ' + title)}",
            f"طبقه‌ی {fa(first)} تا {fa(last)} · هر طبقه ماجرایی تازه و تصمیمی تازه دارد.",
            "👹 هر دو سه طبقه یک غول راه را بسته است و هر چه پایین‌تر بروید سرسخت‌تر می‌شود؛ اگر شکست خوردید، قوی‌تر برگردید.",
            "برکت‌ها فقط تا پایان همین فصل می‌مانند. با بیرون آمدن، همه‌ی غنیمت می‌ماند؛ با شکست، نیمی از آن.",
            f"📚 فصل‌ها: {fa(done)} از {fa(total)} فتح شده · هر فصل پس از فتح، دوباره باز نمی‌شود.",
            f"🏅 رکورد شما: طبقه‌ی {fa(best)}",
            "", f"🎁 {bold('پاداش ماندگار نگهبان‌های این فصل')}",
            *[f"طبقه‌ی {fa(f)}: {fa(cr)} کریستال و صندوقچه" for f, (cr, _) in maze_data.MILESTONES.items() if first <= f <= last],
            "", await _energy_line(c), f"⚡ ورود: {fa(maze_data.ENERGY)} انرژی",
        ]
        rows = [[c.btn("🚪 ورود به هزارتو", "mazego", style="success")], c.back("trip", "🧭 سفر قهرمان")]
        return Screen("\n".join(lines), rows)
    chapter = maze_data.chapter_of(run.floor)
    lines = [
        f"♾️ {bold('هزارتوی ابدی')}", LINE,
        f"{maze_data.CHAPTERS[chapter - 1][1]} فصل {fa(chapter)}: {maze_data.CHAPTERS[chapter - 1][0]}",
        f"🏚️ طبقه‌ی {fa(run.floor)} از {fa(maze_data.chapter_end(run.floor))}",
        f"❤️ {bar(round(run.hp * 100), 100, 10)} {fa(round(run.hp * 100))}٪ جان",
    ]
    names = {"atk": "قدرت حمله", "def": "دفاع", "hp": "جان"}
    for stat, amount in run.buffs.items():
        if amount:
            lines.append(f"{'✨' if amount > 0 else '🕸️'} {names[stat]}: {'+' if amount > 0 else '-'}{fa(round(abs(amount) * 100))}٪")
    lines += [f"🪙 غنیمت تا اینجا: {fa(run.gold)} سکه و {fa(run.xp)} تجربه", LINE]
    rows = []
    active = await c.services.solo.active(c.player.id)
    if active is not None:  # a fight of this run is still going: the way on is the fight, never a dead choice
        lines += [f"⚔️ {bold('نبردی نیمه‌کاره دارید')}", active.info.get("title", ""), "", "اول نبرد را تمام کنید 👇"]
        rows.append([c.btn("⚔️ ادامه‌ی نبرد", "sfight", style="danger")])
        return Screen("\n".join(lines), rows)
    if run.kind == "giant":
        tier, foe = run.tier or "giant", data.get_foe(run.ref)
        level = maze_data.foe_level(run.floor, c.player.level)
        lines += [
            f"{foe.emoji} {bold(maze_data.TIERS[tier][0] + ': ' + foe.name)}",
            maze_data.giant_text(tier, run.floor, foe.name), "",
            f"🎚️ قدرت او هم‌تراز سطح {fa(level)} است · سطح شما {fa(c.player.level)}",
        ]
        if level > c.player.level + 1:
            lines.append("⚠️ این دشمن از شما قوی‌تر است؛ اگر شکست خوردید، سطحتان را بالا ببرید و برگردید.")
        if foe.warn:
            lines.append(f"💡 نشانه‌ی ضربه‌ی ویژه‌اش: {foe.warn}")
        lines += ["", "چه می‌کنید؟ 👇"]
        rows.append([c.btn("⚔️ تیغ می‌کشم و می‌جنگم", "mazepick", 0, style="danger")])
        if tier == "giant":
            rows.append([c.btn("🌫️ از سایه‌ها دزدکی رد می‌شوم", "mazepick", 1)])
    else:
        scene = maze_data.SCENES[run.ref]
        lines += [
            f"{scene.emoji} {bold(scene.title)}", scene.text, "",
            f"👣 غول بعدی در طبقه‌ی {fa(maze_data.next_giant(run.floor))} منتظر است" if run.floor < maze_data.chapter_end(run.floor) else "",
            "چه می‌کنید؟ 👇",
        ]
        rows += [[c.btn(choice.label, "mazepick", i)] for i, choice in enumerate(scene.choices)]
    rows.append([c.btn("🚪 بیرون آمدن با غنیمت", "mazeoutq")])
    return Screen("\n".join(lines), rows)


@screen("mazego")
async def maze_go(c: Ctx) -> Screen:
    _guard(c)
    await c.services.solo.maze_start(c.player)
    await c.refresh()
    return await maze(c)


@screen("mazepick")
async def maze_pick(c: Ctx) -> Screen:
    _guard(c)
    c.recover_to = "maze"
    step = await c.services.solo.maze_pick(c.player, _int(c.a))
    if step.fight is not None:
        await c.show(f"⚔️ {bold('نبرد در هزارتو!')}\n\n" + "\n".join(step.lines))
        return _fight_screen(c, step.fight, step.lines[:1])
    await c.show(f"🎲 {bold('سرنوشت رقم می‌خورد...')}\n\n{step.lines[0]}")
    shown = await maze(c)
    extra = [f"📜 {bold('در راه چه گذشت')}", *step.lines, ""]
    shown.text = "\n".join(extra) + (shown.text or "")
    return shown


@screen("mazeoutq")
async def maze_out_ask(c: Ctx) -> Screen:
    run = await c.services.solo.maze_run(c.player.id)
    if run is None:
        raise GameError("هزارتویی در جریان ندارید.")
    text = (
        f"🚪 {bold('بیرون آمدن از هزارتو')}\n\nبا همین غنیمت بیرون می‌آیید: {fa(run.gold)} سکه و {fa(run.xp)} تجربه. "
        "نیروهای موقتتان از بین می‌رود. مطمئنید؟"
    )
    return Screen(text, [[c.btn("🚪 بله، بیرون برویم", "mazeout", style="success"), c.btn("↩️ نه، ادامه", "maze")]])


@screen("mazeout")
async def maze_out(c: Ctx) -> Screen:
    _guard(c)
    pay = await c.services.solo.maze_retreat(c.player)
    text = [f"🚪 {bold('از هزارتو بیرون آمدید')}", LINE, f"🎁 {bold('غنیمت')}", *_reward_lines(pay)]
    if pay.level_up:
        text.append(f"🎉 به سطح {fa(pay.level_up.new)} رسیدید!")
    return Screen("\n".join(text), [[c.btn("♾️ هزارتو", "maze")], c.back("trip", "🧭 سفر قهرمان")])


# --- the endless tower ----------------------------------------------------------------------------------------------------------------------
@screen("tower")
async def tower(c: Ctx) -> Screen:
    _guard(c)
    p = await c.refresh()
    cleared, best, today = await c.services.solo.tower_state(p.id)
    board = await c.services.solo.tower_board(5)
    nxt = cleared + 1
    lines = [
        f"🗼 {bold('برج بی‌پایان')}", LINE,
        "هر طبقه یک نبرد است و هر طبقه از قبلی سخت‌تر؛ برج پایان ندارد. اگر ببازید، طبقه‌ای از دست نمی‌دهید و دوباره امتحان می‌کنید.",
        f"👹 در هر دهمین طبقه یک نگهبان بزرگ ایستاده و بار نخست شکستنش جایزه‌ی ماندگار دارد.",
        "",
        f"🏅 رکورد شما: طبقه‌ی {fa(best)}",
        f"⬆️ طبقه‌ی بعدی: {fa(nxt)}" + (" · نگهبان" if nxt % 10 == 0 else ""),
        f"📅 صعودهای امروز: {fa(today)} (تا {fa(maze_data.TOWER_FULL_CLIMBS)} صعود پاداش کامل است)",
    ]
    if board:
        lines += ["", f"🌍 {bold('بلندترین صعودکنندگان')}"]
        medals = ("🥇", "🥈", "🥉", "🔹", "🔹")
        lines += [f"{medals[i - 1]} {name} — طبقه‌ی {fa(top)}" for i, name, top in board]
    lines += ["", await _energy_line(c), f"⚡ هر صعود: {fa(maze_data.TOWER_ENERGY)} انرژی"]
    rows = [[c.btn(f"⬆️ صعود به طبقه‌ی {fa(nxt)}", "towergo", style="danger")], c.back("trip", "🧭 سفر قهرمان")]
    return Screen("\n".join(lines), rows)


@screen("towergo")
async def tower_go(c: Ctx) -> Screen:
    _guard(c)
    return _start(c, await c.services.solo.start_tower(c.player))


# --- offline expeditions --------------------------------------------------------------------------------------------------------------------
@screen("expd")
async def expedition(c: Ctx) -> Screen:
    _guard(c)
    from ..game.data import expedition as ed
    from ..shared.text import duration

    now = c.services.ctx.now()
    trip = await c.services.expeditions.current(c.player.id)
    used = await c.services.expeditions.today(c.player.id)
    lines = [f"🏕️ {bold('اعزام قهرمان')}", LINE]
    if trip is not None:
        kind = ed.get_kind(trip.kind)
        if trip.ends_at <= now:
            lines += [f"{kind.emoji} {kind.name} تمام شد!", "قهرمان شما برگشته و گزارش و پاداشش را آورده است."]
            return Screen("\n".join(lines), [[c.btn("📜 گرفتن گزارش و پاداش", "expdclaim", style="success")], c.back("trip", "🧭 سفر قهرمان")])
        done = (now - trip.started_at) / max(1, trip.ends_at - trip.started_at)
        lines += [
            f"{kind.emoji} {kind.name}",
            f"{bar(round(done * 100), 100, 10)} {fa(round(done * 100))}٪",
            f"⏳ {duration(trip.ends_at - now)} تا بازگشت",
            "", "وقتی برگشت برایتان پیام می‌فرستم.",
        ]
        cost = c.services.expeditions.recall_cost(trip.ends_at - now)
        return Screen("\n".join(lines), [
            [c.btn("🔄 تازه‌سازی", "expd"), c.btn(f"⏪ برگرداندن قهرمان · {fa(cost)}💎", "awayq", style="danger")],
            c.back("trip", "🧭 سفر قهرمان"),
        ])
    lines += [
        "قهرمانتان را برای ساعت‌ها به کاری بفرستید؛ حتی وقتی در بازی نیستید برمی‌گردد و گزارش می‌دهد.",
        f"⏳ مدت: {', '.join(fa(h) for h in ed.HOURS)} ساعت · هر روز حداکثر {fa(ed.DAILY_LIMIT)} اعزام (امروز {fa(used)})",
        "پاداش اعزام کوچک‌تر از ماجراجویی فعال است تا ماجراجویی ارزشمندتر بماند.",
        "", "کجا بفرستیمش؟ 👇",
    ]
    rows = [[c.btn(f"{k.emoji} {k.name} · {k.about}", "expdk", k.id)] for k in ed.KINDS]
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return Screen("\n".join(lines), rows)


@screen("awayq")
async def recall_confirm(c: Ctx) -> Screen:
    """Works in groups too: the notice that a hero is away carries a button to this page."""
    now = c.services.ctx.now()
    trip = await c.services.expeditions.current(c.player.id)
    if trip is None or trip.ends_at <= now:
        return Screen(f"🏕️ {bold('قهرمان شما برگشته است')}\n\nدیگر چیزی برای احضار نیست؛ گزارش اعزام را در پیوی ربات بگیرید.", [])
    from ..shared.text import duration

    cost = c.services.expeditions.recall_cost(trip.ends_at - now)
    p = await c.refresh()
    lines = [
        f"⏪ {bold('احضار سریع قهرمان')}", "",
        "می‌خواهید قهرمانتان سریع‌تر برگردد؟", "",
        f"⏳ زمان باقی‌مانده: {duration(trip.ends_at - now)}",
        f"💎 هزینه: {fa(cost)} کریستال (هر چه زمان کمتر، کریستال کمتر)",
        f"👛 کریستال شما: {fa(p.crystal)}", "",
        "با احضار، پاداش کامل اعزام را هم می‌گیرید.",
    ]
    return Screen("\n".join(lines), [[c.btn("✅ تأیید", "awayok", style="success"), c.btn("❌ انصراف", "awayno", style="danger")]])


@screen("awayok")
async def recall_apply(c: Ctx) -> Screen:
    cost = await c.services.expeditions.recall(c.player)
    lines = [
        f"🏕️ {bold('قهرمان شما احضار شد!')}", "",
        "فرمان شما در دشت و کوه پیچید و قهرمانتان شتابان به قلمرو بازگشت.", "",
        f"💎 {fa(cost)} کریستال پرداخت شد.",
        "🎁 گزارش و پاداش اعزام آماده است؛ در پیوی ربات، بخش «سفر قهرمان» بگیریدش.", "",
        "⚔️ اکنون هر نبردی که می‌خواهید در پیش است!",
    ]
    return Screen("\n".join(lines), [])


@screen("awayno")
async def recall_cancel(c: Ctx) -> Screen:
    return Screen(f"👌 {bold('انصراف دادید')}\n\nقهرمان به اعزامش ادامه می‌دهد.", [])


@screen("expdk")
async def expedition_kind(c: Ctx) -> Screen:
    _guard(c)
    from ..game.data import expedition as ed

    try:
        kind = ed.get_kind(c.a)
    except KeyError:
        raise GameError("چنین اعزامی نیست.") from None
    from ..game.data.items import get_item
    from ..game.engine import loot

    level = (await c.refresh()).level
    gives = []
    if kind.gold:
        gives.append(f"🪙 حدود {fa(round(kind.gold * loot.level_scale(level)))} سکه در هر ساعت")
    if kind.xp:
        gives.append(f"⭐ حدود {fa(round(kind.xp * loot.xp_scale(level)))} تجربه در هر ساعت")
    gives += [
        f"{get_item(i).emoji} {get_item(i).name}: " + (f"حدود {fa(round(q))} عدد در هر ساعت" if q >= 1 else f"حدود ۱ عدد در هر {fa(round(1 / q))} ساعت")
        for i, q, _ in kind.items
    ]
    lines = [f"{kind.emoji} {bold(kind.name)}", LINE, kind.about, "", f"🎁 {bold('چه چیزی برمی‌گرداند')}", *gives,
             "", "چند ساعت؟ 👇"]
    rows = [[c.btn(f"⏳ {fa(h)} ساعت", "expdgo", kind.id, h)] for h in ed.HOURS]
    rows.append(c.back("expd"))
    return Screen("\n".join(lines), rows)


@screen("expdgo")
async def expedition_go(c: Ctx) -> Screen:
    _guard(c)
    await c.services.expeditions.start(c.player, c.a, _int(c.b))
    shown = await expedition(c)
    shown.toast = "🏕️ قهرمان شما راهی شد"
    return shown


@screen("expdclaim")
async def expedition_claim(c: Ctx) -> Screen:
    _guard(c)
    report = await c.services.expeditions.claim(c.player)
    lines = [
        f"📜 {bold('گزارش اعزام شما')}", LINE,
        f"{report.kind.emoji} {report.kind.name} · {fa(report.hours)} ساعت", "",
        "در مدت غیبت شما، قهرمانتان این کارها را انجام داد:",
        *[f"• {line}" for line in (report.lines or ["روزی آرام بود و چیزی دیده نشد"])],
    ]
    if report.crystal:
        lines.append(f"💎 {fa(report.crystal)} کریستال هم یافت")
    if report.level_up:
        lines.append(f"🎉 به سطح {fa(report.level_up.new)} رسیدید!")
    return Screen("\n".join(lines), [[c.btn("🏕️ اعزام دوباره", "expd", style="success")], c.back("trip", "🧭 سفر قهرمان")])


# --- the living world ---------------------------------------------------------------------------------------------------------------------------
@screen("world")
async def world(c: Ctx) -> Screen:
    _guard(c)
    from ..shared.text import duration

    now = c.services.ctx.now()
    event = await c.services.world.active(c.player.id)
    lines = [
        f"🌍 {bold('جهان زنده')}", LINE,
        "جهان بی‌توجه به حضور شما هم می‌چرخد: تاریکی مناطق کم‌کم زیاد می‌شود و هر پیروزی شما آن را عقب می‌راند.",
        "منطقه‌ی تاریک‌تر دشمنان قوی‌تری دارد، اما پاداشش بیشتر است.", "",
    ]
    for r in await c.services.world.regions():
        lines.append(f"{r.region.emoji} {r.region.name} — {r.status} · {bar(round(r.darkness), 100, 6)} {fa(round(r.darkness))}٪")
    rows = []
    if event is not None:
        left = event.ends_at - now
        lines += [
            LINE, f"📢 {bold('خبر فوری قلمرو')}", f"{event.kind.emoji} {bold(event.kind.title)}", event.kind.text, "",
            f"⏳ زمان باقی‌مانده: {duration(left)}",
            f"📊 پیشرفت: {bar(event.points, event.max_points, 10)} {fa(min(100, round(100 * event.points / event.max_points)))}٪",
            "برای مشارکت، با نگهبان رویداد بجنگید؛ هر چه آسیب بیشتر، سهم بیشتر.",
            f"🧮 سهم شما: {fa(event.mine)} امتیاز",
        ]
        if event.top:
            lines += ["", f"🏆 {bold('برترین مشارکت‌کنندگان')}"] + [f"{fa(i + 1)}. {n} — {fa(p)}" for i, (n, p) in enumerate(event.top)]
        rows.append([c.btn(f"⚔️ نبرد با نگهبان رویداد · {fa(world_data.ENERGY)}⚡", "worldgo", style="danger")])
    else:
        lines += [LINE, "الان رویداد جهانی فعالی نیست. چند ساعت دیگر خبر تازه‌ای می‌رسد."]
    last = await c.services.world.last_result()
    if last is not None:
        lines += ["", f"📜 آخرین رویداد: {last.kind.title} — {'با موفقیت دفع شد' if last.status == 'won' else 'دفع نشد'}"]
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return Screen("\n".join(lines), rows)


@screen("worldgo")
async def world_go(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.start_world_fight(c.player)
    await c.refresh()
    return _start(c, fight)


@screen("wanderq")
async def wander_intro(c: Ctx) -> Screen:
    _guard(c)
    if await c.services.solo.pending_event(c.player.id) is not None:
        return await wander(c)
    lines = [
        f"🎲 {bold('گشت‌زنی')}", LINE,
        "در جاده‌ها قدم می‌زنید و هر بار اتفاقی پیش می‌آید: مسافری زخمی، صندوقی کهنه، راهزنی کمین‌کرده، تاجری مرموز، مسیری مخفی یا غریبه‌ای با درخواستی عجیب.",
        "",
        "برای هر اتفاق دو راه دارید؛ کمک یا غارت، معامله یا گذشتن، جنگ یا باج دادن.",
        "🎁 سرانجام می‌تواند سکه، تجربه، آیتم، کریستال یا یک نبرد باشد.",
        "", await _energy_line(c), f"⚡ هزینه: {fa(data.ENERGY['wander'])} انرژی",
    ]
    return Screen("\n".join(lines), [[c.btn("🎲 بزن بریم", "wander", style="success")], c.back("trip", "🧭 سفر قهرمان")])
