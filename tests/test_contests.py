import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import clans as clan_repo
from eternal_realm.db.repos import season as season_repo
from eternal_realm.game.services.contests import CONTESTS, PRIZES
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "warrior")


async def do(db, services, p, deed, times):
    async with db.transaction() as tx:
        for _ in range(times):
            await season_repo.add_points(tx, p.id, deed, services.ctx.now())


async def test_deeds_feed_the_right_contests(services, db):
    a, b = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    await do(db, services, a, "duel_win", 3)
    await do(db, services, b, "duel_win", 5)
    await do(db, services, a, "dungeon", 1)
    await do(db, services, a, "dungeon_win", 1)
    duel = await services.contests.standing(a, "duel")
    assert [(r.name, r.count) for r in duel.rows] == [("سارا", 5), ("آرش", 3)] and duel.my_place == 2
    assert (await services.contests.standing(a, "dungeon")).my_count == 2
    assert (await services.contests.standing(a, "hunt")).my_place is None
    with pytest.raises(GameError):
        await services.contests.standing(a, "nonsense")


async def test_prizes_arrive_next_week_for_the_top_three_once(services, db, clock):
    ps = [await hero(services, db, 10 + i, f"قهرمان{i}") for i in range(4)]
    for i, p in enumerate(ps):
        await do(db, services, p, "hunt", 10 - i)  # the fourth one misses the podium
    assert await services.contests.prizes(ps[0]) == []
    with pytest.raises(GameError):
        await services.contests.claim(ps[0])
    clock.advance(clan_repo.WEEK)
    assert await services.contests.prizes(ps[3]) == []
    first = await services.contests.prizes(ps[0])
    assert first == [("hunt", 1, PRIZES[0])]
    gold = (await services.players.require(10)).gold
    assert await services.contests.claim(ps[0]) == PRIZES[0]
    after = await services.players.require(10)
    assert after.gold == gold + PRIZES[0] and "بیشترین شکار" in after.honor
    with pytest.raises(GameError):
        await services.contests.claim(ps[0])
    assert await services.contests.claim(ps[2]) == PRIZES[2]


async def test_glass_flow(h, services, db):
    p = await hero(services, db, 20, "نگار")
    await do(db, services, p, "mission", 2)
    await h.say(20, "مسابقه", group=True)
    assert "مسابقه‌های هفته" in h.session.last_text()
    assert len([b for b in h.session.last_buttons() if "contest" in b.get("callback_data", "")]) >= len(CONTESTS)
    await h.click(20, h.button_data("مأموریت تمام‌شده"), group=True)
    text = h.session.sent("editMessageText")[-1]["text"]
    assert "جایگاه شما" in text and "[نگار](uid:20)" in text
