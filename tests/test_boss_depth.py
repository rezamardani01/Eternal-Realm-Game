import random

from eternal_realm.game.data.bosses import BOSSES, behavior_of
from eternal_realm.game.engine.boss_fight import Boss, Hero, run_round


def hero(pid, cls, hp=500, **kw):
    return Hero(pid, f"h{pid}", cls, hp, hp, 30, 5, 30, 10, 5, **kw)


def texts(events):
    return " ".join(t for _, t in events)


def test_boss_enters_phase_two_once_below_half_health():
    boss = Boss("b", 1000, 1000, 10, 5)
    team = [hero(1, "warrior", 10**6)]
    boss.hp = 400
    out = texts(run_round(boss, team, random.Random(1)))
    assert boss.phase == 2 and "فاز دوم" in out
    again = texts(run_round(boss, team, random.Random(2)))
    assert "فاز دوم" not in again


def test_hunter_boss_picks_the_weakest_hero():
    from eternal_realm.game.engine.boss_fight import _boss_single

    boss = Boss("b", 10**9, 10**9, 50, 5, behavior="hunter")
    weak, strong = hero(1, "rogue", 100), hero(2, "warrior", 100)
    weak.hp = 20
    rng = random.Random(3)
    for _ in range(20):
        weak.hp, weak.alive = 20, True
        assert strong.name not in texts(_boss_single(boss, [weak, strong], rng))


def test_healer_boss_mends_itself_at_most_three_times():
    boss = Boss("b", 10**6, 10**6, 1, 5, behavior="healer")
    boss.hp = 5 * 10**5
    team = [hero(1, "warrior", 10**9)]
    healed = 0
    for _ in range(30):
        healed += "زخم‌هایش را بست" in texts(run_round(boss, team, random.Random(_)))
    assert healed == 3


def test_mage_or_guardian_can_raise_a_fallen_friend_once():
    rng = random.Random(7)
    boss = Boss("b", 10**9, 10**9, 1, 5)
    mage, fallen = hero(1, "mage"), hero(2, "warrior")
    fallen.alive, fallen.hp = False, 0
    for _ in range(200):
        run_round(boss, [mage, fallen], rng)
        if fallen.alive:
            break
    assert fallen.alive and mage.revive == 0 and fallen.hp > 0


def test_warrior_pins_the_boss_and_mage_profits():
    rng = random.Random(11)
    boss = Boss("b", 10**9, 10**9, 1, 5)
    team = [hero(1, "warrior"), hero(2, "mage")]
    seen = ""
    for _ in range(100):
        seen += texts(run_round(boss, team, rng))
    assert "مهار کرد" in seen and "طلسم ترکیبی" in seen


def test_every_boss_has_a_behaviour_line():
    assert all(behavior_of(b)[0] in ("normal", "hunter", "healer", "berserk") and behavior_of(b)[1] for b in BOSSES)
