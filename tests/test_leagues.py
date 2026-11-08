import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import clans as clan_repo
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.leagues import league_of, new_ratings
from eternal_realm.shared.errors import GameError


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


async def hero(services, db, uid, name, gold=5_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def test_league_names_and_elo():
    assert [league_of(r).id for r in (0, 1000, 1100, 1250, 1450, 1700)] == [
        "bronze", "bronze", "silver", "gold", "diamond", "legend",
    ]
    up, down = new_ratings(1000, 1000)
    assert up == 1014 and down == 986
    underdog, _ = new_ratings(900, 1300)
    favourite, _ = new_ratings(1300, 900)
    assert underdog - 900 > favourite - 1300
    assert new_ratings(1000, 0)[1] == 0


async def test_war_points_prize_and_one_claim(services, db, clock):
    leader, mate = await hero(services, db, 1, "رهبر"), await hero(services, db, 2, "آرش")
    clan = await services.clans.create(leader, "جنگجویان")
    await services.clans.join(mate, clan.id)
    clock.advance(clan_repo.WEEK)  # members must have joined before the week that counts
    now = services.ctx.now()
    async with db.transaction() as tx:
        await clan_repo.add_war_points(tx, leader.id, 70, now)
        await clan_repo.add_war_points(tx, mate.id, 30, now)

    view = await services.clans.war(leader)
    assert [(s.name, s.points, s.mine) for s in view.week_rows] == [("جنگجویان", 100, True)]
    assert view.prize == 0  # nothing from last week yet
    with pytest.raises(GameError):
        await services.clans.claim_war(leader)

    clock.advance(clan_repo.WEEK)  # the week ends: this clan was first
    view = await services.clans.war(mate)
    assert view.prize == 800 and view.last_place == 1
    before = (await services.players.require(2)).gold
    assert await services.clans.claim_war(mate) == 800
    assert (await services.players.require(2)).gold == before + 800
    with pytest.raises(GameError):
        await services.clans.claim_war(mate)
    assert (await services.clans.war(leader)).prize == 800  # each member claims once


async def test_leaving_clan_players_get_no_points(services, db):
    solo = await hero(services, db, 5, "تنها")
    async with db.transaction() as tx:
        await clan_repo.add_war_points(tx, solo.id, 50, services.ctx.now())
        assert await clan_repo.war_board(tx, clan_repo.week_of(services.ctx.now()), 5) == []
