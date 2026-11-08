import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.packs import PACKS
from eternal_realm.game.data.pets import PETS, get_pet
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(
        AppContext(db, Settings(token="t", owner_id=1, provider_token="WALLET-TEST-1"), clock=clock, rng=rng)
    )


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=20_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def test_every_premium_pet_has_a_pack():
    for pet in PETS:
        assert bool(pet.price_gold) != bool(pet.pack_id)
        if pet.pack_id:
            assert PACKS[pet.pack_id].pet == pet.id


async def test_coin_pet_is_bought_once_and_changes_stats(services, db):
    p = await hero(services, db, 1, "آرش")
    before = await services.characters.stats(p)
    gold = p.gold
    await services.pets.buy_with_gold(p, "cat")
    assert (await services.players.require(1)).gold == gold - get_pet("cat").price_gold
    after = await services.characters.stats(await services.players.require(1))
    assert after.speed == before.speed + 3 and after.luck == before.luck + 2
    with pytest.raises(GameError, match="از قبل"):
        await services.pets.buy_with_gold(p, "cat")
    with pytest.raises(GameError, match="خزانه"):
        await services.pets.buy_with_gold(p, "fox")


async def test_only_one_pet_is_active(services, db):
    p = await hero(services, db, 2, "سارا")
    await services.pets.buy_with_gold(p, "cat")
    await services.pets.buy_with_gold(p, "hawk")
    assert await services.pets.owned(p.id) == {"cat": True, "hawk": False}
    await services.pets.activate(p, "hawk")
    assert await services.pets.owned(p.id) == {"cat": False, "hawk": True}
    with pytest.raises(GameError):
        await services.pets.activate(p, "wolf")


async def test_premium_pet_order_delivers_and_blocks_a_second_purchase(h, services, db):
    p = await hero(services, db, 3, "رها")
    order = await services.payments.create_order(p, "pet_fox")
    delivery = await services.payments.complete(3, order.payload, order.amount, "charge-1")
    assert delivery.order.status == "delivered"
    assert await services.pets.owned(p.id) == {"fox": True}
    with pytest.raises(GameError, match="از قبل"):
        await services.payments.create_order(p, "pet_fox")


async def test_glass_flow(h, services, db):
    await hero(services, db, 4, "نگار")
    await h.say(4, "حیوان همراه", group=True)
    await h.click(4, h.button_data("گربه"), group=True)
    await h.tap(4, "خرید", group=True)
    assert "تأیید خرید" in h.session.sent("editMessageText")[-1]["text"]
    await h.tap(4, "بله، بخر", group=True)
    assert await services.pets.owned((await services.players.require(4)).id) == {"cat": True}
    assert "همین حالا همراه شماست" in h.session.sent("editMessageText")[-1]["text"]


async def test_upgrading_a_pet_costs_crystals_and_strengthens_it(services, db):
    from eternal_realm.game.data.pets import MAX_PET_LEVEL, bonus_at, upgrade_cost

    p = await hero(services, db, 6, "کیان", gold=5_000)
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, crystal=100, reason="t", now=services.ctx.now())
    p = await services.players.require(6)
    await services.pets.buy_with_gold(p, "cat")
    base = await services.characters.stats(p)
    crystals = p.crystal
    pet, level = await services.pets.upgrade(p, "cat")
    assert level == 2 and (await services.players.require(6)).crystal == crystals - upgrade_cost(1)
    after = await services.characters.stats(p)
    assert after.speed >= base.speed and after.speed == base.speed - 3 + bonus_at(pet, 2).speed
    with pytest.raises(GameError, match="مال شما نیست"):
        await services.pets.upgrade(p, "wolf")
    async with db.transaction() as tx:
        await tx.execute("UPDATE player_pets SET level = ?", (MAX_PET_LEVEL,))
    with pytest.raises(GameError, match="بالاترین"):
        await services.pets.upgrade(p, "cat")


async def test_not_enough_crystals_changes_nothing(services, db):
    p = await hero(services, db, 7, "مینا", gold=5_000)
    await services.pets.buy_with_gold(p, "cat")
    p = await services.players.require(7)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET crystal = 1 WHERE id = ?", (p.id,))
    with pytest.raises(GameError):
        await services.pets.upgrade(await services.players.require(7), "cat")
    assert (await services.pets.levels(p.id))["cat"] == 1


def test_a_pet_announces_its_strike_in_the_duel_log():
    import random

    from eternal_realm.game.data.classes import CLASSES
    from eternal_realm.game.data.stats import Stats
    from eternal_realm.game.engine import combat

    stats = Stats(hp=500, atk=30, defense=5, magic=0, speed=10, luck=0)
    a = combat.Fighter.for_player(1, "آرش", CLASSES["warrior"], stats)
    a.pet_emoji, a.pet_name, a.pet_power = "🐱", "گربه‌ی چابک", 20
    b = combat.Fighter.for_player(2, "سارا", CLASSES["warrior"], stats)
    battle = combat.Battle.start(a, b, 15, random.Random(1))
    seen = []
    for _ in range(60):
        if battle.finished:
            break
        seen += combat.act(battle, combat.Action.ATTACK, random.Random(len(seen)))
    joined = [x for x in seen if "گربه‌ی چابک همراه آرش هم به سارا حمله کرد" in x]
    assert joined and "آسیب" in joined[0]
    assert not any("همراه سارا" in x for x in seen)  # the other fighter has no pet
    assert combat.Battle.from_dict(battle.to_dict()).fighters[0].pet_name == "گربه‌ی چابک"


def test_stronger_pets_cost_more_and_the_legendary_ones_are_sold_for_real_money_only():
    gold_pets = [p for p in PETS if p.price_gold]
    premium = [p for p in PETS if p.pack_id]
    assert len(PETS) >= 12 and len(gold_pets) >= 6 and len(premium) >= 6
    assert all(p.rarity <= 4 for p in gold_pets)  # the everyday ones can be bought with coins
    assert all(p.rarity >= 5 for p in PETS if p.rarity >= 5 and not p.price_gold)
    assert all(not p.price_gold and p.pack_id for p in PETS if p.rarity >= 5)  # legendary: real money only
    def power(p):
        b = p.bonus
        return b.atk + b.magic + b.defense + b.speed + b.luck + b.hp / 10
    strongest_gold = max(power(p) for p in gold_pets)
    assert max(power(p) for p in premium) > strongest_gold  # paid pets are stronger than anything coins buy
    assert max(power(p) for p in PETS if p.rarity == 6) > max(power(p) for p in PETS if p.rarity == 5) * 0.9
