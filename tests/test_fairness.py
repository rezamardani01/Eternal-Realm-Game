import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.engine import combat
from eternal_realm.game.engine.combat import Action, Fighter

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


def fighter(scale: float, pet: int = 0) -> Fighter:
    return Fighter(
        name="x", emoji="x", max_hp=round(200 * scale), hp=round(200 * scale), atk=round(30 * scale),
        defense=round(20 * scale), magic=round(10 * scale), speed=10, luck=5, pet_power=pet,
    )


def test_the_stronger_sides_advantage_is_capped_but_never_removed():
    weak, strong = fighter(1), fighter(4)
    ratio, who = combat.level_field([[weak], [strong]])
    assert who == 1 and ratio > 3  # the real gap is remembered for the rewards
    after = combat.power_of(strong) / combat.power_of(weak)
    assert combat.PVP_CAP - 0.05 <= after <= combat.PVP_CAP + 0.1
    assert strong.atk > weak.atk and strong.max_hp > weak.max_hp  # still stronger
    close_a, close_b = fighter(1), fighter(1.3)
    before = (close_b.atk, close_b.max_hp)
    combat.level_field([[close_a], [close_b]])
    assert (close_b.atk, close_b.max_hp) == before  # an even match is left alone
    assert combat.level_field([[fighter(1)], [fighter(1)]]) == (1.0, -1)


def test_a_legendary_pet_cannot_decide_a_duel():
    plain, pet = fighter(1), fighter(1, pet=90)
    combat.level_field([[plain], [pet]])
    assert pet.pet_power <= round(pet.atk * combat.PVP_PET_SHARE) + 4


def test_teams_are_compared_by_the_average_member():
    solo, trio = [fighter(3)], [fighter(1), fighter(1), fighter(1)]
    ratio, strong = combat.level_field([solo, trio])
    assert strong == 0 and ratio > 1.7
    assert combat.power_of(solo[0]) / combat.power_of(trio[0]) <= 1.8


def test_winning_against_the_weak_pays_little_and_against_the_strong_pays_more():
    assert combat.reward_factor(1.2, True) == 1.0
    assert combat.reward_factor(1.8, True) == 0.6 and combat.reward_factor(2.5, True) == 0.3 and combat.reward_factor(5, True) == 0.0
    assert combat.reward_factor(1.0, False) == 1.0 and combat.reward_factor(3.0, False) == 2.0 and combat.reward_factor(9, False) == 2.0


async def hero(services, db, uid, name, level, gold=0):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        if gold:
            await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def play(services, duel_id, a, b):
    for _ in range(300):
        d = await services.duels.get(duel_id)
        if d.status != "active":
            return d
        who = a if d.battle.current.player_id == a.id else b
        await services.duels.act(duel_id, who, Action.ATTACK)
    raise AssertionError("duel did not end")


async def test_the_invitation_says_how_the_two_compare(h, services, db):
    novice = await hero(services, db, 1, "تازه‌کار", 3)
    giant = await hero(services, db, 2, "غولک", 40)
    note = await services.duels.compare(novice, giant)
    assert "غولک" in note and "برابر" in note and "محدود" in note
    even = await services.duels.compare(novice, novice)
    assert "برابر" in even and "هم‌شأن" in even
    await h.say(1, "مبارزه", group=True, reply_to=h.message_of(2))
    assert "قدرت" in h.session.last_text() and "غولک" in h.session.last_text()


async def test_a_duel_between_a_novice_and_a_giant_is_capped_and_the_giants_win_pays_nothing(services, db):
    novice = await hero(services, db, 1, "تازه‌کار", 3)
    giant = await hero(services, db, 2, "غولک", 40)
    duel = await services.duels.challenge(-500, giant, novice)
    update = await services.duels.accept(duel.id, novice)
    battle = update.battle
    assert battle.power_ratio > 3 and battle.strong == 0
    strong, weak = battle.fighters
    assert combat.power_of(strong) / combat.power_of(weak) <= combat.PVP_CAP + 0.15
    gold_before = (await services.players.require(2)).gold
    final = await play(services, duel.id, giant, novice)
    if final.winner_id == giant.id:
        assert (await services.players.require(2)).gold == gold_before  # a win over somebody that weak pays nothing
        async with db.read() as tx:
            assert await tx.scalar("SELECT rating FROM players WHERE id = ?", (giant.id,), 0) == 1000  # and moves no rating
    else:
        assert (await services.players.require(1)).gold > novice.gold  # the novice's win pays well
