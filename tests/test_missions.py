import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import season as season_repo
from eternal_realm.game.data.missions import KINDS, PER_DAY
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=1):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


async def do(db, services, p, deed, times):
    async with db.transaction() as tx:
        for _ in range(times):
            await season_repo.add_points(tx, p.id, deed, services.ctx.now())


def test_mission_kinds_are_unique():
    assert len({k.id for k in KINDS}) == len(KINDS)


async def test_missions_fit_the_player_and_stay_the_same_all_day(services, db):
    low = await hero(services, db, 1, "تازه", level=1)
    got = await services.missions.today(low)
    assert len(got) == PER_DAY
    assert all(m.kind_id not in ("boss1", "duel1", "dungeon1", "clan2") for m in got)  # too high level for those
    assert [m.kind_id for m in await services.missions.today(low)] == [m.kind_id for m in got]


async def test_progress_claim_and_path_points(services, db):
    p = await hero(services, db, 2, "سارا", level=10)
    got = await services.missions.today(p)
    first = got[0]
    kind = next(k for k in KINDS if k.id == first.kind_id)
    with pytest.raises(GameError, match="تمام نشده"):
        await services.missions.claim(p, first.slot)
    await do(db, services, p, kind.deed, kind.target + 2)  # extra deeds do not overflow
    again = (await services.missions.today(p))[0]
    assert again.progress == again.target and again.done
    gold = (await services.players.require(2)).gold
    path_before = (await services.season.state(p)).points
    paid = await services.missions.claim(p, first.slot)
    assert (await services.players.require(2)).gold == gold + paid.gold
    assert (await services.season.state(p)).points >= path_before + 20
    with pytest.raises(GameError, match="قبلاً"):
        await services.missions.claim(p, first.slot)


async def test_new_day_new_missions(services, db, clock):
    p = await hero(services, db, 3, "رها", level=10)
    day_one = [m.kind_id for m in await services.missions.today(p)]
    clock.advance(86400)
    day_two = await services.missions.today(p)
    assert all(m.progress == 0 and not m.claimed for m in day_two) and len(day_two) == PER_DAY
    assert day_one is not None


async def test_glass_flow(h, services, db):
    p = await hero(services, db, 4, "نگار", level=10)
    first = (await services.missions.today(p))[0]
    kind = next(k for k in KINDS if k.id == first.kind_id)
    await do(db, services, p, kind.deed, kind.target)
    await h.say(4, "ماموریت‌های امروز", group=True)
    assert "مأموریت‌ها" in h.session.sent()[-1]["text"]
    await h.tap(4, "دریافت پاداش", group=True)
    assert "گرفته شد" in h.session.sent("editMessageText")[-1]["text"]
