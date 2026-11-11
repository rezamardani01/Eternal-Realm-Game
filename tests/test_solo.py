import json
import re

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import solo as data
from eternal_realm.game.engine.combat import Action
from eternal_realm.shared.errors import GameError
from eternal_realm.shared.text import EMOJI, fa

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid=1, level=10, name=None):
    p = await services.players.register(uid, f"u{uid}", name or f"قهرمان{uid}", "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, energy = 500 WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


async def rig(db, player_id, foe_hp=1):
    """Make the enemy of the fight in progress a pushover."""
    async with db.transaction() as tx:
        row = await tx.fetchone("SELECT id, state FROM solo_fights WHERE player_id = ? AND status = 'active'", (player_id,))
        state = json.loads(row["state"])
        state["fighters"][1]["hp"] = foe_hp
        state["fighters"][0]["hp"] = state["fighters"][0]["max_hp"]
        await tx.execute("UPDATE solo_fights SET state = ? WHERE id = ?", (json.dumps(state), row["id"]))


async def finish(services, db, player, win=True):
    if win:
        await rig(db, player.id)
    for _ in range(60):
        fight = await services.solo.active(player.id)
        if fight is None:
            raise AssertionError("the fight ended without a verdict")
        update = await services.solo.act(player, Action.ATTACK)
        if update.finished:
            return update
    raise AssertionError("fight did not end")


def test_the_tables_are_sound():
    assert [s.number for s in data.STAGES] == list(range(1, 21))
    assert [s.number for s in data.STAGES if s.boss] == [6, 11, 16, 20]
    for s in data.STAGES:
        assert s.foe in data.FOES and s.labels and set(s.labels) <= set(data.STYLES) and set(s.labels) <= set(data.STYLE_HINTS)
    assert all(f in data.CALIB for f in data.FOES)
    assert all(b in data.FOES for b in data.ARENA_BOTS)
    for d in data.DUNGEONS:
        assert all(f in data.FOES for f in (*d.foes, d.boss))
    assert {b.foe for b in data.SOLO_BOSSES} <= set(data.FOES) and len(data.SOLO_BOSSES) == 5
    for day in range(10):
        assert len({d.id for d in data.todays_dungeons(day)}) == 3
    assert all(len(e.choices) >= 2 for e in data.EVENTS)


async def test_the_arena_costs_energy_pays_once_and_slows_down_after_ten_wins(services, db):
    p = await hero(services, db)
    before = (await services.players.require(1)).energy
    await services.solo.start_arena(p, "normal")
    assert (await services.players.require(1)).energy <= before - 5 + 1
    with pytest.raises(GameError, match="نیمه‌کاره"):
        await services.solo.start_arena(p, "normal")
    gold = (await services.players.require(1)).gold
    update = await finish(services, db, p)
    assert update.won and update.payout.gold > 0 and (await services.players.require(1)).gold == gold + update.payout.gold
    assert await services.solo.active(p.id) is None
    first = update.payout.gold
    for _ in range(data.ARENA_FULL_WINS - 1):
        await services.solo.start_arena(p, "normal")
        await finish(services, db, p)
    await services.solo.start_arena(p, "normal")
    late = await finish(services, db, p)
    assert late.payout.gold <= first // 3 + 1 and any("یک‌سوم" in n for n in late.payout.notes)
    with pytest.raises(GameError, match="سطح"):
        await services.solo.start_arena(p, "legend")


async def test_fleeing_pays_nothing_and_a_loss_pays_a_little(services, db):
    p = await hero(services, db)
    await services.solo.start_arena(p, "normal")
    gold = (await services.players.require(1)).gold
    update = await services.solo.act(p, Action.SURRENDER)
    assert update.fled and not update.won and (await services.players.require(1)).gold == gold and update.payout.xp == 0
    await services.solo.start_arena(p, "normal")
    async with db.transaction() as tx:  # the hero is on his last legs
        row = await tx.fetchone("SELECT id, state FROM solo_fights WHERE player_id = ? AND status = 'active'", (p.id,))
        state = json.loads(row["state"])
        state["fighters"][0]["hp"] = 1
        state["fighters"][1]["atk"] = 10_000
        await tx.execute("UPDATE solo_fights SET state = ? WHERE id = ?", (json.dumps(state), row["id"]))
    lost = await finish(services, db, p, win=False)
    assert not lost.won and not lost.fled and lost.payout.gold == 0 and lost.payout.xp > 0
    with pytest.raises(GameError, match="فعالی ندارید"):
        await services.solo.act(p, Action.ATTACK)


async def test_the_story_goes_stage_by_stage_pays_a_third_on_replay_and_gates_chapters(services, db):
    p = await hero(services, db, level=3)
    with pytest.raises(GameError, match="پیشین"):
        await services.solo.start_stage(p, 2, "fight")
    with pytest.raises(GameError, match="راه"):
        await services.solo.start_stage(p, 1, "bold")  # stage 1 has no such way
    await services.solo.start_stage(p, 1, "mercy")
    first = await finish(services, db, p)
    assert first.won and (await services.solo.overview(p.id))["story"] == 1
    await services.solo.start_stage(p, 1, "mercy")
    again = await finish(services, db, p)
    assert again.payout.gold < first.payout.gold
    for number in (2, 3, 4, 5):
        await services.solo.start_stage(p, number, "fight")
        await finish(services, db, p)
    crystals = (await services.players.require(1)).crystal
    await services.solo.start_stage(p, 6, "fight")
    boss = await finish(services, db, p)
    assert boss.payout.crystal >= data.CHAPTER_DONE_CRYSTALS and any("فصل" in n for n in boss.payout.notes)
    assert (await services.players.require(1)).crystal == crystals + boss.payout.crystal
    async with db.read() as tx:
        assert await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = 'magic_chest'", (p.id,), 0) == 1
    with pytest.raises(GameError, match="سطح"):
        await services.solo.start_stage(p, 7, "fight")  # chapter 2 opens at level 5
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 6 WHERE id = ?", (p.id,))
    await services.solo.start_stage(await services.players.require(1), 7, "plunder")
    await services.solo.abandon(p)


async def test_dungeons_open_three_a_day_and_floors_pay_as_you_go(services, db):
    p = await hero(services, db)
    day = (services.ctx.now() + 12600) // 86400
    today = data.todays_dungeons(day)
    closed = next(d for d in data.DUNGEONS if d not in today)
    with pytest.raises(GameError, match="بسته"):
        await services.solo.start_dungeon(p, closed.id)
    dungeon = today[0]
    energy = (await services.players.require(1)).energy
    await services.solo.start_dungeon(p, dungeon.id)
    spent = energy - (await services.players.require(1)).energy
    gold = (await services.players.require(1)).gold
    one = await finish(services, db, p)
    assert one.won and (await services.players.require(1)).gold > gold
    assert any("رکورد" in n for n in one.payout.notes)
    for _ in range(2, data.FLOORS + 1):
        await services.solo.next_floor(p)  # no new energy
        assert (await finish(services, db, p)).won
    assert (await services.players.require(1)).energy >= energy - spent - 2
    assert (await services.solo.overview(p.id))[f"dng:{dungeon.id}"] == data.FLOORS
    async with db.read() as tx:
        assert await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = 'wooden_chest'", (p.id,), 0) >= 1
    with pytest.raises(GameError, match="جریان"):
        await services.solo.next_floor(p)  # the run is over
    await services.solo.start_dungeon(p, dungeon.id)  # a flight ends the run
    await services.solo.act(p, Action.SURRENDER)
    with pytest.raises(GameError, match="جریان"):
        await services.solo.next_floor(p)


async def test_solo_bosses_have_a_level_gate_and_a_daily_prize(services, db):
    p = await hero(services, db, level=6)
    with pytest.raises(GameError, match="سطح"):
        await services.solo.start_boss(p, "boss_red_dragon")
    crystals = (await services.players.require(1)).crystal
    await services.solo.start_boss(p, "boss_undead_king")
    first = await finish(services, db, p)
    boss = data.get_solo_boss("boss_undead_king")
    assert first.payout.crystal == boss.crystal and first.payout.items == {boss.item[0]: boss.item[1]}
    assert (await services.players.require(1)).crystal == crystals + boss.crystal
    await services.solo.start_boss(p, "boss_undead_king")
    second = await finish(services, db, p)
    assert second.payout.crystal == 0 and not second.payout.items and second.payout.gold < first.payout.gold
    assert (await services.solo.overview(p.id))["boss:boss_undead_king"] == 2


async def test_events_on_the_road(services, db):
    p = await hero(services, db)
    energy = (await services.players.require(1)).energy
    event = await services.solo.wander(p)
    assert (await services.players.require(1)).energy <= energy - 3 + 1
    with pytest.raises(GameError, match="منتظر"):
        await services.solo.wander(p)
    assert (await services.solo.pending_event(p.id)).id == event.id
    with pytest.raises(GameError, match="گزینه"):
        await services.solo.decide(p, 9)
    result = await services.solo.decide(p, 0)
    assert result.lines or result.fight
    if result.fight is not None:
        await services.solo.abandon(p)
    assert await services.solo.pending_event(p.id) is None
    with pytest.raises(GameError, match="اتفاقی"):
        await services.solo.decide(p, 0)
    # every choice of every event can be played through
    for e in data.EVENTS:
        for i in range(len(e.choices)):
            async with db.transaction() as tx:
                await tx.execute("UPDATE solo_fights SET status = 'fled' WHERE player_id = ?", (p.id,))
                await tx.execute(
                    "INSERT INTO solo_progress (player_id, key, n) VALUES (?, 'event', ?)"
                    " ON CONFLICT (player_id, key) DO UPDATE SET n = excluded.n", (p.id, data.EVENTS.index(e) + 1),
                )
                await wallet.apply(tx, p.id, gold=1_000, reason="t", now=services.ctx.now())
            res = await services.solo.decide(p, i)
            assert res.lines or res.fight


async def test_the_hub_and_a_whole_session_through_buttons(h, services, db):
    p = await hero(services, db)
    await h.say(1, "/start")
    assert "🧭 سفر قهرمان" in h.labels()
    await h.panel(1, "trip")
    assert {"📖 داستان سرزمین فراموش‌شده", "🏚️ دخمه‌های روزانه", "🐉 باس‌های تک‌نفره", "🥊 میدان بات‌ها"} <= set(h.labels())
    for screen_name, arg in [("trip", ""), ("arena", ""), ("story", ""), ("storych", "1"), ("stage", "1"), ("dng", ""),
                             ("sbosses", ""), ("sbossv", "boss_undead_king")]:
        await h.panel(1, screen_name, arg)
        for line in h.session.last_text().splitlines():
            assert len(re.findall(EMOJI, line)) <= 1, (screen_name, line)
    await h.panel(1, "arenago", "normal")
    assert "نوبت شماست" in h.session.last_text() and {"⚔️ حمله", "🛡️ دفاع", "🏳️ فرار"} <= set(h.labels())
    await h.panel(1, "trip")
    assert "ادامه‌ی نبرد" in " ".join(h.labels())
    await rig(db, p.id)
    for _ in range(30):
        await h.panel(1, "sact", "attack")
        if "پیروزی" in h.session.last_text() or "شکست" in h.session.last_text():
            break
    assert "پیروزی!" in h.session.last_text() and "پاداش" in h.session.last_text()
    assert any("میدان" in x for x in h.labels())  # the arena opens once a day, so no "again" here
    await h.panel(1, "stagego", "1", "fight")
    assert "داستان" in h.session.last_text()
    await h.panel(1, "sfleeq")
    assert "فرار" in h.session.last_text()
    await h.panel(1, "sfleeok")
    assert "گریختید" in h.session.last_text()
    await h.panel(1, "wander")
    assert "چه می‌کنید" in h.session.last_text()
    h.session.reset()
    await h.panel(1, "trip", group=True)  # it is a private-chat section
    assert not h.session.sent("editMessageText")


async def test_the_clan_word_works_in_a_group_again(h, services, db):
    await hero(services, db)
    await h.say(1, "خاندان", group=True)
    assert "خاندان" in h.session.last_text()


async def test_stage_grades_follow_the_health_kept_and_better_grades_pay_crystals(services, db):
    p = await hero(services, db, level=3)
    await services.solo.start_stage(p, 1, "fight")
    async with db.transaction() as tx:  # win with a sliver of health: bronze
        row = await tx.fetchone("SELECT id, state FROM solo_fights WHERE player_id = ? AND status = 'active'", (p.id,))
        state = json.loads(row["state"])
        state["fighters"][1]["hp"] = 1
        state["fighters"][0]["hp"] = 2
        state["fighters"][0]["max_hp"] = 100
        await tx.execute("UPDATE solo_fights SET state = ? WHERE id = ?", (json.dumps(state), row["id"]))
    for _ in range(40):
        update = await services.solo.act(p, Action.ATTACK)
        if update.finished:
            break
    if update.won:
        assert update.payout.grade == 1
        assert (await services.solo.overview(p.id))["grade:1"] == 1
    crystals = (await services.players.require(1)).crystal
    await services.solo.start_stage(p, 1, "fight")
    gold = await finish(services, db, p)  # full health: gold, and the two grades of difference are paid in crystals
    assert gold.won and gold.payout.grade == 3 and (await services.solo.overview(p.id))["grade:1"] == 3
    assert (await services.players.require(1)).crystal >= crystals + 1
    assert any("طلایی" in n for n in gold.payout.notes)


async def test_the_advisor_reads_the_real_situation(services, db, clock):
    p = await hero(services, db, level=3)
    tips = await services.advisor.for_player(p, 10)
    kinds = [t.screen for t in tips]
    assert "wheel" in kinds and "stage" in kinds  # the free spin and the next story stage
    assert tips[0].screen == "wheel" or tips[0].screen == "ach" or tips[0].screen == "missions"
    await services.solo.start_arena(p, "normal")
    assert (await services.advisor.for_player(p, 10))[0].screen == "sfight"  # a fight in progress comes first
    for _ in range(3):  # three defeats in a row: an easier road is offered
        await services.solo.act(p, Action.SURRENDER)
        await services.solo.start_arena(p, "normal")
    await services.solo.act(p, Action.SURRENDER)
    assert any(t.screen == "arenago" and t.arg == "easy" for t in await services.advisor.for_player(p, 10))
    clock.advance(5 * 86400)
    await services.players.claim_daily(p.id)
    clock.advance(5 * 86400)
    assert any(t.screen == "daily" for t in await services.advisor.for_player(await services.players.require(1), 10))
    big = await hero(services, db, uid=2, level=30)
    assert any(t.screen == "sbossv" for t in await services.advisor.for_player(big, 10))


async def maze_win(services, db, player):
    await rig(db, player.id)
    for _ in range(40):
        update = await services.solo.act(player, Action.ATTACK)
        if update.finished:
            return update
    raise AssertionError("maze fight did not end")


async def put_on_floor(db, player, floor, kind, ref, hp=1.0):
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE maze_runs SET floor = ?, hp = ?, options = ? WHERE player_id = ?",
            (floor, hp, json.dumps({"kind": kind, "ref": ref, "seen": []}), player.id),
        )


async def giant_step(services, db, player, floor=3):
    from eternal_realm.game.data import maze as md

    await put_on_floor(db, player, floor, "giant", md.BOSS_FLOORS.get(floor) or md.pool_for(floor)[0])
    step = await services.solo.maze_pick(player, 0)
    assert step.fight is not None and step.fight.info["path"] == md.giant_tier(floor)
    return step


def test_the_maze_has_a_giant_every_second_or_third_floor_and_scenes_are_well_formed():
    from eternal_realm.game.data import maze as md
    from eternal_realm.game.data.items import ITEMS

    giants = [f for f in range(1, md.FLOORS + 1) if md.giant_tier(f)]
    assert giants[0] == 3 and giants[-1] == md.FLOORS
    assert {b - a for a, b in zip(giants, giants[1:])} == {2, 3}
    assert all(md.giant_tier(f) == "great" for f in md.BOSS_FLOORS) and md.giant_tier(5) == "elite" and md.giant_tier(3) == "giant"
    assert md.next_giant(1) == 3 and md.next_giant(4) == 5
    # a weak hero meets the maze's own strength, a strong one meets foes near their level
    assert md.foe_level(3, 1) == 3 and md.foe_level(30, 10) == 57 and md.foe_level(3, 100) == 90
    assert md.TIERS["giant"][1] < md.TIERS["elite"][1] < md.TIERS["great"][1]
    assert len(md.SCENE_IDS) >= 20 and md.CAMPFIRE.id not in md.SCENE_IDS
    labels = set()
    for scene in md.SCENES.values():
        assert len(scene.text.splitlines()) == 2 and 2 <= len(scene.choices) <= 3, scene.id
        for choice in scene.choices:
            labels.add(choice.label)
            assert sum(o.weight for o in choice.outcomes) == 100, (scene.id, choice.label)
            for o in choice.outcomes:
                assert o.text and set(o.fx) <= {"gold", "xp", "heal", "hurt", "bless", "curse", "item", "lose", "fight"}
                assert "item" not in o.fx or o.fx["item"][0] in ITEMS
                assert o.fx.get("bless", "any") in ("any", *md.BLESSINGS)
    assert len(labels) > 50  # the buttons really differ from floor to floor


async def test_the_maze_run_scenes_choices_and_what_each_does(services, db):
    from eternal_realm.game.data import maze as md

    p = await hero(services, db, level=12)
    energy = (await services.players.require(1)).energy
    run = await services.solo.maze_start(p)
    assert (await services.players.require(1)).energy <= energy - md.ENERGY + 1
    assert run.floor == 1 and run.kind == "scene" and run.ref in md.SCENE_IDS and run.hp == 1.0 and run.seen == [run.ref]
    with pytest.raises(GameError, match="نیمه‌کاره"):
        await services.solo.maze_start(p)
    with pytest.raises(GameError, match="راه"):
        await services.solo.maze_pick(p, 7)
    marks = set()
    for scene in md.SCENES.values():  # every choice of every scene keeps the run alive and moves it on
        for index in range(len(scene.choices)):
            for _ in range(3):
                await put_on_floor(db, p, 2, "scene", scene.id, hp=0.6)
                step = await services.solo.maze_pick(p, index)
                assert step.lines
                marks |= {line[0] for line in step.lines[1:]}
                if step.fight is not None:
                    assert step.fight.info["path"] == "ambush"
                    assert (await maze_win(services, db, p)).won
                run = await services.solo.maze_run(p.id)
                assert run.floor == 3 and run.kind == "giant" and 0.05 <= run.hp <= 1.0
    assert {"🪙", "⭐", "💔", "💚", "✨", "🕸"} <= marks
    # the floor before a great guardian is a campfire, and resting there heals half
    run.hp = 0.3
    services.solo._enter(run, 9)
    assert (run.kind, run.ref) == ("scene", md.CAMPFIRE.id)
    await put_on_floor(db, p, 9, "scene", md.CAMPFIRE.id, hp=0.3)
    step = await services.solo.maze_pick(p, 0)
    assert step.run.hp == pytest.approx(0.8) and step.run.floor == 10 and step.run.ref == md.BOSS_FLOORS[10]
    # a run saved in the old format still opens
    async with db.transaction() as tx:
        await tx.execute("UPDATE maze_runs SET floor = 4, options = ? WHERE player_id = ?", (json.dumps(["war", "gold", "magic"]), p.id))
    old = await services.solo.maze_run(p.id)
    assert old.kind == "scene" and old.ref in md.SCENE_IDS
    await services.solo.maze_retreat(p)


async def test_a_maze_win_moves_down_keeps_health_and_pays_only_on_exit_or_milestones(services, db):
    from eternal_realm.game.data import maze as md

    p = await hero(services, db, level=12)
    await services.solo.maze_start(p)
    gold = (await services.players.require(1)).gold
    await giant_step(services, db, p)
    update = await maze_win(services, db, p)
    assert update.won and update.payout.gold == 0  # nothing is paid until the run ends
    run = await services.solo.maze_run(p.id)
    assert run.floor == 4 and run.kind == "scene" and run.gold > 0 and run.xp > 0 and 0.05 <= run.hp <= 1.0
    assert (await services.solo.overview(p.id))["maze:best"] == 3
    assert (await services.players.require(1)).gold == gold
    pool = run.gold
    paid = await services.solo.maze_retreat(p)
    assert paid.gold >= pool and (await services.players.require(1)).gold >= gold + pool
    assert await services.solo.maze_run(p.id) is None
    with pytest.raises(GameError, match="جریان"):
        await services.solo.maze_retreat(p)
    # the first win over the guardian of floor 10 pays crystals and a chest for good, a second one does not
    crystals = (await services.players.require(1)).crystal
    for round_ in (1, 2):
        await services.solo.maze_start(p)
        await giant_step(services, db, p, 10)
        update = await maze_win(services, db, p)
        chest = md.MILESTONES[10][1]
        if round_ == 1:
            assert update.payout.crystal == md.MILESTONES[10][0] and update.payout.items.get(chest) == 1
            assert any("جایزه‌ی ماندگار" in n for n in update.payout.notes)
        else:
            assert update.payout.crystal == 0 and chest not in update.payout.items
        await services.solo.maze_retreat(p)
    assert (await services.players.require(1)).crystal >= crystals + md.MILESTONES[10][0]
    assert (await services.solo.overview(p.id))["maze:best"] == 10


async def test_slipping_past_a_giant_works_only_for_ordinary_ones(services, db):
    from eternal_realm.game.data import maze as md

    p = await hero(services, db, level=12)
    await services.solo.maze_start(p)
    seen = set()
    for _ in range(30):
        await put_on_floor(db, p, 3, "giant", md.pool_for(3)[0])
        before = (await services.solo.maze_run(p.id)).gold
        step = await services.solo.maze_pick(p, 1)
        if step.fight is None:
            assert step.run.floor == 4 and step.run.gold == before
            seen.add("past")
        else:
            assert step.run.floor == 3 and step.run.hp == pytest.approx(1.0 - md.SNEAK_HURT)
            assert (await maze_win(services, db, p)).won
            seen.add("caught")
    assert seen == {"past", "caught"}
    await put_on_floor(db, p, 5, "giant", md.pool_for(5)[0])
    with pytest.raises(GameError, match="راه"):
        await services.solo.maze_pick(p, 1)
    await services.solo.maze_retreat(p)


async def test_a_maze_defeat_ends_the_run_and_pays_half(services, db):
    p = await hero(services, db, level=12)
    await services.solo.maze_start(p)
    async with db.transaction() as tx:
        await tx.execute("UPDATE maze_runs SET gold = 1000, xp = 400 WHERE player_id = ?", (p.id,))
    await giant_step(services, db, p)
    gold = (await services.players.require(1)).gold
    update = await services.solo.act(p, Action.SURRENDER)
    assert update.fled and update.payout.gold >= 500 and update.payout.gold <= 700
    assert (await services.players.require(1)).gold == gold + update.payout.gold
    assert await services.solo.maze_run(p.id) is None
    assert any("بلعید" in n for n in update.payout.notes)


async def test_a_deep_giant_beats_a_weak_hero_and_says_to_come_back_stronger(services, db):
    p = await hero(services, db, level=2)
    await services.solo.maze_start(p)
    step = await giant_step(services, db, p, 25)
    assert step.fight.info["level"] == 47
    for _ in range(40):
        update = await services.solo.act(p, Action.ATTACK)
        if update.finished:
            break
    assert update.finished and not update.won
    assert any("سطح ۴۷" in n and "برگردید" in n for n in update.payout.notes)
    assert await services.solo.maze_run(p.id) is None


async def test_the_maze_screens(h, services, db):
    from eternal_realm.game.data import maze as md

    p = await hero(services, db, level=12)
    await h.panel(1, "maze")
    assert "هزارتوی ابدی" in h.session.last_text() and "ورود به هزارتو" in " ".join(h.labels())
    await h.panel(1, "mazego")
    scene = md.SCENES[(await services.solo.maze_run(p.id)).ref]
    text = h.session.last_text()
    assert f"طبقه‌ی ۱ از {fa(md.chapter_end(1))}" in text and scene.title in text and scene.text in text and "غول بعدی در طبقه‌ی ۳" in text
    assert {choice.label for choice in scene.choices} <= set(h.labels())
    for line in text.splitlines():
        assert len(re.findall(EMOJI, line)) <= 1, line
    await put_on_floor(db, p, 1, "scene", "forge")
    await h.panel(1, "mazepick", "2")  # rummaging the forge never starts a fight
    assert "در راه چه گذشت" in h.session.last_text() and f"طبقه‌ی ۲ از {fa(md.chapter_end(1))}" in h.session.last_text()
    for line in h.session.last_text().splitlines():
        assert len(re.findall(EMOJI, line)) <= 1, line
    await put_on_floor(db, p, 3, "giant", md.pool_for(3)[0])
    await h.panel(1, "maze")
    text = h.session.last_text()
    assert "غول طبقه" in text and "هم‌تراز سطح" in text
    assert any("می‌جنگم" in x for x in h.labels()) and any("دزدکی" in x for x in h.labels())
    for line in text.splitlines():
        assert len(re.findall(EMOJI, line)) <= 1, line
    await h.panel(1, "mazepick", "0")  # facing the giant starts a real fight
    assert "نوبت شماست" in h.session.last_text()
    await rig(db, p.id)
    for _ in range(30):
        await h.panel(1, "sact", "attack")
        if "پیروزی!" in h.session.last_text():
            break
    assert any("ادامه‌ی هزارتو" in x for x in h.labels())
    await h.panel(1, "maze")
    assert "غنیمت تا اینجا" in h.session.last_text() and f"طبقه‌ی ۴ از {fa(md.chapter_end(1))}" in h.session.last_text()
    await put_on_floor(db, p, 5, "giant", md.pool_for(5)[0])
    await h.panel(1, "maze")
    assert "غول سرسخت" in h.session.last_text() and not any("دزدکی" in x for x in h.labels())
    await h.panel(1, "mazeoutq")
    assert "بیرون آمدن" in h.session.last_text()
    await h.panel(1, "mazeout")
    assert "غنیمت" in h.session.last_text() and await services.solo.maze_run(p.id) is None


async def test_expeditions_take_time_pay_modestly_and_are_limited(services, db, clock):
    from eternal_realm.game.data import expedition as ed

    p = await hero(services, db)
    with pytest.raises(GameError, match="چنین"):
        await services.expeditions.start(p, "nowhere", 4)
    with pytest.raises(GameError, match="مدت"):
        await services.expeditions.start(p, "mine", 3)
    trip = await services.expeditions.start(p, "mine", 4)
    assert trip.ends_at == services.ctx.now() + 4 * 3600
    with pytest.raises(GameError, match="هم‌اکنون"):
        await services.expeditions.start(p, "herb", 1)
    with pytest.raises(GameError, match="برنگشته"):
        await services.expeditions.claim(p)
    clock.advance(4 * 3600 + 1)
    report = await services.expeditions.claim(p)
    clock.advance(86400)  # one expedition a day
    assert report.hours == 4 and report.lines and report.items.get("iron_ore", 0) >= 6
    async with db.read() as tx:
        assert await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = 'iron_ore'", (p.id,), 0) >= 6
    with pytest.raises(GameError, match="در اعزام نیست"):
        await services.expeditions.claim(p)
    await services.expeditions.start(p, "train", 8)
    clock.advance(8 * 3600)
    trained = await services.expeditions.claim(p)
    assert trained.xp > 0 and trained.gold == 0
    with pytest.raises(GameError, match=f"{ed.DAILY_LIMIT}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))):
        await services.expeditions.start(p, "treasure", 1)  # one a day is the limit
    clock.advance(86400)
    await services.expeditions.start(p, "treasure", 1)


async def test_a_hero_back_from_an_expedition_is_told_and_reads_the_report(h, services, db, clock):
    from eternal_realm.bot import notifier

    p = await hero(services, db)
    await h.panel(1, "expd")
    assert "اعزام قهرمان" in h.session.last_text() and len([x for x in h.labels() if "·" in x]) == 5
    await h.panel(1, "expdk", "guard")
    assert {"⏳ ۱ ساعت", "⏳ ۴ ساعت", "⏳ ۸ ساعت"} <= set(h.labels())
    await h.panel(1, "expdgo", "guard", "1")
    await h.panel(1, "expd")
    assert "تا بازگشت" in h.session.last_text()
    h.session.reset()
    await notifier.deliver(h.bot, services)
    assert not [m for n, m in h.session.calls if n == "sendMessage"]
    clock.advance(3700)
    await notifier.deliver(h.bot, services)
    told = [m for n, m in h.session.calls if n == "sendMessage" and m.get("chat_id") == 1]
    assert told and "از اعزام برگشت" in told[-1]["text"]
    await notifier.deliver(h.bot, services)
    assert len([m for n, m in h.session.calls if n == "sendMessage" and m.get("chat_id") == 1]) == len(told)
    await h.panel(1, "expd")
    assert "گرفتن گزارش" in " ".join(h.labels())
    await h.panel(1, "expdclaim")
    assert "گزارش اعزام شما" in h.session.last_text() and "در مدت غیبت شما" in h.session.last_text()
    for line in h.session.last_text().splitlines():
        assert len(re.findall(EMOJI, line)) <= 1, line
    assert await services.expeditions.current(p.id) is None


# --- the living world ---------------------------------------------------------------------------------------------------
async def darkness_of(db, region):
    async with db.read() as tx:
        return await tx.scalar("SELECT darkness FROM world_regions WHERE id = ?", (region,), -1)


async def test_regions_grow_dark_by_themselves_and_wins_push_the_darkness_back(services, db, clock):
    from eternal_realm.game.data import world as wd

    regions = await services.world.regions()
    assert {r.region.id for r in regions} == {r.id for r in wd.REGIONS} and all(r.darkness == wd.START_DARKNESS for r in regions)
    clock.advance(10 * 3600)
    grown = {r.region.id: r.darkness for r in await services.world.regions()}
    assert all(v == pytest.approx(wd.START_DARKNESS + 8) for v in grown.values())
    clock.advance(500 * 3600)
    assert all(r.darkness == 100 for r in await services.world.regions())  # it never passes the top
    assert wd.status_of(10) == "عادی" and wd.status_of(40) == "جنگی" and wd.status_of(70) == "نفرین‌شده" and wd.status_of(95) == "متروکه"
    assert wd.effect_of(0) == (1.0, 1.0) and wd.effect_of(100) == (1.15, 1.3)
    p = await hero(services, db, level=10)
    base = None
    for dark in (0, 100):
        async with db.transaction() as tx:
            await tx.execute("UPDATE world_regions SET darkness = ?, calc = ? WHERE id = ?", (dark, services.ctx.now(), wd.ARENA_REGION))
        fight = await services.solo.start_arena(p, "normal", "bot_swordsman")
        await services.solo.abandon(p)
        if base is None:
            base = fight
    assert fight.info["gold"] > base.info["gold"] and fight.battle.fighters[1].max_hp > base.battle.fighters[1].max_hp
    async with db.transaction() as tx:
        await tx.execute("UPDATE world_regions SET darkness = 50, calc = ? WHERE id = ?", (services.ctx.now(), wd.ARENA_REGION))
    await services.solo.start_arena(p, "easy")
    await finish(services, db, p)
    assert await darkness_of(db, wd.ARENA_REGION) == pytest.approx(49, abs=0.1)


async def test_a_world_event_is_opened_fought_over_and_paid_to_everyone_who_took_part(services, db, clock):
    from eternal_realm.bot import notifier
    from eternal_realm.game.data import world as wd

    a = await hero(services, db, 1, level=10)
    b = await hero(services, db, 2, level=10)
    assert await services.world.active() is not None and await services.world.active() is not None  # opened once
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM world_events", (), 0) == 1
    event = await services.world.active(a.id)
    fight = await services.solo.start_world_fight(a)
    assert fight.kind == "world" and fight.info["event"] == event.id
    await rig(db, a.id, foe_hp=1)
    first = await finish(services, db, a, win=False)
    assert first.won and any("سهم شما" in n for n in first.payout.notes)
    mine = (await services.world.active(a.id)).mine
    assert mine >= 5
    await services.solo.start_world_fight(b)
    fled = await services.solo.act(b, Action.SURRENDER)
    assert fled.fled and any("فرار" in n for n in fled.payout.notes)
    assert (await services.world.active(b.id)).mine == 0
    # make the event nearly full: the next fight completes it and pays at once
    async with db.transaction() as tx:
        await tx.execute("UPDATE world_events SET max_points = points + 10 WHERE id = ?", (event.id,))
    gold_a, crystal_a = (await services.players.require(1)).gold, (await services.players.require(1)).crystal
    await services.solo.start_world_fight(b)
    done = await finish(services, db, b)
    assert any("پایان رسید" in n for n in done.payout.notes)
    assert (await services.players.require(1)).crystal > crystal_a and (await services.players.require(1)).gold > gold_a
    async with db.read() as tx:
        assert await tx.scalar("SELECT status FROM world_events WHERE id = ?", (event.id,), "") == "won"
        assert await tx.scalar("SELECT qty FROM inventory WHERE player_id = 1 AND item_id = 'magic_chest'", (), 0) >= 1 or \
            await tx.scalar("SELECT qty FROM inventory WHERE player_id = 2 AND item_id = 'magic_chest'", (), 0) >= 1
    h_bot = Harness(services).bot
    sent = await notifier.deliver(h_bot, services)
    assert sent >= 2
    # nothing opens until the gap has passed, and the next event is a different one
    assert await services.world.active() is None
    clock.advance(wd.GAP_HOURS * 3600 + 5)
    nxt = await services.world.active()
    assert nxt is not None and nxt.kind.id != event.kind.id


async def test_an_event_nobody_finished_fails_pays_a_little_and_darkens_the_region(services, db, clock):
    from eternal_realm.game.data import world as wd

    p = await hero(services, db, level=10)
    event = await services.world.active(p.id)
    await services.solo.start_world_fight(p)
    await rig(db, p.id, foe_hp=40)  # a little damage only
    await finish(services, db, p, win=False)
    before = await darkness_of(db, event.kind.region)
    gold = (await services.players.require(1)).gold
    clock.advance(wd.EVENT_HOURS * 3600 + 10)
    await services.world.tick()
    async with db.read() as tx:
        assert await tx.scalar("SELECT status FROM world_events WHERE id = ?", (event.id,), "") == "lost"
    assert (await services.players.require(1)).gold > gold
    assert await darkness_of(db, event.kind.region) > before
    last = await services.world.last_result()
    assert last is not None and last.status == "lost"


async def test_the_world_screen(h, services, db):
    p = await hero(services, db, level=10)
    await h.panel(1, "trip")
    assert any("جهان زنده" in x for x in h.labels())
    await h.panel(1, "world")
    text = h.session.last_text()
    assert "خبر فوری قلمرو" in text and "سهم شما" in text and "جنگل سیاه" in text and "زمان باقی‌مانده" in text
    for line in text.splitlines():
        assert len(re.findall(EMOJI, line)) <= 1, line
    await h.panel(1, "worldgo")
    assert "نوبت شماست" in h.session.last_text()
    await rig(db, p.id)
    for _ in range(30):
        await h.panel(1, "sact", "attack")
        if "پیروزی!" in h.session.last_text():
            break
    assert any("جهان" in x for x in h.labels()) and "سهم شما در رویداد جهانی" in h.session.last_text()


async def test_the_hub_has_no_suggestion_buttons_and_every_section_explains_itself(h, services, db):
    await hero(services, db)
    await h.panel(1, "trip")
    text = h.session.last_text()
    for part in ("داستان:", "دخمه‌ها:", "باس‌ها:", "میدان بات‌ها:", "هزارتو:", "گشت‌زنی:", "اعزام:", "جهان زنده:"):
        assert part in text, part
    assert "پیشنهاد فرمانده" not in text
    assert not any(b["text"].startswith(("🏅", "🎡", "📅", "🧰", "🏗️")) for b in h.session.last_buttons())
    await h.panel(1, "wanderq")
    assert "کمک یا غارت" in h.session.last_text() and "هزینه" in h.session.last_text()
    assert await services_event(services, 1) is None  # reading about it costs nothing
    await h.panel(1, "arena")
    assert "تازه‌کار:" in h.session.last_text() and "افسانه‌ای:" in h.session.last_text()
    await h.panel(1, "dng")
    assert "رکورد شما" in h.session.last_text() and "—" in h.session.last_text()
    await h.panel(1, "sbosses")
    assert "ضربه‌ی ویژه" in h.session.last_text()
    await h.panel(1, "expdk", "mine")
    assert "چه چیزی برمی‌گرداند" in h.session.last_text() and "سنگ آهن" in h.session.last_text()
    for screen_name, arg in [("trip", ""), ("wanderq", ""), ("arena", ""), ("dng", ""), ("sbosses", ""), ("expdk", "mine"), ("story", "")]:
        await h.panel(1, screen_name, arg)
        for line in h.session.last_text().splitlines():
            assert len(re.findall(EMOJI, line)) <= 1, (screen_name, line)


async def services_event(services, pid):
    return await services.solo.pending_event(pid)


async def test_tips_come_as_one_message_a_day_and_never_at_night(h, services, db, clock):
    from eternal_realm.bot import notifier

    await hero(services, db, level=3)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy_at = ? WHERE id = 1", (services.ctx.now(),))
    hour = ((services.ctx.now() + 12600) % 86400) // 3600
    h_bot = Harness(services).bot
    if hour >= 23 or hour < 8:  # the night is silent: nothing is queued, and in the morning the tip comes
        await notifier.deliver(h_bot, services)
        async with db.read() as tx:
            assert await tx.scalar("SELECT COUNT(*) FROM player_alerts WHERE key LIKE 'tip:%'", (), 0) == 0
        clock.advance(((8 - hour) % 24) * 3600 + 700)
    sent_before = await notifier.deliver(h_bot, services)
    async with db.read() as tx:
        n = await tx.scalar("SELECT COUNT(*) FROM player_alerts WHERE key LIKE 'tip:%'", (), 0)
    assert n == 1 and sent_before >= 1
    clock.advance(700)
    await notifier.deliver(h_bot, services)  # the same day: no second tip
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM player_alerts WHERE key LIKE 'tip:%'", (), 0) == 1
        text = await tx.scalar("SELECT text FROM player_alerts WHERE key LIKE 'tip:%'", (), "")
    assert "پیشنهاد فرمانده" in text
    clock.advance(86400)
    await notifier.deliver(h_bot, services)
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM player_alerts WHERE key LIKE 'tip:%'", (), 0) == 2


async def test_a_hero_away_on_an_expedition_cannot_fight_other_players(h, services, db, clock):
    a = await hero(services, db, 1, name="دورافتاده")
    b = await hero(services, db, 2, name="رقیب‌جان")
    await services.expeditions.start(a, "mine", 4)
    with pytest.raises(GameError, match="اعزام"):
        await services.duels.challenge(-500, a, b)
    with pytest.raises(GameError, match="اعزام"):
        await services.duels.challenge(-500, b, a)
    with pytest.raises(GameError, match="اعزام"):
        await services.bets.create(a, -500, "gold", "", 100)
    with pytest.raises(GameError, match="اعزام"):
        await services.teams.create(-500, a)
    lobby = await services.teams.create(-500, b)
    with pytest.raises(GameError, match="اعزام"):
        await services.teams.sit(lobby.id, a, 1, 0)
    await h.say(1, "مبارزه", group=True, reply_to=h.message_of(2))
    assert "اعزام" in h.session.last_text()
    clock.advance(4 * 3600 + 1)  # back home: reading the report is not required to fight
    duel = await services.duels.challenge(-500, a, b)
    assert duel.id
    await services.expeditions.claim(a)  # and a hero with an open duel cannot leave again
    with pytest.raises(GameError, match="مبارزه"):
        await services.expeditions.start(a, "mine", 1)


def test_the_away_refusal_tells_the_exact_time_left():
    from eternal_realm.db.repos.players import away_text

    text = away_text(2 * 3600 + 5 * 60 + 9)
    assert "۲ ساعت و ۵ دقیقه و ۹ ثانیه" in text
    assert "۴۵ ثانیه" in away_text(45, "آرش")


async def test_a_hero_can_be_called_back_for_crystals(h, services, db, clock):
    p = await hero(services, db)
    await services.expeditions.start(p, "mine", 4)
    with pytest.raises(GameError):  # no crystals yet
        await services.expeditions.recall(p)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET crystal = 10 WHERE id = ?", (p.id,))
    await h.panel(1, "expd")
    assert any("برگرداندن قهرمان" in x for x in h.labels())
    await h.panel(1, "awayq")
    assert "۴ کریستال" in h.session.last_text()
    await h.panel(1, "awayok")
    assert "احضار شد" in h.session.last_text()
    assert (await services.players.require(1)).crystal == 6
    report = await services.expeditions.claim(await services.players.require(1))
    assert report.hours == 4


async def test_the_away_notice_in_a_group_carries_the_recall_button(h, services, db, clock):
    a = await hero(services, db, 1, name="دورافتاده")
    await hero(services, db, 2, name="رقیب‌جان")
    await services.expeditions.start(a, "mine", 4)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET crystal = 10 WHERE id = ?", (a.id,))
    await h.say(1, "مبارزه", group=True, reply_to=h.message_of(2))
    assert "احضار سریع (۴ کریستال)" in " ".join(h.labels())
    clock.advance(3 * 3600)
    await h.say(1, "مبارزه", group=True, reply_to=h.message_of(2))
    assert "احضار سریع (۱ کریستال)" in " ".join(h.labels())


async def test_a_double_tap_on_the_last_blow_never_freezes_the_fight_screen(h, services, db):
    p = await hero(services, db)
    day = (services.ctx.now() + 12600) // 86400
    dungeon = data.todays_dungeons(day)[0]
    await services.solo.start_dungeon(p, dungeon.id)
    for _ in range(data.FLOORS - 1):
        assert (await finish(services, db, p)).won
        await services.solo.next_floor(p)
    await rig(db, p.id)  # the last floor
    await h.panel(1, "sact", "attack")
    assert "پیروزی" in h.session.last_text() and "پاداش" in h.session.last_text()
    result = h.session.last_text()
    h.session.reset()
    await h.panel(1, "sact", "attack")  # a second tap that arrives after the fight is over
    assert not [a for a in h.session.callback_answers() if a.get("show_alert")]
    shown = [m["text"] for n, m in h.session.calls if n in ("editMessageText", "sendMessage")]
    assert all("پیروزی" in t for t in shown)  # either untouched or a recovered result, never an error or a dead screen
    assert result
    async with db.read() as tx:
        assert await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = 'wooden_chest'", (p.id,), 0) >= 1
