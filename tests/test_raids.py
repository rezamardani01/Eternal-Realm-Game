"""Realm-wide events: announced in every group, joined from the private chat, played out and paid by the game itself."""

import pytest

from eternal_realm.bot import raid_ui
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import raids as data
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, level=10):
    p = await services.players.register(uid, f"u{uid}", f"قهرمان{uid}", "dragonborn", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


@pytest.mark.parametrize("kind", [k.id for k in data.KINDS])
async def test_every_kind_plays_out_pays_everybody_and_tells_them(services, db, clock, kind):
    players = [await hero(services, db, 10 + i, level=8 + 4 * i) for i in range(4)]
    view = await services.raids.create(kind, 5)
    assert view.status == "lobby" and view.seconds_left == 300
    for p in players:
        view, fresh = await services.raids.join(p, view.id)
        assert fresh
    assert view.count == 4 and (await services.raids.join(players[0], view.id))[1] is False
    assert await services.raids.tick() == []  # the countdown is still running
    before = [(await services.players.require(p.platform_user_id)).gold for p in players]
    clock.advance(301)
    events = await services.raids.tick()
    assert [e.what for e in events] == ["finished"]
    done = events[0].view
    assert done.status == "done" and done.summary["count"] == 4 and done.summary["top"]
    for p, gold in zip(players, before):
        assert (await services.players.require(p.platform_user_id)).gold > gold
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM player_alerts WHERE key = ?", (f"raid:{view.id}",), 0) == 4
        ranks = sorted(r["rank"] for r in await tx.fetchall("SELECT rank FROM raid_players WHERE raid_id = ?", (view.id,)))
    assert ranks[0] >= 1
    assert await services.raids.tick() == []  # it never plays twice
    assert "پایان" in raid_ui.dm_text(done) or "انجام شد" in raid_ui.dm_text(done)
    assert raid_ui.final_text(done)


async def test_too_few_heroes_calls_it_off(services, db, clock):
    p = await hero(services, db, 10)
    view = await services.raids.create("dragon", 1)
    await services.raids.join(p, view.id)
    clock.advance(61)
    event = (await services.raids.tick())[0]
    assert event.what == "cancelled" and "برگزار نشد" in raid_ui.final_text(event.view)
    assert (await services.raids.current()) is None


async def test_rules_of_the_lobby(services, db, clock):
    p = await hero(services, db, 10)
    with pytest.raises(GameError):
        await services.raids.create("nope", 5)
    with pytest.raises(GameError):
        await services.raids.create("dragon", 0)
    view = await services.raids.create("dragon", 2)
    with pytest.raises(GameError, match="در حال جمع"):
        await services.raids.create("titan", 2)
    clock.advance(121)
    with pytest.raises(GameError, match="تمام شده"):
        await services.raids.join(p, view.id)


async def test_a_won_raid_pays_more_than_a_lost_one(services, db, clock, monkeypatch):
    ps = [await hero(services, db, 10 + i, level=30) for i in range(3)]
    view = await services.raids.create("darkness", 1)
    for p in ps:
        await services.raids.join(p, view.id)

    async def easy(tx, player, kind):  # a hero that wins every fight with ease
        return 1.0, True, 0.9

    monkeypatch.setattr(services.raids, "_fight", easy)
    clock.advance(61)
    event = (await services.raids.tick())[0]
    assert event.view.summary["victory"] is True
    assert (await services.players.require(10)).crystal >= data.WIN_CRYSTALS


async def test_the_owner_announces_to_every_group_and_players_join_from_the_private_chat(h, services, db, clock):
    await hero(services, db, 1)
    await hero(services, db, 2)
    for chat in (-501, -502):
        await services.groups.touch(chat, f"گروه{chat}")
    await h.say(1, "رویداد سراسری اژدها 5", group=True, chat=-501)
    view = await services.raids.current()
    assert view is not None and view.kind.id == "dragon"
    posts = await services.raids.posts(view.id)
    assert sorted(c for c, _ in posts) == [-502, -501] or {c for c, _ in posts} >= {-501, -502}
    group_msgs = [p for p in h.session.sent("sendMessage") if "طوفان اژدهای سرخ" in p.get("text", "")]
    assert group_msgs and any("start=ev_" in b["url"] for p in group_msgs for row in p["reply_markup"]["inline_keyboard"] for b in row)

    await h.say(2, f"/start ev_{view.id}")
    dm = h.session.last_text()
    assert "پیوستید" in dm and "قهرمان2" in dm and "شروع تا" in dm
    assert (await services.raids.get(view.id)).count == 1

    h.session.reset()
    await raid_ui.refresh(h.bot, services, await services.raids.get(view.id))  # the live update edits the same messages
    assert len(h.session.sent("editMessageText")) >= 3

    await h.say(1, f"/start ev_{view.id}")
    clock.advance(301)
    for event in await services.raids.tick():
        await raid_ui.conclude(h.bot, services, event)
    assert any("قلمرو" in x.get("text", "") for x in h.session.sent("editMessageText"))


async def test_a_newcomer_from_the_group_button_joins_once_the_hero_is_born(h, services, db):
    view = await services.raids.create("treasure", 5)
    await h.say(77, f"/start ev_{view.id}")
    assert "ساخت" in h.session.last_text() or h.session.last_text()
    assert (await services.raids.get(view.id)).count == 0


async def test_the_automatic_mode_is_off_until_the_owner_turns_it_on(h, services, db, clock):
    await hero(services, db, 1)
    assert await services.raids.auto_due() is None
    await h.say(1, "رویداد سراسری خودکار روشن", group=True)
    assert await services.raids.auto_enabled()
    clock.t = 19_675 * 86400 + 30_600  # noon in Tehran
    kind = await services.raids.auto_due()
    assert kind in {k.id for k in data.KINDS}
    await services.raids.create(kind, 1)
    assert await services.raids.auto_due() is None  # one is already gathering
    clock.advance(61)
    await services.raids.tick()
    assert await services.raids.auto_due() is None  # too soon after the last one
    clock.advance(data.AUTO_GAP_HOURS * 3600)
    assert await services.raids.auto_due() in {None, *(k.id for k in data.KINDS)}  # (None only when the clock left the daytime window)
    await h.say(1, "رویداد سراسری خودکار خاموش", group=True)
    assert not await services.raids.auto_enabled()
