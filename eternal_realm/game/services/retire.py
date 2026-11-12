"""One-time retirement of the old gear system.

Before the war-gear update heroes carried swords, shields, helmets, armour, boots, rings and amulets from the old
catalogue. That system is gone (war gear replaced it), so every old piece still sitting in a hero's chest is turned into
coins, at the value it had (with its upgrades), and the piece is removed. Running it again finds nothing to do.
"""

from __future__ import annotations

from ...db.database import Database
from ...db.repos import wallet

#: what each old piece was worth in coins (its shop price, or a fair value for the ones only the forge or a boss made)
LEGACY_VALUE: dict[str, int] = {
    "wooden_sword": 150, "iron_sword": 900, "steel_sword": 3200, "fire_sword": 30_000, "short_bow": 160,
    "hunter_bow": 3000, "dagger": 150, "shadow_dagger": 15_000, "wooden_staff": 160, "crystal_staff": 4500,
    "rusty_sword": 300, "broad_sword": 1800, "knight_sword": 7500, "battle_axe": 3800, "war_hammer": 8200,
    "long_bow": 1500, "elven_bow": 7800, "twin_daggers": 3400, "assassin_blade": 7200, "oak_staff": 1600,
    "sage_staff": 3600, "storm_staff": 8000, "wooden_shield": 140, "iron_shield": 850, "bronze_shield": 1300,
    "tower_shield": 3300, "knight_shield": 7000, "leather_cap": 120, "iron_helm": 800, "bronze_helm": 1100,
    "steel_helm": 2900, "knight_helm": 6500, "leather_armor": 260, "chain_mail": 2600, "padded_armor": 600,
    "bronze_armor": 1700, "steel_armor": 4200, "knight_armor": 9000, "mage_robe": 3800, "dragon_armor": 40_000,
    "dragonbane_helm": 25_000, "dragonbane_boots": 25_000, "leather_boots": 120, "swift_boots": 2200,
    "traveler_boots": 900, "iron_boots": 2400, "wind_boots": 6200, "strength_ring": 2800, "luck_ring": 2800,
    "life_amulet": 3000, "guard_ring": 2800, "sage_ring": 2800, "swift_amulet": 3000, "ward_amulet": 6800,
}


async def retire_old_gear(db: Database, now: int) -> dict[int, tuple[int, int]]:
    """Close fights of the old engine, then pay out and remove every old gear piece. Returns ``{player id: (pieces, coins)}`` for who got something."""
    paid: dict[int, tuple[int, int]] = {}
    async with db.transaction() as tx:
        # fights started before the update hold heroes without the new skills: close them (new fights always carry "cds")
        old = "state NOT LIKE '%\"cds\"%'"
        await tx.execute(f"UPDATE solo_fights SET status = 'fled', updated_at = ? WHERE status = 'active' AND {old}", (now,))
        await tx.execute(f"UPDATE duels SET status = 'expired', updated_at = ? WHERE status = 'active' AND {old}", (now,))
        await tx.execute(f"UPDATE team_battles SET status = 'cancelled', updated_at = ? WHERE status = 'active' AND {old}", (now,))
        rows = await tx.fetchall("SELECT id, player_id, item_id, upgrade FROM gear")
        if not rows:
            return paid
        await tx.execute("UPDATE bet_duels SET status = 'cancelled' WHERE kind = 'gear' AND status IN ('open', 'active')")
        await tx.execute("UPDATE market_listings SET status = 'cancelled', closed_at = ? WHERE gear_id IS NOT NULL AND status = 'active'", (now,))
        await tx.execute("UPDATE market_listings SET gear_id = NULL WHERE gear_id IS NOT NULL")
        for row in rows:
            value = round(LEGACY_VALUE.get(row["item_id"], 500) * (1 + 0.5 * row["upgrade"]))
            await wallet.apply(tx, row["player_id"], gold=value, reason="gear_retired", now=now, ref=f"gear_retired:{row['id']}")
            count, coins = paid.get(row["player_id"], (0, 0))
            paid[row["player_id"]] = (count + 1, coins + value)
        await tx.execute("DELETE FROM gear")
    return paid
