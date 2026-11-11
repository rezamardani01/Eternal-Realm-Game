"""The pace of the game: how many days a player of each kind needs to reach the milestone levels.

A simple model of a day: so many calm activities, so many hunts and the three daily missions. The bands are wide on
purpose; they only guard against the curve becoming far too fast (a week to the top) or far too slow.
"""

from eternal_realm.config import Balance
from eternal_realm.game.data import monsters
from eternal_realm.game.data.activities import ACTIVITIES
from eternal_realm.game.engine import loot, progression


def days_to_reach(activities_a_day: int, hunts_a_day: int, targets: tuple[int, ...]) -> dict[int, int]:
    balance = Balance()
    level, xp, day, marks = 1, 0.0, 0, {}
    while level < max(targets) and day < 3000:
        day += 1
        per_activity = []
        for activity in ACTIVITIES.values():
            pool = [o for o in activity.outcomes if o.min_level <= level]
            total = sum(o.weight for o in pool)
            per_activity.append(sum(o.weight * (sum(o.xp) / 2) * loot.xp_scale(level) for o in pool) / total)
        band = [m for m in monsters.MONSTERS if m.min_level <= level <= m.max_level]
        hunt = sum(sum(m.xp) / 2 for m in band) / len(band) * loot.xp_scale(level)
        xp += activities_a_day * sum(per_activity) / len(per_activity) + hunts_a_day * hunt
        while level < max(targets) and xp >= progression.xp_needed(level, balance):
            xp -= progression.xp_needed(level, balance)
            level += 1
            if level in targets:
                marks[level] = day
    return marks


def test_a_regular_player_climbs_neither_too_fast_nor_too_slowly():
    marks = days_to_reach(60, 8, (5, 10, 20, 30, 50, 100))
    assert 1 <= marks[5] <= 4
    assert 4 <= marks[10] <= 12  # the first week
    assert 14 <= marks[20] <= 40  # about a month
    assert 35 <= marks[30] <= 80
    assert 90 <= marks[50] <= 200
    assert 280 <= marks[100] <= 600  # the top is a year-long road, not a week's


def test_a_casual_player_is_slower_but_still_moves_and_a_hardcore_one_is_faster():
    casual = days_to_reach(25, 4, (10, 30))
    hardcore = days_to_reach(110, 12, (10, 30))
    regular = days_to_reach(60, 8, (10, 30))
    assert hardcore[30] < regular[30] < casual[30]
    assert hardcore[30] >= 20  # even the keenest player needs weeks for level 30
    assert casual[10] <= 25  # and a casual one sees level 10 within a few weeks


def test_energy_costs_leave_room_for_the_daily_routine():
    balance = Balance()
    # a full bar plus a day of regeneration pays for the routine above (60 calm activities of ~6 energy, 8 hunts of 10)
    day_energy = progression.max_energy(10, balance) + 86400 // balance.energy_regen_seconds
    assert 60 * 6 + 8 * 10 <= day_energy
