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


# --- cities ------------------------------------------------------------------------------------------------------
def test_the_loot_factor_and_trophies_follow_the_strength_gap():
    from eternal_realm.game.data import city as d
    from eternal_realm.game.services.city import City, CityService

    assert [d.loot_factor(r) for r in (0.3, 0.6, 1.0, 1.6, 2.5, 4.0)] == [1.6, 1.3, 1.0, 0.6, 0.3, 0.1]
    assert d.START_SHIELD == 3 * 86400

    def city(trophies=0):
        return City(1, 1, "x", "🦁", {r: 0.0 for r in d.RES}, 300, 100, 0, 0, trophies, 0, 0, 0, 0)

    svc = CityService.__new__(CityService)
    assert svc._trophies(city(), city(), 0) == (-8, 6)
    fair = svc._trophies(city(), city(), 2, 1.0)[0]
    assert fair > 0 and svc._trophies(city(), city(), 3, 2.5) == (0, 0)  # beating a far weaker city changes nothing
    assert svc._trophies(city(), city(), 2, 0.5)[0] > fair  # beating a stronger one pays more


async def make_city(services, db, uid, name):
    from eternal_realm.game.data import city as d

    p = await hero(services, db, uid, f"قهرمان{uid}", 10, gold=50_000)
    c = await services.city.found(p, name, d.FLAGS[0][0])
    async with db.transaction() as tx:
        await tx.execute("UPDATE cities SET shield_until = 0 WHERE id = ?", (c.id,))
    return p, c


async def raid(services, db, attacker, a_city, d_city, sword):
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO city_troops (city_id, kind, qty) VALUES (?, 'sword', ?)"
            " ON CONFLICT (city_id, kind) DO UPDATE SET qty = ?", (a_city.id, sword, sword),
        )
        await tx.execute("UPDATE cities SET food = 100000, shield_until = 0 WHERE id IN (?, ?)", (a_city.id, d_city.id))
    await services.city.search(attacker)
    await services.city.adjust(attacker, None, 0, everyone=True)
    return await services.city.attack(attacker)


async def test_a_bully_gets_little_and_a_victim_is_left_in_peace_after_repeated_hits(services, db, clock, h):
    big_p, big = await make_city(services, db, 1, "بزرگ‌شهر")
    small_p, small = await make_city(services, db, 2, "خردشهر")
    res = await raid(services, db, big_p, big, small, 400)
    assert res.ratio >= 3 and res.loot["gold"] <= small.res["gold"] * 0.15 * 0.1 + 2  # a tenth of the usual loot
    assert res.trophies == 0 and res.xp <= 12  # a tenth of the usual experience
    victim_after = await services.city.mine(small_p, visit=False)
    assert victim_after.troops == {} or sum(victim_after.troops.values()) == 0
    # three successful raids in a day, by different raiders, put the weak city to rest even when little was destroyed
    for uid, name in ((3, "سومین‌شهر"), (4, "چهارمین‌شهر")):
        other_p, other = await make_city(services, db, uid, name)
        async with db.transaction() as tx:
            await tx.execute("UPDATE cities SET shield_until = 0 WHERE id = ?", (small.id,))
        await raid(services, db, other_p, other, small, 400)
    async with db.read() as tx:
        row = await tx.fetchone("SELECT shield_until FROM cities WHERE id = ?", (small.id,))
    assert row["shield_until"] >= services.ctx.now() + 12 * 3600 - 5
    # the target card tells the raider what to expect
    from eternal_realm.bot.city_panel import _fairness_note

    assert "ضعیف‌تر" in _fairness_note(3.5) and "قوی‌تر" in _fairness_note(0.3) and "هم‌شأن" in _fairness_note(1.0)
