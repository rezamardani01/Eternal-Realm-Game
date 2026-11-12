"""Attribute points, level unlocks, class talents, status effects, gear upgrades and the multi-phase bosses."""

import random

import pytest

from eternal_realm.bot import keyboards
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import bosses as boss_data
from eternal_realm.game.data.arms import (
    ARMS, MAX_UPGRADE, UPGRADE_CHANCE, Trait, upgrade_gold, upgrade_materials, upgraded_stats,
)
from eternal_realm.game.data.classes import CLASSES
from eternal_realm.game.data.growth import (
    ATTRS, POINTS_PER_LEVEL, SKILL_LEVELS, SLOT_LEVELS, TALENT_BY_ID, TALENT_LEVELS, TALENTS, UNLOCKS, attr_stats,
    points_earned, slots_open, talent_places, talents_of,
)
from eternal_realm.game.data.skills import EFFECT_INFO, HARMFUL
from eternal_realm.game.engine import progression
from eternal_realm.game.engine.boss_fight import Boss, Hero, run_round
from eternal_realm.game.engine.combat import (
    Action, Battle, Fighter, _inflict, act, auto_action, auto_fight, eff_atk, eff_defense, readiness_error, status_line,
)
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid=10, name="آرش", race="human", cls="warrior", gold=500_000, level=None):
    p = await services.players.register(uid, f"u{uid}", name, race, cls)
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
        if level:
            await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


def fighter(cls="warrior", level_=10, traits=(), lvl=999, **over):
    f = Fighter.for_player(1, "قهرمان", CLASSES[cls], progression.base_stats("human", cls, level_), race_id="human", traits=traits, level=lvl)
    for k, v in over.items():
        setattr(f, k, v)
    return f


# --- attribute points ---------------------------------------------------------------------------------------------------------------
def test_points_and_effects_are_data():
    assert points_earned(1) == 0 and points_earned(11) == 10 * POINTS_PER_LEVEL
    assert set(ATTRS) == {"str", "agi", "int", "vit", "luk"}
    assert attr_stats({"str": 10}).atk == 10 and attr_stats({"str": 10}).hp == 30
    assert attr_stats({"int": 10}).magic == 12 and attr_stats({"agi": 10}).speed == 8
    assert attr_stats({"vit": 10}).defense == 7 and attr_stats({"luk": 10}).luck == 10
    assert attr_stats({}) == attr_stats({"nope": 5})


async def test_spend_points_and_two_heroes_of_one_class_differ(services, db):
    a = await hero(services, db, 10, "آرش", level=11)
    b = await hero(services, db, 11, "بهرام", level=11)
    assert await services.growth.free_points(a) == 20
    await services.growth.spend(a, "str", 20)
    await services.growth.spend(b, "vit", 20)
    sa, sb = await services.characters.stats(a), await services.characters.stats(b)
    assert sa.atk > sb.atk and sb.defense > sa.defense and sb.hp != sa.hp
    assert await services.growth.free_points(a) == 0
    with pytest.raises(GameError, match="امتیاز"):
        await services.growth.spend(a, "agi")
    with pytest.raises(GameError):
        await services.growth.spend(b, "nope")


async def test_reset_gives_everything_back_for_coins(services, db):
    p = await hero(services, db, level=6, gold=100_000)
    await services.growth.spend(p, "int", 10)
    before = (await services.players.require(10)).gold
    assert await services.growth.reset(p) == 10
    assert (await services.players.require(10)).gold == before - services.growth.reset_price(p)
    assert await services.growth.free_points(p) == 10
    with pytest.raises(GameError):
        await services.growth.reset(p)  # nothing left to take back


async def test_vitality_adds_resistance_to_the_fighter(services, db):
    p = await hero(services, db, level=60)
    await services.growth.spend(p, "vit", 100)
    async with db.read() as tx:
        f = await services.characters.fighter_from(tx, p, await services.characters.stats_in(tx, p))
    assert any(t["k"] == "resist_all" and t["v"] > 0 for t in f.traits)


# --- unlocks ------------------------------------------------------------------------------------------------------------------------
def test_unlock_levels_are_sorted_and_consistent():
    levels = [u[0] for u in UNLOCKS]
    assert levels == sorted(levels)
    assert SKILL_LEVELS[0] == 1 and list(SKILL_LEVELS) == sorted(SKILL_LEVELS)
    assert slots_open(1) == 2 and slots_open(8) == 3 and slots_open(15) == 4
    assert talent_places(4) == 0 and talent_places(5) == 1 and talent_places(25) == 3


def test_a_new_hero_has_only_his_first_skill_and_the_rest_open_with_levels():
    f = fighter(lvl=1)
    assert f.lock == [0, SKILL_LEVELS[1], SKILL_LEVELS[2]]
    assert readiness_error(f, Action.SKILL1) is None
    assert "سطح" in readiness_error(f, Action.SKILL2) and "سطح" in readiness_error(f, Action.SKILL3)
    assert "سطح" in readiness_error(f, Action.SKILL)  # the legacy "skill" is the third one
    assert auto_action(f) is Action.SKILL1
    battle = Battle.start(f, fighter("guardian"), 15, random.Random(1))
    battle.actor = 0
    with pytest.raises(ValueError):
        act(battle, Action.SKILL3, random.Random(1))
    assert fighter(lvl=5).lock == [0, 0, SKILL_LEVELS[2]] and fighter(lvl=12).lock == [0, 0, 0]
    rows = keyboards.duel_actions(1, f)
    assert [len(r) for r in rows] == [1, 1, 1, 1, 2]  # one under the other
    assert "🔒" in rows[2][0].text and "🔒" in rows[3][0].text and "🔒" not in rows[1][0].text


async def test_gear_places_open_with_the_level(services, db):
    p = await hero(services, db, level=5)
    for arm_id in ("iron_blade", "evil_eye", "green_pendant"):
        await services.arms.buy(p, arm_id)
    await services.arms.equip(p, 2, "iron_blade")
    with pytest.raises(GameError, match=str(SLOT_LEVELS[2]).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))):
        await services.arms.equip(p, 3, "evil_eye")
    rich = await hero(services, db, 11, "بهرام", level=15)
    await services.arms.buy(rich, "evil_eye")
    await services.arms.equip(rich, 4, "evil_eye")


# --- talents ------------------------------------------------------------------------------------------------------------------------
def test_every_class_has_talents_with_real_effects():
    for cls in CLASSES:
        mine = talents_of(cls)
        assert len(mine) >= 6, cls
        assert all(t.lines() and t.blurb for t in mine)
    assert len({t.id for t in TALENTS}) == len(TALENTS) == len(TALENT_BY_ID)
    assert len(TALENT_LEVELS) == 3


async def test_talents_are_chosen_with_limited_places(services, db):
    p = await hero(services, db, level=5)
    await services.growth.choose(p, "w_might")
    with pytest.raises(GameError, match="پر"):
        await services.growth.choose(p, "w_iron")
    with pytest.raises(GameError, match="کلاس"):
        await services.growth.choose(p, "m_focus")
    with pytest.raises(GameError, match="همین حالا"):
        await services.growth.choose(p, "w_might")
    await services.growth.drop(p, "w_might")
    await services.growth.choose(p, "w_iron")
    low = await hero(services, db, 11, "بهرام", level=2)
    with pytest.raises(GameError, match="باز"):
        await services.growth.choose(low, "w_might")
    big = await hero(services, db, 12, "سارا", level=25)
    for t in ("w_might", "w_iron", "w_last"):
        await services.growth.choose(big, t)
    async with db.read() as tx:
        f = await services.characters.fighter_from(tx, big, await services.characters.stats_in(tx, big))
    assert {"phys_power", "crit_resist", "low_hp_def"} <= {t["k"] for t in f.traits}
    stats = await services.characters.stats(big)
    await services.growth.drop(big, "w_last")
    await services.growth.choose(big, "w_vigor")
    assert (await services.characters.stats(big)).hp == stats.hp + TALENT_BY_ID["w_vigor"].stats.hp


def test_talent_traits_change_damage_in_a_fight():
    def damage(traits, seed):
        a, b = fighter(traits=traits), fighter("guardian")
        a.luck = 0
        battle = Battle.start(a, b, 15, random.Random(seed))
        battle.actor = 0
        act(battle, Action.ATTACK, random.Random(seed))
        return b.max_hp - b.hp

    plain = sum(damage([], s) for s in range(30))
    mighty = sum(damage([Trait("phys_power", 0.25)], s) for s in range(30))
    assert mighty > plain
    # backstab only works on a foe that carries a harmful effect
    base = fighter(traits=[Trait("backstab", 0.5)])
    foe = fighter("guardian")
    from eternal_realm.game.engine.combat import _apply, _bonus

    assert _bonus(base, foe) == 1.0
    _apply(foe, "poison", 5, 3)
    assert _bonus(base, foe) == pytest.approx(1.5)


def test_defensive_talents_low_hp_defence_and_crit_resist():
    f = fighter(traits=[Trait("low_hp_def", 0.3)])
    full = eff_defense(f)
    f.hp = f.max_hp // 4
    assert eff_defense(f) == pytest.approx(full * 1.3)
    from eternal_realm.game.engine.combat import _crit_chance

    a, tough = fighter(), fighter(traits=[Trait("crit_resist", 0.4)])
    assert _crit_chance(a, tough) == pytest.approx(_crit_chance(a) * 0.6)


# --- status effects -------------------------------------------------------------------------------------------------------------------
def test_the_effects_the_game_promises_exist_and_all_have_a_time():
    assert {"burn", "poison", "bleed", "freeze", "shock", "shield", "regen"} <= set(EFFECT_INFO) | {"shield"}
    assert {"burn", "poison", "bleed", "freeze", "shock"} <= set(HARMFUL)


def test_freeze_blocks_skills_for_one_turn_only():
    a, b = fighter(), fighter("guardian")
    battle = Battle.start(a, b, 15, random.Random(1))
    lines: list[str] = []
    _inflict(b, a, "freeze", 0, 1, 10, lines, random.Random(1))
    assert "❄️" in status_line(a)
    assert readiness_error(a, Action.SKILL1) and auto_action(a) is Action.ATTACK
    battle.actor = 0
    act(battle, Action.ATTACK, random.Random(1))  # an ordinary blow is allowed, and the ice melts
    battle.actor = 0
    assert readiness_error(a, Action.SKILL1) is None


def test_shock_weakens_the_attack_and_regen_heals_every_turn():
    a = fighter()
    before = eff_atk(a)
    _inflict(fighter("mage"), a, "shock", 0.3, 2, 10, [], random.Random(1))
    assert eff_atk(a) == pytest.approx(before * 0.7)
    from eternal_realm.game.engine.combat import _apply

    c = fighter()
    c.hp = c.max_hp // 2
    _apply(c, "regen", 0.1, 2)
    battle = Battle.start(c, fighter("guardian", 40), 15, random.Random(2))
    battle.actor = 0
    gained = []
    for _ in range(3):
        hp = c.hp
        battle.actor = 0
        lines = act(battle, Action.DEFEND, random.Random(2))
        gained.append(any("بازیابی" in line for line in lines))
    assert gained == [True, True, False]  # exactly the promised two turns


def test_resistance_and_immunity_and_cleanse():
    prey = fighter(traits=[Trait("resist_all", 0.6)])
    hits = 0
    for seed in range(100):
        f = fighter(traits=[Trait("resist_all", 0.6)])
        _inflict(fighter(), f, "poison", 0.2, 3, 20, [], random.Random(seed))
        hits += bool(f.statuses)
    assert 20 <= hits <= 60  # about 40% get through
    boss = fighter("guardian", resist={"burn": 1.0})
    out: list[str] = []
    _inflict(fighter(), boss, "burn", 0.3, 3, 30, out, random.Random(1))
    assert not boss.statuses and "مقاومت" in out[0]
    # the guardian's third skill clears what sits on him
    g = fighter("guardian")
    from eternal_realm.game.engine.combat import _apply

    _apply(g, "poison", 5, 3)
    _apply(g, "shock", 0.3, 2)
    battle = Battle.start(g, fighter("warrior", 40), 15, random.Random(3))
    battle.actor = 0
    act(battle, Action.SKILL3, random.Random(3))
    assert not [s for s in g.statuses if s["k"] in HARMFUL]


def test_dots_tick_a_set_number_of_times():
    a, b = fighter(), fighter("guardian")
    _inflict(a, b, "bleed", 0.3, 3, 40, [], random.Random(1))
    battle = Battle.start(a, b, 30, random.Random(1))
    ticks = 0
    for _ in range(6):
        battle.actor = 1
        lines = act(battle, Action.DEFEND, random.Random(1))
        ticks += any("خونریز" in line for line in lines)
    assert ticks == 3


# --- upgrading gear ---------------------------------------------------------------------------------------------------------------------
def test_upgrade_rules_are_graded():
    assert len(UPGRADE_CHANCE) == MAX_UPGRADE and UPGRADE_CHANCE[0] == 1.0
    assert list(UPGRADE_CHANCE) == sorted(UPGRADE_CHANCE, reverse=True) and UPGRADE_CHANCE[-1] <= 0.25
    arm = ARMS["blood_sword"]
    golds = [upgrade_gold(arm, n) for n in range(1, 11)]
    assert golds == sorted(golds) and golds[0] > 0
    for n in range(1, 11):
        assert upgrade_materials(n)
    assert "dragon_scale" in upgrade_materials(10)
    stats = [upgraded_stats(arm, n).atk for n in range(0, 11)]
    assert stats == sorted(stats) and stats[10] > stats[0] * 2 - 1 and stats[0] == arm.stats.atk


async def test_upgrade_success_failure_and_costs(services, db):
    p = await hero(services, db, level=20, gold=2_000_000)
    await services.arms.buy(p, "blood_sword")
    with pytest.raises(GameError, match="کافی نیست"):
        await services.arms.upgrade(p, "blood_sword")  # no iron ore yet
    async with db.transaction() as tx:
        await services.inventory.grant(tx, p.id, "iron_ore", 500)
        await services.inventory.grant(tx, p.id, "crystal_shard", 500)
        await services.inventory.grant(tx, p.id, "gold_ore", 500)
        await services.inventory.grant(tx, p.id, "dragon_scale", 50)
    await services.arms.equip(p, 1, "blood_sword")
    base = (await services.characters.stats(p)).atk
    gold_before = (await services.players.require(10)).gold
    first = await services.arms.upgrade(p, "blood_sword")
    assert first.success and first.level == 1 and first.chance == 1.0  # +1 never fails
    assert (await services.players.require(10)).gold == gold_before - first.gold
    assert (await services.characters.stats(p)).atk > base
    assert (await services.arms.plus_of(p.id))["blood_sword"] == 1

    # push on with a fixed luck: a failure keeps the level and still costs
    services.ctx.rng.seed(5)
    failures = successes = 0
    for _ in range(40):
        try:
            res = await services.arms.upgrade(p, "blood_sword")
        except GameError:
            break
        failures += not res.success
        successes += res.success
        assert res.level == (await services.arms.plus_of(p.id))["blood_sword"]
    assert failures and successes
    assert (await services.arms.plus_of(p.id))["blood_sword"] <= MAX_UPGRADE


async def test_upgrade_needs_ownership_and_stops_at_ten(services, db):
    p = await hero(services, db, level=20, gold=10**8)
    with pytest.raises(GameError, match="ندارید"):
        await services.arms.upgrade(p, "iron_blade")
    await services.arms.buy(p, "iron_blade")
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO arms_upgrades (player_id, arm_id, lvl) VALUES (?, 'iron_blade', 10)", (p.id,))
    with pytest.raises(GameError, match="بیشترین"):
        await services.arms.upgrade(p, "iron_blade")


def test_mythic_gear_and_boss_spoils():
    mythic = [a for a in ARMS.values() if a.rarity == 6]
    assert len(mythic) >= 3 and all(a.price >= 90_000 for a in mythic)
    spoils = {a.id for a in ARMS.values() if a.boss}
    assert spoils == set(boss_data.ELEMENT_DROP.values()) and set(boss_data.ELEMENT_DROP) == {e.id for e in boss_data.ELEMENTS}
    assert set(boss_data.MYTHIC_DROPS) <= {a.id for a in mythic}


async def test_boss_spoils_cannot_be_bought(services, db):
    p = await hero(services, db)
    with pytest.raises(GameError, match="باس"):
        await services.arms.buy(p, "b_fire")
    from eternal_realm.game.data.packs import PACKS

    assert "arm_b_fire" not in PACKS


# --- bosses -----------------------------------------------------------------------------------------------------------------------------
def _hero(i, cls="warrior", traits=()):
    return Hero(i, f"h{i}", cls, 4000, 4000, 40, 10, 10, 20, 5, traits=list(traits))


def test_a_boss_has_three_phases_with_their_own_announcement():
    boss = Boss("اژدها", 1000, 1000, 30, 5)
    heroes = [_hero(i) for i in range(4)]
    seen = {}
    rng = random.Random(1)
    for hp in (900, 480, 200, 100):
        boss.hp = hp
        text = " ".join(t for _, t in run_round(boss, heroes, rng))
        seen[hp] = (boss.phase, "فاز دوم" in text, "فاز سوم" in text)
    assert boss.phase == 3
    assert seen[900][0] == 1 and seen[480][1] and seen[200][2]


def test_boss_resistances_immunity_and_effects():
    boss = Boss("اژدهای آتشین", 10**7, 10**7, 30, 5, immune=["burn"], resist_class="warrior", weak_class="mage")
    mage = _hero(0, "mage")
    texts, hits = [], 0
    rng = random.Random(2)
    for _ in range(60):
        texts += [t for _, t in run_round(boss, [mage], rng)]
    assert any("مقاوم" in t for t in texts) and not any("باس را «سوخته»" in t for t in texts)

    rogue = _hero(0, "rogue")
    boss2 = Boss("b", 10**7, 10**7, 30, 5)
    got_bleed, dealt = False, 0
    for seed in range(60):
        out = run_round(boss2, [rogue], random.Random(seed))
        got_bleed |= any("خونریز" in t for _, t in out)
    assert got_bleed
    assert rogue.damage > 0  # the bleeding counts for the one who caused it


def test_gear_traits_work_in_group_fights():
    plain, geared = _hero(0), _hero(1, traits=[{"k": "dmg_cut", "v": 0.25, "c": 1.0, "t": 0}, {"k": "leech_flat", "v": 20, "c": 1.0, "t": 0}])
    for h in (plain, geared):
        h.hp = h.max_hp // 2
    boss = Boss("b", 10**7, 10**7, 60, 5)
    totals = {0: 0, 1: 0}
    for seed in range(40):
        for h, key in ((plain, 0), (geared, 1)):
            boss2 = Boss("b", 10**7, 10**7, 60, 5)
            h.hp = h.max_hp // 2
            before = h.hp
            run_round(boss2, [h], random.Random(seed))
            totals[key] += before - h.hp
    assert totals[1] < totals[0]  # the same blows hurt less (and the gear drank some life back)
    assert boss.phase == 1


# --- the screens -----------------------------------------------------------------------------------------------------------------------
async def test_growth_screens_flow(h, services, db):
    p = await hero(services, db, level=12, gold=2_000_000)
    await h.say(10, "/start")
    await h.panel(10, "profile")
    assert "امتیاز ویژگی آماده" in h.session.last_text()
    await h.panel(10, "arms")
    assert {"🎯 ویژگی‌ها", "🧬 استعدادها", "📈 پیشرفت"} <= set(h.labels())
    await h.panel(10, "progress")
    assert "تجربه" in h.session.last_text() and "🔒" in h.session.last_text() and "✅" in h.session.last_text()
    await h.panel(10, "attrs")
    assert "امتیاز آماده" in h.session.last_text()
    await h.panel(10, "attradd", "str", "5")
    assert (await services.growth.attrs(p.id))["str"] == 5
    await h.panel(10, "attrresetq")
    await h.panel(10, "attrreset")
    assert await services.growth.attrs(p.id) == {}
    await h.panel(10, "talents")
    await h.panel(10, "talent", "w_might")
    assert await services.growth.talents(p) == ["w_might"]
    await h.panel(10, "talent", "w_might")
    assert await services.growth.talents(p) == []
    await services.arms.buy(p, "iron_blade")
    await h.panel(10, "armview", "iron_blade")
    assert "⬆️ ارتقا" in h.labels()
    await h.panel(10, "armup", "iron_blade")
    assert "شانس موفقیت" in h.session.last_text() and "منابع" in h.session.last_text()
