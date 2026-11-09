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
from eternal_realm.shared.text import EMOJI

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
    assert boss.payout.crystal == data.CHAPTER_DONE_CRYSTALS and any("فصل" in n for n in boss.payout.notes)
    assert (await services.players.require(1)).crystal == crystals + data.CHAPTER_DONE_CRYSTALS
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
    assert any("دوباره" in x for x in h.labels())
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
