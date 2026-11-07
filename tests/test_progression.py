from eternal_realm.game.data.classes import CLASSES
from eternal_realm.game.data.races import RACES
from eternal_realm.game.engine import progression as p


def test_xp_curve_and_levelup(balance):
    assert p.xp_needed(1, balance) == 100
    level, xp, gained = p.apply_xp(1, 0, 100, balance)
    assert (level, xp, gained) == (2, 0, 1)
    level, xp, gained = p.apply_xp(1, 50, 5000, balance)
    assert gained >= 3 and level == 1 + gained


def test_level_cap(balance):
    level, xp, _ = p.apply_xp(balance.max_level, 0, 10**9, balance)
    assert (level, xp) == (balance.max_level, 0)


def test_energy_regeneration(balance):
    cap = p.max_energy(1, balance)
    energy, at = p.regen_energy(10, 1000, 1000 + balance.energy_regen_seconds * 3 + 5, 1, balance)
    assert energy == 13
    assert at == 1000 + balance.energy_regen_seconds * 3
    assert p.regen_energy(10, 0, 10**9, 1, balance)[0] == cap


def test_every_race_and_class_has_valid_stats():
    for race in RACES:
        for cls in CLASSES:
            low, high = p.base_stats(race, cls, 1), p.base_stats(race, cls, 50)
            assert low.hp > 0 and low.atk > 0 and low.defense > 0
            assert high.hp > low.hp and high.speed >= low.speed


def test_no_race_dominates_every_stat():
    def power(stats):  # hp points are worth far less than one point of another stat
        d = stats.as_dict()
        return d["hp"] / 5 + sum(v for k, v in d.items() if k != "hp")

    scores = {r.id: power(r.stats) for r in RACES.values()}
    assert max(scores.values()) - min(scores.values()) <= 8
