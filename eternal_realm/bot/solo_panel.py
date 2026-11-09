"""«سفر قهرمان»: solo play in the private chat. Story, daily dungeons, solo bosses, the bot arena and events on the road."""

from __future__ import annotations

from ..game.data import solo as data
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
    lines = [
        f"🧭 {bold('سفر قهرمان')}", LINE,
        "تنها هم می‌شود قهرمان بود! داستان را دنبال کنید، به دخمه‌ها بروید، با باس‌ها بجنگید یا در میدان بات‌ها تمرین کنید.",
        "همه‌ی این نبردها با قدرت، تجهیزات و مهارت خودتان انجام می‌شود و برای ادامه به هیچ بازیکن دیگری نیاز ندارید.",
        LINE, await _energy_line(c),
    ]
    rows = []
    tips = await c.services.advisor.for_player(c.player)
    if tips:
        lines += ["", f"💡 {bold('پیشنهاد فرمانده')}"]
        for tip in tips:
            lines.append(f"{tip.emoji} {tip.text}")
            rows.append([c.btn(f"{tip.emoji} {tip.text}"[:60], tip.screen, tip.arg)])
    if fight is not None:
        lines += ["", f"⚔️ نبرد نیمه‌کاره: {fight.info.get('title', '')}"]
        rows.append([c.btn("⚔️ ادامه‌ی نبرد", "sfight", style="danger")])
    if event is not None:
        lines += ["", f"{event.emoji} اتفاقی در راه منتظر تصمیم شماست: {event.title}"]
        rows.append([c.btn(f"{event.emoji} تصمیم بگیرید", "wander", style="primary")])
    rows += [
        [c.btn("📖 داستان سرزمین فراموش‌شده", "story"), c.btn("🏚️ دخمه‌های روزانه", "dng")],
        [c.btn("🐉 باس‌های تک‌نفره", "sbosses"), c.btn("🥊 میدان بات‌ها", "arena")],
        [c.btn(f"🎲 گشت‌زنی · {fa(data.ENERGY['wander'])}⚡", "wander")],
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


@screen("sfight")
async def fight_view(c: Ctx) -> Screen:
    _guard(c)
    fight = await c.services.solo.active(c.player.id)
    if fight is None:
        raise GameError("نبرد فعالی ندارید.")
    return _fight_screen(c, fight, [])


ACTIONS = {"attack": Action.ATTACK, "skill": Action.SKILL, "defend": Action.DEFEND}


@screen("sact")
async def fight_act(c: Ctx) -> Screen:
    _guard(c)
    action = ACTIONS.get(c.a)
    if action is None:
        raise GameError("این حرکت وجود ندارد.")
    update = await c.services.solo.act(c.player, action)
    return _after(c, update)


@screen("sfleeq")
async def flee_ask(c: Ctx) -> Screen:
    text = f"🏳️ {bold('فرار از نبرد')}\n\nاگر فرار کنید پاداشی نمی‌گیرید و انرژی برنمی‌گردد. مطمئنید؟"
    return Screen(text, [[c.btn("🏳️ بله، فرار", "sfleeok", style="danger"), c.btn("↩️ نه، می‌جنگم", "sfight")]])


@screen("sfleeok")
async def flee_do(c: Ctx) -> Screen:
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
    rows: list = []
    if kind == "arena":
        rows.append([c.btn("🔁 دوباره همین سطح", "arenago", info["tier"], style="success"), c.btn("🥊 میدان", "arena")])
    elif kind == "story":
        nxt = info["stage"] + 1
        if update.won and nxt <= len(data.STAGES):
            rows.append([c.btn(f"➡️ مرحله‌ی بعد: {data.get_stage(nxt).title}", "stage", nxt, style="success")])
        rows.append([c.btn("📖 داستان", "story")])
    elif kind == "dungeon":
        if update.won and info["floor"] < data.FLOORS:
            rows.append([c.btn(f"⬇️ طبقه‌ی {fa(info['floor'] + 1)}", "dngnext", style="success"), c.btn("🚪 خروج با غنیمت", "dng")])
        else:
            rows.append([c.btn("🏚️ دخمه‌ها", "dng")])
    elif kind == "boss":
        rows.append([c.btn("🐉 باس‌ها", "sbosses")])
    rows.append(c.back("trip", "🧭 سفر قهرمان"))
    return Screen("\n".join(text), rows)


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
        "حریفان ساخته‌ی ربات با مهارت‌های گوناگون؛ بی‌انتظار هر وقت خواستید بجنگید.",
        f"🏅 {fa(data.ARENA_FULL_WINS)} برد اول هر روز پاداش کامل دارد و بعدش یک‌سوم.",
        f"📅 بردهای امروز: {fa(done)}", await _energy_line(c), "", "سطح حریف را انتخاب کنید 👇",
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
        lines.append(f"{d.emoji} {d.name} · رکورد شما: طبقه‌ی {fa(best)}")
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
        lines.append(f"{foe.emoji} {foe.name} · سطح {fa(boss.min_level)}" + (f" · {fa(kills)} پیروزی" if kills else "") + (" · امروز زده‌اید" if taken else ""))
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

