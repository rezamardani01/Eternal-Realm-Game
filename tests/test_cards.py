import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.cards import CARDS, PACK_ODDS, PACK_PRICE, SETS, cards_in, get_card
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=20_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def test_roster_is_big_and_every_set_has_cards():
    assert len({c.id for c in CARDS}) == len(CARDS) >= 30
    assert all(cards_in(s.id) for s in SETS)
    assert sum(PACK_ODDS.values()) == 100


async def test_pack_costs_gold_and_fills_the_album(services, db):
    p = await hero(services, db, 1, "آرش")
    result = await services.cards.buy_pack(p)
    assert len(result.cards) == 5
    assert (await services.players.require(1)).gold == p.gold - PACK_PRICE
    owned = await services.cards.owned(p.id)
    assert sum(owned.values()) == 5
    poor = await hero(services, db, 2, "فقیر", gold=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 0 WHERE id = ?", (poor.id,))
    with pytest.raises(GameError):
        await services.cards.buy_pack(await services.players.require(2))


async def test_duplicates_sell_but_the_last_copy_stays(services, db):
    p = await hero(services, db, 3, "سارا")
    async with db.transaction() as tx:
        assert await services.cards.grant(tx, p.id, "hero_mage") is True
        assert await services.cards.grant(tx, p.id, "hero_mage") is False
    with pytest.raises(GameError, match="تکراری"):
        await services.cards.sell_duplicate(p, "hero_rogue")
    gold = (await services.players.require(3)).gold
    value = await services.cards.sell_duplicate(p, "hero_mage")
    assert (await services.players.require(3)).gold == gold + value
    with pytest.raises(GameError, match="تکراری"):
        await services.cards.sell_duplicate(p, "hero_mage")


async def test_completing_a_set_gives_title_and_crystals_once(services, db):
    p = await hero(services, db, 4, "رها")
    with pytest.raises(GameError, match="هنوز"):
        await services.cards.claim_set(p, "heroes")
    async with db.transaction() as tx:
        for card in cards_in("heroes"):
            await services.cards.grant(tx, p.id, card.id)
    crystals = (await services.players.require(4)).crystal
    reward = await services.cards.claim_set(p, "heroes")
    after = await services.players.require(4)
    assert after.crystal == crystals + reward.crystals and after.honor == reward.title
    with pytest.raises(GameError, match="قبلاً"):
        await services.cards.claim_set(p, "heroes")


async def test_hunting_can_drop_the_monster_card(services, db):
    p = await hero(services, db, 5, "نگار")
    got = 0
    async with db.transaction() as tx:
        for _ in range(200):
            got += bool(await services.cards.drop_for_monster(tx, p.id, "wolf", chance=0.5))
    assert 50 < got < 150
    assert (await services.cards.owned(p.id)).get("mon_wolf", 0) == got


async def test_glass_flow(h, services, db):
    await hero(services, db, 6, "پویا")
    await h.say(6, "آلبوم", group=True)
    assert "آلبوم کارت" in h.session.sent()[-1]["text"]
    await h.tap(6, "بسته‌ی کارت", group=True)
    assert "شانس هر کارت" in h.session.sent("editMessageText")[-1]["text"]
    await h.tap(6, "بله، بخر", group=True)
    assert "کارت‌های بسته" in h.session.sent("editMessageText")[-1]["text"]
    await h.tap(6, "آلبوم", group=True)
    await h.click(6, h.button_data("قهرمانان"), group=True)
    assert "از ۵ کارت" in h.session.sent("editMessageText")[-1]["text"]
    assert get_card("hero_warrior").name
