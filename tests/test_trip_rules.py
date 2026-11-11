"""The trip's daily limit, the longer maze, the dead-button rescue and the new group games."""

import json

import pytest

from eternal_realm.bot import events as events_ui
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import group_games
from eternal_realm.game.data import maze as md
from eternal_realm.game.data import solo as data
from eternal_realm.game.data.items import ITEMS
from eternal_realm.shared.errors import GameError

from .harness import Harness

CHAT = -500


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid=1, level=10, gold=3_000):
    p = await services.players.register(uid, f"u{uid}", f"قهرمان{uid}", "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, energy = 500 WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def drop_fight(services, p):
    await services.solo.abandon(p)


# --- one use of every section a day -----------------------------------------------------------------------------------
async def test_every_section_of_the_trip_opens_once_a_day(services, db, clock, monkeypatch):
    monkeypatch.setattr(data, "DAILY_USES", 1)
    p = await hero(services, db, level=30)

    await services.solo.start_arena(p, "normal")
    await drop_fight(services, p)
    with pytest.raises(GameError, match="امروز از «میدان بات‌ها»"):
        await services.solo.start_arena(p, "normal")

    await services.solo.maze_start(p)
    await services.solo.maze_retreat(p)
    with pytest.raises(GameError, match="امروز از «هزارتوی ابدی»"):
        await services.solo.maze_start(p)

    await services.solo.wander(p)
    with pytest.raises(GameError):  # the pending event, then (once decided) the daily limit
        await services.solo.wander(p)

    await services.solo.start_boss(p, "boss_undead_king")
    await drop_fight(services, p)
    with pytest.raises(GameError, match="امروز از «باس‌های تک‌نفره»"):
        await services.solo.start_boss(p, "boss_undead_king")

    dungeon = data.todays_dungeons((clock() + 12600) // 86400)[0]
    await services.solo.start_dungeon(p, dungeon.id)
    await drop_fight(services, p)
    with pytest.raises(GameError, match="امروز از «دخمه‌ها»"):
        await services.solo.start_dungeon(p, dungeon.id)

    clock.advance(86400)  # a new day opens them all again
    await services.solo.start_arena(p, "normal")


async def test_a_refused_start_does_not_use_up_the_day(services, db, monkeypatch):
    monkeypatch.setattr(data, "DAILY_USES", 1)
    p = await hero(services, db, level=5)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 0 WHERE id = ?", (p.id,))
    with pytest.raises(GameError):
        await services.solo.maze_start(p)  # no energy
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 100 WHERE id = ?", (p.id,))
    await services.solo.maze_start(p)


async def test_the_owner_is_not_limited(services, db, monkeypatch):
    monkeypatch.setattr(data, "DAILY_USES", 1)
    p = await hero(services, db, uid=999, level=10)
    for _ in range(2):
        await services.solo.maze_start(p)
        await services.solo.maze_retreat(p)


async def test_trip_pays_less_than_it_used_to(services, db):
    assert data.REWARD_SHARE < 0.6
    p = await hero(services, db, level=10)
    gold, xp = services.solo._scale(p.level, 100, 100)
    assert gold < 100 and xp < 100 or p.level < 5


# --- the longer maze ----------------------------------------------------------------------------------------------------
def test_the_maze_has_sixty_floors_six_guardians_and_pools_for_every_depth():
    assert md.FLOORS == 60 and sorted(md.BOSS_FLOORS) == [10, 20, 30, 40, 50, 60]
    assert set(md.MILESTONES) == set(md.BOSS_FLOORS)
    for floor in range(1, md.FLOORS + 1):
        assert md.pool_for(floor)
        tier = md.giant_tier(floor)
        assert (tier == "great") == (floor in md.BOSS_FLOORS)
        assert md.depth_level(floor) >= md.depth_level(floor - 1) if floor > 1 else True
    for foe in (*md.BOSS_FLOORS.values(), *(f for _, pool in md.POOLS for f in pool)):
        assert foe in data.FOES, foe
    giants = [f for f in range(1, md.FLOORS + 1) if md.giant_tier(f)]
    assert {b - a for a, b in zip(giants, giants[1:])} == {2, 3}
    assert len(md.SCENE_IDS) >= 40
    for scene in md.SCENES.values():
        for choice in scene.choices:
            for outcome in choice.outcomes:
                assert "item" not in outcome.fx or outcome.fx["item"][0] in ITEMS


async def test_a_run_can_go_down_past_floor_thirty(services, db):
    p = await hero(services, db, level=80)
    await services.solo.maze_start(p)
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE maze_runs SET floor = 39, options = ? WHERE player_id = ?",
            (json.dumps({"kind": "scene", "ref": "campfire", "seen": []}), p.id),
        )
    step = await services.solo.maze_pick(p, 0)
    assert step.run.floor == 40 and step.run.kind == "giant" and step.run.ref == "ice_king"
    step = await services.solo.maze_pick(p, 0)
    assert step.fight is not None and step.fight.info["path"] == "great"


# --- no dead end in the maze ----------------------------------------------------------------------------------------------
async def test_the_maze_screen_always_offers_the_fight_that_is_still_going(h, services, db):
    p = await hero(services, db, level=12)
    await h.panel(1, "mazego")
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE maze_runs SET floor = 3, options = ? WHERE player_id = ?",
            (json.dumps({"kind": "giant", "ref": md.pool_for(3)[0], "seen": []}), p.id),
        )
    await h.panel(1, "mazepick", "0")  # the giant's fight begins
    assert any("حمله" in x for x in h.labels())
    await h.panel(1, "maze")  # the player comes back to the maze instead of the fight
    assert any("ادامه‌ی نبرد" in x for x in h.labels())
    await h.panel(1, "trip")
    assert any("ادامه‌ی نبرد" in x for x in h.labels())


async def test_the_hub_offers_a_maze_run_in_progress(h, services, db):
    await hero(services, db, level=12)
    await h.panel(1, "mazego")
    await h.panel(1, "trip")
    assert any("ادامه‌ی هزارتو" in x for x in h.labels())


async def test_a_screen_that_fails_after_the_progress_frame_gives_the_buttons_back(h, services, db, monkeypatch):
    from eternal_realm.bot import panel

    await hero(services, db, level=12)
    await h.panel(1, "mazego")
    real = panel.SCREENS["maze"]

    async def broken(c):
        raise RuntimeError("boom")

    monkeypatch.setitem(panel.SCREENS, "maze", broken)
    h.session.reset()
    await h.panel(1, "mazepick", "0")  # the middleware logs the failure; the player must still get a way on
    assert h.session.last_buttons(), "the message must not be left without buttons"
    assert any("ادامه" in x for x in h.labels())
    monkeypatch.setitem(panel.SCREENS, "maze", real)


# --- the new group games ---------------------------------------------------------------------------------------------------
async def test_riddle_pays_the_first_right_answer_only(services, db, clock):
    a, b = await hero(services, db, 1), await hero(services, db, 2)
    view = await services.events.spawn(CHAT, "riddle")
    assert view is not None and "معمای کاروان" in events_ui.text_for(view)
    order = view.state["order"]
    right, wrong = order.index(0), next(i for i, o in enumerate(order) if o != 0)
    gold = (await services.players.require(1)).gold
    view, ok = await services.events.answer(view.id, a, wrong)
    assert not ok and view.status == "active"
    with pytest.raises(GameError, match="دوباره حدس"):
        await services.events.answer(view.id, a, right)
    view, ok = await services.events.answer(view.id, b, right)
    assert ok and view.status == "done" and "معما حل شد" in events_ui.text_for(view)
    assert (await services.players.require(2)).gold > gold - 1
    with pytest.raises(GameError, match="تمام شده"):
        await services.events.answer(view.id, a, right)


async def test_riddle_answers_are_distinct_and_every_riddle_has_one_right_option():
    for question, answer, wrong in group_games.RIDDLES:
        assert len({answer, *wrong}) == 4, question


async def test_tiles_give_each_player_one_prize_and_show_it_to_everyone(services, db):
    a, b = await hero(services, db, 1), await hero(services, db, 2)
    view = await services.events.spawn(CHAT, "tiles")
    assert len(view.state["tiles"]) == group_games.TILE_COUNT
    view, text = await services.events.pick_tile(view.id, a, 0)
    assert text and "قهرمان1" in events_ui.text_for(view) or a.mention in events_ui.text_for(view)
    with pytest.raises(GameError, match="یک کاشی"):
        await services.events.pick_tile(view.id, a, 1)
    with pytest.raises(GameError, match="قبلاً"):
        await services.events.pick_tile(view.id, b, 0)
    view, _ = await services.events.pick_tile(view.id, b, 1)
    assert len(view.state["picked"]) == 2


async def test_raffle_draws_one_winner_when_time_is_up(services, db, clock):
    from eternal_realm.game.services.events import LIFETIME

    players = [await hero(services, db, i, level=10) for i in (1, 2, 3)]
    view = await services.events.spawn(CHAT, "raffle")
    pot = view.state["pot"]
    for p in players:
        view = await services.events.enter_raffle(view.id, p)
    with pytest.raises(GameError, match="هست"):
        await services.events.enter_raffle(view.id, players[0])
    assert view.state["pot"] > pot
    async def total() -> int:
        return sum([(await services.players.require(i)).gold for i in (1, 2, 3)])

    before = await total()
    clock.advance(LIFETIME["raffle"] + 1)
    actions = await services.events.tick()
    ended = next(a for a in actions if a.what == "ended")
    assert ended.view.status == "done" and "قرعه به نام" in events_ui.text_for(ended.view)
    assert await total() == before + ended.view.state["prize"]


async def test_a_raffle_with_one_entry_is_called_off(services, db, clock):
    from eternal_realm.game.services.events import LIFETIME

    p = await hero(services, db, 1)
    view = await services.events.spawn(CHAT, "raffle")
    await services.events.enter_raffle(view.id, p)
    clock.advance(LIFETIME["raffle"] + 1)
    actions = await services.events.tick()
    ended = next(a for a in actions if a.what == "ended")
    assert ended.view.status == "expired" and "برگزار نشد" in events_ui.text_for(ended.view)


async def test_the_new_games_can_be_tapped_in_a_group(h, services, db):
    await hero(services, db, 999)
    await services.groups.touch(CHAT, "گروه")
    for word in ("معما", "کاشی", "قرعه کشی"):
        await h.say(999, f"احضار {word}", group=True, chat=CHAT)
    kinds = sorted(v.kind for v in await services.events.active(CHAT))
    assert kinds == ["raffle", "riddle", "tiles"]
    for view in await services.events.active(CHAT):
        action = {"riddle": "answer", "tiles": "tile", "raffle": "enter"}[view.kind]
        await h.click(999, f"e:{action}:{view.id}:0", group=True)
    answers = [a.get("text", "") for a in h.session.callback_answers()]
    assert any("قرعه" in x for x in answers) and any(x for x in answers)
