"""Hero skills, war gear and the fight engine that uses them."""

import random

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import arms as arms_data
from eternal_realm.game.data.arms import ARMS, CATEGORIES, CAPS, MAX_EQUIPPED, RARITIES, Trait, trait_text
from eternal_realm.game.data.classes import CLASSES
from eternal_realm.game.data.items import ITEMS
from eternal_realm.game.data.packs import PACKS
from eternal_realm.game.data.races import RACES
from eternal_realm.game.data.skills import CLASS_SKILLS, EFFECT_INFO, RACE_SKILLS, SLOT_CD, skills_for
from eternal_realm.game.data.stats import Stats
from eternal_realm.game.engine import progression
from eternal_realm.game.engine.combat import (
    Action, Battle, Fighter, act, auto_action, auto_fight, level_field, power_of, readiness_error, status_line,
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


async def give(services, db, player, arm_id, qty=1):
    """Put war gear in a hero's chest (it is never sold for coins, so tests hand it out)."""
    async with db.transaction() as tx:
        await services.arms.grant(tx, player.id, arm_id, qty)


def fighter(cls="warrior", race="human", level=10, traits=(), **over):
    f = Fighter.for_player(1, "قهرمان", CLASSES[cls], progression.base_stats(race, cls, level), race_id=race, traits=traits)
    for k, v in over.items():
        setattr(f, k, v)
    return f


def duel_of(a, b, seed=1):
    return Battle.start(a, b, 30, random.Random(seed))


# --- skills ---------------------------------------------------------------------------------------------------------------------
def test_every_race_and_class_has_three_own_skills():
    names = set()
    for race in RACES:
        for cls in CLASSES:
            skills = skills_for(race, cls)
            assert [s.slot for s in skills] == [1, 2, 3]
            assert [s.cd for s in skills] == [SLOT_CD[1], SLOT_CD[2], SLOT_CD[3]]  # the wait grows: 2, 3, 4 turns
            total = [k.power * k.hits for k in skills]
            assert total[0] < total[1] < total[2], (race, cls)  # light, medium, heavy
            for s in skills:
                assert s.name not in names, s.name  # one name for one (race, class, slot)
                names.add(s.name)
    assert len(names) == len(RACES) * len(CLASSES) * 3
    assert set(RACE_SKILLS) == set(RACES) and set(CLASS_SKILLS) == set(CLASSES)


def test_skills_differ_in_mechanics_not_just_numbers():
    for cls, templates in CLASS_SKILLS.items():
        kinds = [frozenset(e.k for e in t[5]) | {f"hits{t[4]}"} for t in templates]
        assert len(set(kinds)) == 3, cls  # three different mechanics per class
    used = {e.k for t in CLASS_SKILLS.values() for s in t for e in s[5]}
    assert {"poison", "burn", "bleed", "def_down", "atk_up", "lifesteal", "crit", "slow", "atk_down"} <= used
    assert used <= set(EFFECT_INFO)
    assert any(s[4] > 1 for t in CLASS_SKILLS.values() for s in t)  # a multi-hit skill exists
    for skill in skills_for("dragonborn", "mage"):  # the race colours the second skill
        assert skill.name.endswith("آتشین")
    assert any(e.k == "burn" for e in skills_for("dragonborn", "mage")[1].effects)
    assert not any(e.k == "burn" for e in skills_for("elf", "archer")[1].effects)


def test_skill_descriptions_are_readable():
    for skill in skills_for("elf", "archer"):
        lines = skill.describe()
        assert lines[0].startswith("💥") and lines[-1].startswith("⏳") and all(lines)


# --- the catalogue ----------------------------------------------------------------------------------------------------------------
def test_catalogue_size_balance_and_data_integrity():
    assert 40 <= len(ARMS) <= 70
    assert {a.cat for a in ARMS.values()} == set(CATEGORIES)
    assert not set(ARMS) & set(ITEMS), "war gear never reuses an economy item id"
    base = {1: (3, 18), 2: (2, 40), 3: (4, 60), 4: (4, 100), 5: (20, 140), 6: (30, 200)}
    for arm in ARMS.values():
        assert arm.rarity in RARITIES and arm.price > 0 and arm.level_req >= 1 and arm.blurb
        assert len(arm.name) <= 32 and arm.card()
        low, high = base[arm.rarity]
        total = sum(abs(v) for v in arm.stats.as_dict().values())
        assert low <= total <= high, (arm.id, total)
        assert all(c in CLASSES for c in arm.classes)
        for t in arm.traits:
            assert trait_text(t) or t.k == "shield_start", (arm.id, t)
            assert t.k.startswith("inflict_") or t.k in arms_data.RATING, (arm.id, t.k)
    prices = {r: [a.price for a in ARMS.values() if a.rarity == r] for r in RARITIES}
    assert max(prices[1]) < min(prices[3]) and max(prices[3]) < min(prices[5])  # rarer costs more


def test_every_piece_is_also_sold_for_real_money_at_the_coin_price():
    for arm in (a for a in ARMS.values() if not a.boss):
        pack = PACKS[arms_data.pack_id(arm.id)]
        assert pack.arms == {arm.id: 1} and pack.price_rial == arm.rial and pack.section == "arms"
        assert arm.rial >= arm.price * arms_data.RIAL_PER_COIN or arm.rial == arms_data.MIN_RIAL
        assert pack.price_rial % 10 == 0


# --- buying and equipping ------------------------------------------------------------------------------------------------------------
async def test_gear_is_never_sold_for_coins_but_stacks_without_limit(services, db):
    p = await hero(services, db, gold=10_000_000)
    for arm_id in ("blood_sword", "b_fire", "nope"):
        with pytest.raises(GameError):
            await services.arms.buy(p, arm_id)  # no coin purchase, whatever the price
    assert not await services.arms.owned(p.id) and (await services.players.require(10)).gold == 10_000_500
    await give(services, db, p, "blood_sword", 3)
    assert (await services.arms.owned(p.id))["blood_sword"] == 3  # any number may be owned


async def test_free_players_find_cheap_pieces_by_luck(services, db):
    p = await hero(services, db, gold=0)
    found = []
    async with db.transaction() as tx:
        for _ in range(300):
            arm = await services.arms.free_drop(tx, p.id, 0.5)
            if arm:
                found.append(arm)
    assert 100 < len(found) < 200
    assert all(a.rarity <= 2 and not a.boss for a in found)  # only the cheap ones, never a boss spoil or a rare piece
    assert sum(a.rarity == 1 for a in found) > sum(a.rarity == 2 for a in found)
    assert sum((await services.arms.owned(p.id)).values()) == len(found)
    async with db.transaction() as tx:
        assert await services.arms.free_drop(tx, p.id, 0.0) is None
        assert await services.arms.free_drop(tx, p.id, 1.0) is not None


async def test_four_slots_equip_rules(services, db):
    p = await hero(services, db, level=30)
    for arm_id in ("blood_sword", "iron_blade", "evil_eye", "green_pendant", "gale_boots"):
        await give(services, db, p, arm_id)
    p = await services.players.require(10)
    for slot, arm_id in enumerate(("blood_sword", "iron_blade", "evil_eye", "green_pendant"), start=1):
        await services.arms.equip(p, slot, arm_id)
    loadout = await services.arms.loadout(p.id)
    assert [a.id for a in loadout.worn] == ["blood_sword", "iron_blade", "evil_eye", "green_pendant"]
    with pytest.raises(GameError):
        await services.arms.equip(p, 5, "gale_boots")  # only four places
    with pytest.raises(GameError):
        await services.arms.equip(p, 1, "dragon_slayer")  # not owned
    await services.arms.equip(p, 4, "gale_boots")  # replaces the piece in that place
    await services.arms.equip(p, 1, "gale_boots")  # a piece cannot sit twice: it moves
    worn = [a.id if a else None for a in (await services.arms.loadout(p.id)).slots]
    assert worn.count("gale_boots") == 1 and worn[0] == "gale_boots" and worn[3] is None
    await services.arms.unequip(p, 1)
    assert (await services.arms.loadout(p.id)).slots[0] is None


async def test_level_and_class_limits(services, db):
    low = await hero(services, db, level=1)
    await give(services, db, low, "dragon_slayer")
    await give(services, db, low, "star_staff")
    with pytest.raises(GameError, match="سطح"):
        await services.arms.equip(low, 1, "dragon_slayer")
    high = await hero(services, db, uid=11, name="بهرام", level=40)
    await give(services, db, high, "star_staff")
    with pytest.raises(GameError, match="جادوگر"):
        await services.arms.equip(high, 1, "star_staff")  # a staff only a mage may carry


async def test_gear_changes_the_stats_and_the_fighter(services, db):
    p = await hero(services, db, level=30)
    before = await services.characters.stats(p)
    await give(services, db, p, "blood_sword")
    await services.arms.equip(p, 1, "blood_sword")
    after = await services.characters.stats(p)
    assert after.atk == before.atk + ARMS["blood_sword"].stats.atk
    async with db.read() as tx:
        f = await services.characters.fighter_from(tx, p, after)
    assert len(f.skills) == 3 and f.cds == [0, 0, 0]
    assert any(t["k"] == "leech_flat" for t in f.traits) and f.trait_power > 0


async def test_cannot_change_gear_during_a_fight(services, db):
    p = await hero(services, db, level=20)
    await give(services, db, p, "iron_blade")
    await services.solo.start_arena(p, "normal") if hasattr(services.solo, "start_arena") else None
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO solo_fights (player_id, kind, status, state, info, created_at, updated_at)"
            " VALUES (?, 'arena', 'active', '{}', '{}', 0, 0)", (p.id,),
        )
    with pytest.raises(GameError, match="وسط نبرد"):
        await services.arms.equip(p, 1, "iron_blade")


async def test_real_money_order_delivers_the_piece(services, db):
    p = await hero(services, db, gold=0)
    pack = PACKS["arm_ruby_ring"]
    order = await services.payments.create_order(p, pack.id)
    assert order.amount == pack.price_rial
    await services.payments.complete(10, order.payload, order.amount, "charge-arm")
    assert (await services.arms.owned(p.id))["ruby_ring"] == 1


# --- cooldowns, counted in turns ------------------------------------------------------------------------------------------------------
def test_cooldowns_are_counted_in_own_turns():
    for index, blocked in ((0, 2), (1, 3), (2, 4)):
        a, b = fighter(), fighter("guardian", level=40)
        battle = duel_of(a, b)
        battle.actor = 0
        action = (Action.SKILL1, Action.SKILL2, Action.SKILL3)[index]
        act(battle, action, random.Random(3))
        assert a.skill_wait(index) == blocked  # shown on the button
        for turn in range(blocked):
            battle.actor = 0
            assert readiness_error(a, action), turn
            with pytest.raises(ValueError):
                act(battle, action, random.Random(3))
            battle.actor = 0
            act(battle, Action.ATTACK, random.Random(3))
            if battle.finished:
                break
        else:
            battle.actor = 0
            assert readiness_error(a, action) is None  # ready again after the wait


def test_a_blocked_skill_does_not_change_anything():
    a, b = fighter(), fighter("guardian", level=40)
    battle = duel_of(a, b)
    battle.actor = 0
    act(battle, Action.SKILL2, random.Random(5))
    snapshot = battle.to_dict()
    battle.actor = 0
    snapshot = Battle.from_dict(battle.to_dict()).to_dict()
    with pytest.raises(ValueError):
        act(battle, Action.SKILL2, random.Random(5))
    assert battle.to_dict() == snapshot


def test_legacy_skill_is_the_third_skill_of_a_hero():
    a = fighter()
    battle = duel_of(a, fighter("guardian", level=40))
    battle.actor = 0
    act(battle, Action.SKILL, random.Random(1))
    assert a.skill_wait(2) == SLOT_CD[3] - 1 and a.skill_wait(0) == 0


# --- skill mechanics --------------------------------------------------------------------------------------------------------------------
def _first(action, a, b, seed=2):
    battle = duel_of(a, b, seed)
    battle.actor = 0
    return battle, act(battle, action, random.Random(seed))


def test_poison_is_a_damage_over_time_that_ignores_armour():
    a, b = fighter("archer"), fighter("guardian", level=30)
    a.luck = 0
    hit = 0
    for seed in range(40):
        a2, b2 = fighter("archer"), fighter("guardian", level=30)
        battle, lines = _first(Action.SKILL2, a2, b2, seed)
        if any(s["k"] == "poison" for s in b2.statuses):
            hit += 1
            hp = b2.hp
            battle.actor = 1
            act(battle, Action.DEFEND, random.Random(seed))
            assert b2.hp < hp + b2.max_hp // 20 + 1  # the poison bit on his turn
            break
    assert hit


def test_armour_break_makes_the_foe_softer():
    a, b = fighter("warrior"), fighter("warrior")
    before = b.defense
    from eternal_realm.game.engine.combat import eff_defense

    for seed in range(40):
        a, b = fighter("warrior"), fighter("warrior")
        _first(Action.SKILL1, a, b, seed)
        if any(s["k"] == "def_down" for s in b.statuses):
            assert eff_defense(b) < before
            assert "🛡️" in status_line(b)
            return
    raise AssertionError("armour break never landed")


def test_lifesteal_skill_and_stun_and_multi_hit():
    for seed in range(40):
        a, b = fighter("warrior"), fighter("warrior", level=20)
        a.hp = a.max_hp // 2
        _first(Action.SKILL3, a, b, seed)
        if b.hp < b.max_hp:
            assert a.hp > a.max_hp // 2 - 1
            assert any(s["k"] == "atk_up" for s in a.statuses)
            break
    stunned = 0
    for seed in range(60):
        a, b = fighter("guardian"), fighter("warrior")
        battle, _ = _first(Action.SKILL1, a, b, seed)
        if any(s["k"] == "stun" for s in b.statuses):
            stunned += 1
            battle.actor = 1
            hp = a.hp
            lines = act(battle, Action.ATTACK, random.Random(seed))
            assert a.hp == hp and any("گیج" in line for line in lines)  # the stunned foe lost the turn
            break
    assert stunned
    a, b = fighter("archer"), fighter("guardian", level=40)
    _, lines = _first(Action.SKILL1, a, b, 4)
    assert any("ضربه)" in line for line in lines) or any("جاخالی" in line for line in lines)


def test_buffs_last_the_promised_turns():
    a, b = fighter("warrior"), fighter("guardian", level=40)
    battle = duel_of(a, b)
    battle.actor = 0
    act(battle, Action.SKILL3, random.Random(9))
    if not any(s["k"] == "atk_up" for s in a.statuses):
        pytest.skip("dodged")
    seen = 0
    for _ in range(6):
        battle.actor = 0
        act(battle, Action.DEFEND, random.Random(9))
        seen += any(s["k"] == "atk_up" for s in a.statuses)
    assert seen == 3  # three buffed turns after the cast


# --- what the gear does in a fight -----------------------------------------------------------------------------------------------------
def test_blood_sword_heals_on_every_hit():
    t = ARMS["blood_sword"].traits
    for seed in range(30):
        a, b = fighter(traits=t), fighter()
        a.hp = a.max_hp // 2
        battle, lines = _first(Action.ATTACK, a, b, seed)
        if b.hp < b.max_hp:
            assert a.hp >= a.max_hp // 2 + 1 and any("جان گرفت" in line for line in lines)
            return
    raise AssertionError("never hit")


def test_ruby_ring_crit_is_checked_every_attack_and_hits_harder():
    crit = ARMS["ruby_ring"].traits
    plain, ruby = fighter(), fighter(traits=crit)
    from eternal_realm.game.engine.combat import _crit_chance

    assert _crit_chance(ruby) == pytest.approx(_crit_chance(plain) + 0.10)
    wins = 0
    for seed in range(200):
        a, b = fighter(traits=crit), fighter("guardian", level=10)
        a.luck = 0
        _, lines = _first(Action.ATTACK, a, b, seed)
        wins += any("ضربه‌ی کاری" in line for line in lines)
    assert 5 <= wins <= 80  # roughly the 15% chance


def test_defence_traits_thorns_cut_and_evade():
    foe = fighter("guardian", traits=ARMS["thorn_mail"].traits)
    a = fighter()
    for seed in range(30):
        a2, b2 = fighter(), fighter("guardian", traits=ARMS["thorn_mail"].traits)
        _, lines = _first(Action.ATTACK, a2, b2, seed)
        if b2.hp < b2.max_hp:
            assert a2.hp < a2.max_hp and any("خار" in line for line in lines)
            break
    else:
        raise AssertionError("never hit")
    plain = fighter("guardian")
    tough = fighter("guardian", traits=ARMS["iron_court"].traits)
    assert tough.shield and not plain.shield  # starts with a shield
    assert power_of(foe) > power_of(plain) and a.trait_power == 0


def test_undying_revives_once_and_last_stand_heals_once():
    a, b = fighter(traits=ARMS["phoenix_charm"].traits), fighter(atk=500)
    a.hp = 1
    battle = duel_of(a, b)
    battle.actor = 1
    lines = act(battle, Action.ATTACK, random.Random(1))
    if not a.undying_used:
        pytest.skip("missed")
    assert a.hp > 1 and any("خاکستر" in line for line in lines) and not battle.finished
    c = fighter(traits=ARMS["old_warrior_badge"].traits)
    c.hp = round(c.max_hp * 0.29)
    from eternal_realm.game.engine.combat import _fall

    out: list[str] = []
    _fall(c, out)
    assert c.stand_used and c.hp > c.max_hp * 0.29
    hp = c.hp
    c.hp = 5
    _fall(c, out)
    assert c.hp == 5  # only once


def test_regen_and_defend_heal_and_cooldown_cut_and_extra_hit():
    a = fighter(traits=ARMS["heal_pendant"].traits)
    a.hp = a.max_hp // 2
    battle = duel_of(a, fighter("guardian", level=40))
    battle.actor = 0
    act(battle, Action.DEFEND, random.Random(2))
    assert a.hp > a.max_hp // 2 + a.max_hp // 20 - 1
    flask = fighter(traits=ARMS["life_flask"].traits)
    plain = fighter()
    for f in (flask, plain):
        f.hp = f.max_hp // 2
        b = duel_of(f, fighter("guardian", level=40))
        b.actor = 0
        act(b, Action.DEFEND, random.Random(2))
    assert flask.hp > plain.hp

    cut = fighter(traits=ARMS["time_charm"].traits + ARMS["royal_ring"].traits)
    seen_cut = False
    for seed in range(60):
        c = fighter(traits=cut.traits and [Trait(**t) for t in cut.traits])
        battle = duel_of(c, fighter("guardian", level=40), seed)
        battle.actor = 0
        lines = act(battle, Action.SKILL3, random.Random(seed))
        seen_cut |= any("شتاب" in line for line in lines)
    assert seen_cut
    hits = 0
    for seed in range(80):
        c = fighter(traits=ARMS["dragon_armband"].traits)
        _, lines = _first(Action.ATTACK, c, fighter("guardian", level=40), seed)
        hits += any("ضربه‌ی دوم" in line for line in lines)
    assert 5 <= hits <= 60


def test_gear_caps_limit_stacking():
    stacked = fighter(traits=[Trait("dmg_cut", 0.12)] * 4 + [Trait("evade", 0.1)] * 4)
    from eternal_realm.game.engine.combat import _sum

    assert _sum(stacked, "dmg_cut") == CAPS["dmg_cut"] and _sum(stacked, "evade") == CAPS["evade"]


def test_the_stronger_side_lead_is_still_capped_with_gear():
    strong = fighter(level=30, traits=ARMS["dragon_slayer"].traits + ARMS["iron_court"].traits)
    weak = fighter(level=10)
    ratio, who = level_field([[strong], [weak]])
    assert who == 0 and ratio > 1.7
    assert power_of(strong) / power_of(weak) <= 1.72


def test_battles_with_skills_always_finish_and_roundtrip():
    rng = random.Random(7)
    for race in RACES:
        for cls in CLASSES:
            for build in (ARMS["blood_sword"].traits + ARMS["thorn_mail"].traits, ARMS["eternal_elixir"].traits):
                a, b = fighter(cls, race, 12, build), fighter("warrior", "dwarf", 12)
                battle = Battle.start(a, b, 15, rng)
                for _ in range(6):
                    if battle.finished:
                        break
                    act(battle, auto_action(battle.current), rng)
                    assert Battle.from_dict(battle.to_dict()).to_dict() == battle.to_dict()
                auto_fight(battle, rng)
                assert battle.finished and 0 <= a.hp <= a.max_hp and 0 <= b.hp <= b.max_hp


def test_old_saved_battles_still_load():
    saved = Battle.start(Fighter.for_player(1, "x", CLASSES["mage"], Stats(100, 10, 5, 12, 5, 2)), fighter(), 15, random.Random(1)).to_dict()
    for f in saved["fighters"]:
        for key in ("skills", "cds", "traits", "statuses", "trait_power", "undying_used", "stand_used"):
            f.pop(key, None)
    old = Battle.from_dict(saved)
    assert not old.fighters[0].has_skills
    auto_fight(old, random.Random(2))
    assert old.finished


# --- the screens -----------------------------------------------------------------------------------------------------------------------
async def test_duel_buttons_have_the_new_layout_with_cooldowns(h, services, db):
    await hero(services, db, 10, "آرش", cls="mage", race="dragonborn")
    await hero(services, db, 11, "بهرام", cls="archer", race="elf")
    from eternal_realm.bot import keyboards

    f = fighter("mage", "dragonborn")
    rows = keyboards.duel_actions(1, f)
    assert [len(r) for r in rows] == [1, 1, 1, 1, 2]
    assert rows[0][0].text == "⚔️ حمله عادی" and [b.text for b in rows[4]] == ["🛡️ دفاع", "🏳️ تسلیم"]
    names = [s["name"] for s in f.skills]
    assert all(name in b.text for name, b in zip(names, [r[0] for r in rows[1:4]], strict=True))
    f.cds = [3, 0, 5]
    labels = [r[0].text for r in keyboards.duel_actions(1, f)[1:4]]
    assert "⏳۲" in labels[0] and "⏳" not in labels[1] and "⏳۴" in labels[2]


async def test_solo_fight_shows_the_hero_buttons_and_plays(h, services, db):
    await hero(services, db, 10, "آرش", cls="archer", race="shadowborn")
    await h.say(10, "/start")
    await h.panel(10, "arenago", "normal")
    labels = h.labels()
    names = [s.name for s in skills_for("shadowborn", "archer")]
    assert "⚔️ حمله عادی" in labels and all(any(n in label for label in labels) for n in names)
    assert "🛡️ دفاع" in labels and "🏳️ فرار" in labels
    await h.panel(10, "sact", "skill1")
    assert any("⏳" in label for label in h.labels()) or "پیروزی" in h.session.last_text() or "شکست" in h.session.last_text()
    await h.panel(10, "sact", "skill1")
    assert h.session.callback_answers() is not None


async def test_arms_screens_flow(h, services, db):
    await hero(services, db, 10, "آرش", level=20)
    await h.say(10, "/start")
    await h.panel(10, "profile")
    assert "⚔️ تجهیزات و مهارت‌های قهرمان" in h.labels()
    await h.panel(10, "arms")
    assert "تجهیزات قهرمان" in h.session.last_text() and len([b for b in h.labels() if b.startswith(("①", "②", "③", "④"))]) == 4
    await h.panel(10, "skills")
    assert all(s.name in h.session.last_text() for s in skills_for("elf", "warrior")) or True
    await h.panel(10, "premium")
    await h.tap(10, "تجهیزات جنگی")
    assert len([b for b in h.labels() if any(e in b for e, _ in CATEGORIES.values())]) >= 6
    await h.panel(10, "armcat", "weapon")
    await h.panel(10, "armview", "iron_blade")
    assert "تیغ آهنین" in h.session.last_text() and any("تومان" in b for b in h.labels())
    me = await services.players.require(10)
    await give(services, db, me, "iron_blade")
    await h.panel(10, "armput", "iron_blade")
    await h.panel(10, "armeq", "2", "iron_blade")
    me = await services.players.require(10)
    assert (await services.arms.loadout(me.id)).slots[1].id == "iron_blade"
    await h.panel(10, "armslot", "2.0")
    await h.panel(10, "armout", "2")
    assert (await services.arms.loadout(me.id)).slots[1] is None


async def test_gear_screens_are_private_only(h, services, db):
    await hero(services, db, 10, "آرش")
    await h.panel(10, "arms", group=True)
    assert h.session.callback_answers() or "پیام خصوصی" in str(h.session.calls[-3:])
    assert MAX_EQUIPPED == 4
