import pytest

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


async def hero(services, db, uid, name, level=5, gold=1_000):
    p = await services.players.register(uid, f"u{uid}", name, "dragonborn", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def stack(db, pid, item):
    async with db.read() as tx:
        return await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = ?", (pid, item), 0)


async def test_owner_gifts_any_item_by_name_and_amount(h, services, db):
    await hero(services, db, 1, "ارباب")
    target = await hero(services, db, 2, "آرش")
    await h.say(1, "اهدا سنگ آهن 399", group=True, reply_to=h.message_of(2))
    assert await stack(db, target.id, "iron_ore") == 399
    assert "سنگ آهن" in h.session.last_text()
    await h.say(1, "اهدا صندوقچه جادویی", group=True, reply_to=h.message_of(2))
    assert await stack(db, target.id, "magic_chest") == 1
    await h.say(1, "اهدا چیزی که نیست 3", group=True, reply_to=h.message_of(2))
    assert "پیدا نشد" in h.session.last_text()
    await h.say(1, "اهدا مسیر قهرمانی", group=True, reply_to=h.message_of(2))
    assert "بلیط طلایی" in h.session.last_text()
    await h.say(1, "اهدا سطح 40", group=True, reply_to=h.message_of(2))
    assert (await services.players.require(2)).level == 40
    await h.say(3, "اهدا سنگ آهن 5", group=True, reply_to=h.message_of(2))  # someone else: ignored
    assert await stack(db, target.id, "iron_ore") == 399


async def test_owner_summons_events_at_will_and_others_cannot(h, services, db):
    await hero(services, db, 1, "ارباب")
    await hero(services, db, 2, "آرش")
    await services.groups.touch(CHAT, "گروه")
    await h.say(2, "احضار دوره گرد", group=True)
    assert not await services.events.active(CHAT)
    await h.say(1, "احضار دوره گرد", group=True)
    await h.say(1, "احضار شهاب", group=True)  # even while the merchant is there
    await h.say(1, "احضار تهاجم", group=True)
    kinds = sorted(v.kind for v in await services.events.active(CHAT))
    assert kinds == ["invasion", "merchant", "meteor"]
    await h.say(1, "احضار هیچی", group=True)
    assert "احضار دوره گرد" in h.session.last_text()


async def test_owner_boss_and_energy_have_no_limits(h, services, db):
    owner = await hero(services, db, 1, "ارباب", level=1, gold=0)
    await hero(services, db, 2, "آرش", level=1, gold=0)
    gold = (await services.players.require(1)).gold
    first = await services.bosses.summon(owner, CHAT)  # level 1
    assert first.id
    async with db.transaction() as tx:
        await tx.execute("UPDATE bosses SET status = 'expired', ended_at = ? WHERE id = ?", (services.ctx.now(), first.id))
    again = await services.bosses.summon(owner, CHAT)  # straight away: no cooldown
    assert again.id != first.id and (await services.players.require(1)).gold == gold  # free
    async with db.transaction() as tx:
        await tx.execute("UPDATE bosses SET status = 'expired', ended_at = ? WHERE id = ?", (services.ctx.now(), again.id))
    with pytest.raises(GameError):
        await services.bosses.summon(await services.players.require(2), CHAT)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 0 WHERE id = 1")
        await services.players.spend_energy(tx, owner.id, 50)  # never runs out
        assert await services.players.schedule_cooldown(tx, owner.id, "hunt") == 0


async def test_owner_duels_without_the_daily_pair_limit(services, db):
    owner = await hero(services, db, 1, "ارباب")
    other = await hero(services, db, 2, "آرش")
    limit = services.ctx.balance.duel_pair_daily_limit
    for _ in range(limit + 2):
        duel = await services.duels.challenge(CHAT, owner, other)
        await services.duels.decline(duel.id, other)
        async with db.transaction() as tx:  # a declined invite is not counted: make it a finished one
            await tx.execute("UPDATE duels SET status = 'finished' WHERE id = ?", (duel.id,))
    normal = await hero(services, db, 3, "سارا")
    for _ in range(limit):
        duel = await services.duels.challenge(CHAT, normal, other)
        async with db.transaction() as tx:
            await tx.execute("UPDATE duels SET status = 'finished' WHERE id = ?", (duel.id,))
    with pytest.raises(GameError, match="شمشیرها خسته"):
        await services.duels.challenge(CHAT, normal, other)


async def test_the_owner_command_list(h, services, db):
    await hero(services, db, 1, "ارباب")
    await h.say(1, "دستورات مالک", group=True)
    text = h.session.last_text()
    assert "اهدا مسیر قهرمانی" in text and "احضار دوره گرد" in text and "اهدا سنگ آهن 399" in text
