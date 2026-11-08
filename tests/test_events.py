import pytest

from eternal_realm.bot import events as events_ui
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.shared.errors import GameError

from .harness import Harness

CHAT = -500


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=5, gold=3_000):
    p = await services.players.register(uid, f"u{uid}", name, "dragonborn", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def active_group(services, db, players):
    await services.groups.touch(CHAT, "گروه")
    async with db.transaction() as tx:
        for p in players:
            await tx.execute(
                "INSERT INTO group_members (chat_id, player_id, points, last_active) VALUES (?, ?, 0, ?)",
                (CHAT, p.id, services.ctx.now()),
            )


async def test_mystery_chest_opens_for_exactly_one_player(services, db, clock):
    a, b = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    view = await services.events.spawn(CHAT, "mystery_chest")
    assert view is not None and view.status == "active"
    won = None
    for _ in range(60):
        clock.advance(25)
        for p in (a, b):
            if won is None:
                try:
                    view, ok = await services.events.try_open(view.id, p)
                except GameError:
                    continue
                if ok:
                    won = p
    assert won is not None
    with pytest.raises(GameError):
        await services.events.try_open(view.id, b)
    stored = await services.events.get(view.id)
    assert stored.status == "done" and stored.state["winner"] == won.name
    assert "گشوده" in events_ui.text_for(stored)


async def test_chest_try_has_a_gap(services, db):
    a = await hero(services, db, 1, "آرش")
    view = await services.events.spawn(CHAT, "mystery_chest")
    await services.events.try_open(view.id, a)
    with pytest.raises(GameError, match="ثانیه"):
        await services.events.try_open(view.id, a)


async def test_one_event_at_a_time_and_expiry(services, db, clock):
    assert await services.events.spawn(CHAT, "merchant") is not None
    assert await services.events.spawn(CHAT, "double_xp") is None
    clock.advance(10_000)
    actions = await services.events.tick()
    assert [a.what for a in actions] == ["ended"]
    assert await services.events.active(CHAT) == []


async def test_merchant_sells_limited_stock_and_charges_gold(services, db):
    a = await hero(services, db, 1, "آرش")
    view = await services.events.spawn(CHAT, "merchant")
    entry = view.state["stock"][0]
    before = (await services.players.require(1)).gold
    view, label = await services.events.buy(view.id, a, 0)
    assert (await services.players.require(1)).gold == before - entry["price"]
    assert view.state["stock"][0]["left"] == entry["left"] - 1 and label
    poor = await hero(services, db, 2, "سارا", gold=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 0 WHERE id = ?", (poor.id,))
    with pytest.raises(GameError):
        await services.events.buy(view.id, poor, 0)
    with pytest.raises(GameError):
        await services.events.buy(view.id, a, 9)


async def test_tick_spawns_in_active_groups_only(services, db, clock):
    ps = [await hero(services, db, i, f"قهرمان{i}") for i in (1, 2, 3)]
    await services.groups.touch(CHAT, "گروه")
    clock.advance(3_000)
    assert await services.events.tick() == []  # nobody active yet: tries again later
    async with db.transaction() as tx:
        await tx.execute("UPDATE groups SET next_event_at = 0")
    await active_group(services, db, ps)
    actions = await services.events.tick()
    assert [a.what for a in actions] == ["spawned"]
    async with db.read() as tx:
        nxt = await tx.scalar("SELECT next_event_at FROM groups WHERE chat_id = ?", (CHAT,), 0)
    assert nxt > services.ctx.now()


async def test_disabled_events_are_not_spawned(services, db, clock):
    ps = [await hero(services, db, i, f"قهرمان{i}") for i in (1, 2, 3)]
    await active_group(services, db, ps)
    await services.groups.set_command(CHAT, "events", False)
    async with db.transaction() as tx:
        await tx.execute("UPDATE groups SET next_event_at = 0")
    assert await services.events.tick() == []


async def _fighters(db, boss_id):
    async with db.read() as tx:
        return await tx.fetchall("SELECT player_id FROM boss_hits WHERE boss_id = ?", (boss_id,))


async def test_hidden_boss_is_free_to_start_and_pays_no_refund(services, db):
    ps = [await hero(services, db, i, f"قهرمان{i}") for i in (1, 2, 3)]
    await active_group(services, db, ps)
    before = [p.gold for p in ps]
    view = await services.events.spawn(CHAT, "hidden_boss")
    assert view is not None and view.boss is not None and view.boss.free
    boss = view.boss
    for p in ps:
        if p.id not in [f["player_id"] for f in await _fighters(db, boss.id)]:
            boss = await services.bosses.join(boss.id, p)
    gold = [(await services.players.require(p.platform_user_id)).gold for p in ps]
    boss = await services.bosses.start(boss.id, ps[1])
    assert boss.phase == "fighting"
    assert gold == [(await services.players.require(p.platform_user_id)).gold for p in ps] == before


async def test_double_xp_doubles_activity_xp_in_that_group(services, db):
    a = await hero(services, db, 1, "آرش", level=3)
    await services.events.spawn(CHAT, "double_xp")
    services.ctx.rng.seed(5)
    normal = await services.activities.perform(a.id, "fishing")
    services.ctx.rng.seed(5)
    async with db.transaction() as tx:
        await tx.execute("DELETE FROM cooldowns")
        await tx.execute("UPDATE players SET energy = 100, energy_at = ? WHERE id = ?", (services.ctx.now(), a.id))
    doubled = await services.activities.perform(a.id, "fishing", CHAT)
    assert doubled.double_xp and not normal.double_xp
    assert doubled.rolled.xp == normal.rolled.xp * 2


async def test_greeting_and_commands(h, services, db, clock):
    await hero(services, db, 1, "آرش", level=7)
    await hero(services, db, 2, "سارا", level=7)
    await h.say(2, "رویدادها", group=True)
    assert "رویدادهای گروه" in h.session.sent()[-1]["text"]
    await h.say(2, "/event merchant", group=True)
    assert "مدیران" in h.session.sent()[-1]["text"]
    await h.say(1, "/event merchant", group=True)
    assert "تاجر دوره‌گرد" in h.session.sent()[-1]["text"]
    assert h.session.sent()[-1]["reply_markup"]
    await h.say(1, "/event bogus", group=True)
    assert "نوع رویداد" in h.session.sent()[-1]["text"]
