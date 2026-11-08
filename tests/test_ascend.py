import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.engine import progression
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=25, gold=20_000, crystal=50):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, crystal=crystal, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def test_stats_grow_with_second_class_and_awakening():
    plain = progression.base_stats("elf", "warrior", 20)
    second = progression.base_stats("elf", "warrior", 20, "mage")
    awake = progression.base_stats("elf", "warrior", 20, "mage", True)
    assert second.magic > plain.magic
    assert all(getattr(awake, f) >= getattr(second, f) for f in plain.as_dict())
    assert awake.hp > second.hp


async def test_second_class_rules_and_cost(services, db):
    low = await hero(services, db, 1, "تازه", level=5)
    with pytest.raises(GameError, match="سطح"):
        await services.characters.choose_second_class(low, "mage")
    p = await hero(services, db, 2, "آرش")
    with pytest.raises(GameError):
        await services.characters.choose_second_class(p, "warrior")  # same as the first
    before = p.gold
    stats_before = await services.characters.stats(p)
    after = await services.characters.choose_second_class(p, "mage")
    assert after.class2_id == "mage" and after.gold == before - services.ctx.balance.second_class_gold
    assert (await services.characters.stats(after)).magic > stats_before.magic
    with pytest.raises(GameError, match="کلاس دوم"):
        await services.characters.choose_second_class(after, "archer")


async def test_awakening_costs_gold_and_crystals_once(services, db):
    poor = await hero(services, db, 3, "فقیر", crystal=0)
    with pytest.raises(GameError):
        await services.characters.awaken(poor)
    assert not (await services.players.require(3)).awakened
    p = await hero(services, db, 4, "سارا")
    before = await services.characters.stats(p)
    after = await services.characters.awaken(p)
    assert after.awakened and after.crystal == p.crystal - services.ctx.balance.awaken_crystal
    assert (await services.characters.stats(after)).hp > before.hp
    with pytest.raises(GameError, match="بیدار"):
        await services.characters.awaken(after)


async def test_glass_flow_and_profile_lines(h, services, db):
    await hero(services, db, 5, "رها")
    await h.say(5, "قلمرو", group=True)
    await h.tap(5, "شخصیت من", group=True)
    await h.tap(5, "ارتقای قهرمان", group=True)
    await h.tap(5, "انتخاب کلاس دوم", group=True)
    await h.click(5, h.button_data("جادوگر"), group=True)
    await h.tap(5, "بله", group=True)
    assert (await services.players.require(5)).class2_id == "mage"
    await h.tap(5, "بیدار کردن", group=True)
    await h.tap(5, "بیدار شو", group=True)
    assert (await services.players.require(5)).awakened
    await h.panel(5, "profile", group=True)
    text = h.session.sent("editMessageText")[-1]["text"]
    assert "کلاس دوم" in text and "قدرت پنهان" in text
