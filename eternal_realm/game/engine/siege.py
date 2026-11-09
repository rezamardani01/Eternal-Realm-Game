"""The battle for a city, calculated on the server in a few phases (pure logic, deterministic per RNG).

Phase 1: traps and the guard tower thin out the attackers. Phase 2: three rounds of fighting between the
armies. Phase 3: whoever is still standing batters the buildings; the destruction is worked out building by
building, so the castle star really means the castle fell.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ...shared.text import fa
from ..data.city import (
    DEFAULT_HP_PER_LEVEL, DESTRUCTION_ORDER, HP_PER_LEVEL, TRAP_FIRES_PER_BATTLE, get_building, get_trap, get_troop,
)

ROUNDS = 3
SIEGE_ROUNDS = 3
TOWER_DAMAGE = 45


@dataclass
class Defence:
    troops: dict[str, int]
    traps: dict[str, int]
    levels: dict[str, int]
    name: str = ""


@dataclass
class Outcome:
    att_start: dict[str, int]
    att_alive: dict[str, int]
    def_start: dict[str, int]
    def_alive: dict[str, int]
    traps_used: dict[str, int]
    destruction: float = 0.0
    castle_down: bool = False
    stars: int = 0
    destroyed: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    @property
    def att_lost(self) -> dict[str, int]:
        return {k: v - self.att_alive.get(k, 0) for k, v in self.att_start.items() if v > self.att_alive.get(k, 0)}

    @property
    def def_lost(self) -> dict[str, int]:
        return {k: v - self.def_alive.get(k, 0) for k, v in self.def_start.items() if v > self.def_alive.get(k, 0)}


def building_hp(building_id: str, level: int) -> int:
    return level * HP_PER_LEVEL.get(building_id, DEFAULT_HP_PER_LEVEL)


def total_hp(levels: dict[str, int]) -> int:
    return sum(building_hp(b, lv) for b, lv in levels.items() if lv > 0)


def _hp_pool(units: dict[str, float]) -> float:
    return sum(q * get_troop(k).hp for k, q in units.items())


def _count(units: dict[str, float]) -> float:
    return sum(units.values())


def _thin(units: dict[str, float], damage: float) -> None:
    """Hurt every unit type alike: the share of the hit-point pool that was destroyed dies."""
    pool = _hp_pool(units)
    if pool <= 0 or damage <= 0:
        return
    keep = max(0.0, 1 - damage / pool)
    for k in units:
        units[k] *= keep


def _troop_damage(units: dict[str, float], bonus: float) -> float:
    return sum(q * get_troop(k).atk for k, q in units.items()) * bonus


def _cavalry_share(units: dict[str, float]) -> float:
    total = _count(units)
    return sum(q for k, q in units.items() if get_troop(k).cavalry) / total if total else 0.0


def _defence_value(units: dict[str, float]) -> float:
    return sum(q * get_troop(k).defense for k, q in units.items()) * 2


def simulate(
    attack: dict[str, int], defence: Defence, rng: random.Random, *, smithy: int = 0, commander: float = 0.0,
    attacker_name: str = "", attacker_hospital: int = 0,
) -> Outcome:
    att = {k: float(v) for k, v in attack.items() if v > 0}
    dfn = {k: float(v) for k, v in defence.troops.items() if v > 0}
    att0, dfn0 = {k: int(v) for k, v in att.items()}, {k: int(v) for k, v in dfn.items()}
    levels = {b: lv for b, lv in defence.levels.items() if lv > 0}
    wall, tower, hospital = levels.get("wall", 0), levels.get("tower", 0), levels.get("hospital", 0)
    bonus = 1 + 0.03 * smithy + commander
    out = Outcome(att0, {}, dfn0, {}, {})
    log = out.log
    city = defence.name or "شهر دشمن"
    log.append(f"🚩 لشکر {attacker_name or 'مهاجم'} با {fa(sum(att0.values()))} نفر به دیوارهای {city} رسید.")

    # phase 1: traps and the guard tower
    trap_damage = 0.0
    for trap_id, charges in sorted(defence.traps.items()):
        fired = min(charges, TRAP_FIRES_PER_BATTLE)
        if fired > 0:
            trap_damage += fired * get_trap(trap_id).damage * rng.uniform(0.9, 1.1)
            out.traps_used[trap_id] = fired
    if trap_damage:
        before = _count(att)
        _thin(att, trap_damage)
        log.append(f"🪤 تله‌های شهر کار کردند و {fa(round(before - _count(att)))} مهاجم را از پا انداختند.")
    else:
        log.append("🪤 شهر تله‌ای نداشت و لشکر بی‌گزند پیش رفت.")

    # phase 2: the armies clash
    for number in range(1, ROUNDS + 1):
        if _count(att) < 0.5:
            break
        spear_bonus = 1 + 0.6 * _cavalry_share(att) * (dfn.get("spear", 0) / max(1.0, _count(dfn))) if dfn else 1.0
        hit_on_defenders = _troop_damage(att, bonus) * rng.uniform(0.9, 1.1)
        hit_on_attackers = (_troop_damage(dfn, 1.0) * spear_bonus + tower * TOWER_DAMAGE) * rng.uniform(0.9, 1.1)
        shield_def = _defence_value(dfn)
        shield_att = _defence_value(att)
        dead_d = hit_on_defenders * _hp_pool(dfn) / (_hp_pool(dfn) + shield_def) if dfn else 0.0
        dead_a = hit_on_attackers * _hp_pool(att) / (_hp_pool(att) + shield_att)
        before_a, before_d = _count(att), _count(dfn)
        _thin(dfn, dead_d)
        _thin(att, dead_a)
        log.append(
            f"⚔️ دور {fa(number)}: {fa(round(before_d - _count(dfn)))} مدافع و "
            f"{fa(round(before_a - _count(att)))} مهاجم کشته شدند."
        )
        if _count(dfn) < 0.5 and dfn:
            dfn = {k: 0.0 for k in dfn}
            log.append("🛡️ مدافعان شهر از پا درآمدند و راه دروازه باز شد.")
            break

    # phase 3: the siege of the buildings
    guard = (_count(dfn) / sum(dfn0.values())) if dfn0 else 0.0
    siege_units = {k: q for k, q in att.items() if get_troop(k).siege}
    towers = att.get("tower_siege", 0)
    wall_eff = wall * (0.6 if towers >= 1 else 1.0)
    structure = 0.0
    for k, q in att.items():
        t = get_troop(k)
        factor = 1 / (1 + 0.05 * wall_eff) if t.siege else 1 / (1 + 0.20 * wall_eff)
        structure += q * t.struct * factor * bonus
    structure *= (1 - 0.6 * guard) * SIEGE_ROUNDS * rng.uniform(0.92, 1.08)
    total = total_hp(levels)
    remaining, destroyed, castle_down = structure, [], False
    for b in DESTRUCTION_ORDER:
        lv = levels.get(b, 0)
        if lv <= 0:
            continue
        hp = building_hp(b, lv)
        if remaining >= hp:
            remaining -= hp
            destroyed.append(b)
            if b == "castle":
                castle_down = True
        else:
            break
    damage_done = min(total, structure)
    out.destruction = (damage_done / total) if total else 0.0
    out.destroyed, out.castle_down = destroyed, castle_down
    if wall:
        log.append(
            ("🐏 ماشین‌های محاصره دیوار را شکافتند." if siege_units else "🧱 دیوار شهر پیاده‌ها را دیر به پیش می‌برد.")
        )
    if destroyed:
        names = "، ".join(get_building(b).name for b in destroyed[:4])
        log.append(f"🔥 {names}{' و ...' if len(destroyed) > 4 else ''} ویران شد.")
    log.append(f"📊 میزان تخریب شهر: {fa(round(out.destruction * 100))}٪")

    # losses: the hospital heals part of the dead
    out.att_alive = _round_survivors(att0, att, attacker_hospital)
    out.def_alive = _round_survivors(dfn0, dfn, hospital)
    out.stars = (out.destruction >= 0.5) + castle_down + (out.destruction >= 0.9)
    return out


def _round_survivors(start: dict[str, int], alive: dict[str, float], hospital: int) -> dict[str, int]:
    heal = min(0.5, 0.05 * hospital)
    result = {}
    for k, v in start.items():
        dead = v - alive.get(k, 0.0)
        saved = dead * heal
        result[k] = min(v, max(0, round(alive.get(k, 0.0) + saved)))
    return result
