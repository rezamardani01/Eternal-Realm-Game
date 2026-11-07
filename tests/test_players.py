import pytest

from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.services.players import DAY, PlayerService
from eternal_realm.shared.errors import GameError, NotRegistered


@pytest.fixture
def ctx(db, clock, rng):
    return AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng)


@pytest.fixture
def players(ctx):
    return PlayerService(ctx)


async def make(players, uid=100, name="آرش", race="elf", cls="archer"):
    return await players.register(uid, f"u{uid}", name, race, cls)


async def test_register_creates_character_with_start_gift(players, ctx):
    p = await make(players)
    assert p.name == "آرش" and p.level == 1
    assert p.gold == ctx.balance.start_gold
    assert p.energy == ctx.balance.base_energy


async def test_one_character_per_user_and_unique_names(players):
    await make(players)
    with pytest.raises(GameError):
        await make(players)
    with pytest.raises(GameError):
        await make(players, uid=101)  # same name
    await make(players, uid=101, name="سارا")


@pytest.mark.parametrize("bad", ["", "a", "x" * 40, "آرش!!", "admin", "<b>x</b>"])
async def test_invalid_names_rejected(players, bad):
    with pytest.raises(GameError):
        await make(players, name=bad)


async def test_require_unknown_user(players):
    with pytest.raises(NotRegistered):
        await players.require(999)


async def test_spend_energy_and_regen(players, ctx, clock):
    p = await make(players)
    async with ctx.db.transaction() as tx:
        await players.spend_energy(tx, p.id, 60)
    assert (await players.require(100)).energy == 40
    clock.advance(ctx.balance.energy_regen_seconds * 10)
    assert (await players.require(100)).energy == 50
    with pytest.raises(GameError):
        async with ctx.db.transaction() as tx:
            await players.spend_energy(tx, p.id, 99)


async def test_wallet_never_goes_negative_and_refs_are_idempotent(players, ctx):
    p = await make(players)
    async with ctx.db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=-10, reason="t", now=ctx.now(), ref="r1")
    with pytest.raises(wallet.DuplicateOperation):
        async with ctx.db.transaction() as tx:
            await wallet.apply(tx, p.id, gold=-10, reason="t", now=ctx.now(), ref="r1")
    with pytest.raises(wallet.InsufficientFunds):
        async with ctx.db.transaction() as tx:
            await wallet.apply(tx, p.id, gold=-10**9, reason="t", now=ctx.now())
    assert (await players.require(100)).gold == ctx.balance.start_gold - 10


async def test_daily_reward_once_per_day_and_streak(players, clock):
    p = await make(players)
    first = await players.claim_daily(p.id)
    assert first.streak == 1
    with pytest.raises(GameError):
        await players.claim_daily(p.id)
    clock.advance(DAY + 60)
    assert (await players.claim_daily(p.id)).streak == 2
    clock.advance(3 * DAY)
    assert (await players.claim_daily(p.id)).streak == 1


async def test_grant_xp_levels_up(players, ctx):
    p = await make(players)
    async with ctx.db.transaction() as tx:
        up = await players.grant_xp(tx, p.id, 100)
    assert up is not None and up.new_level == 2
