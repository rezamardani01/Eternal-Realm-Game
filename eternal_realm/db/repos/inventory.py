"""Queries on ``inventory`` (stackable items), ``gear`` (single pieces) and ``cooldowns``."""

from __future__ import annotations

from dataclasses import dataclass

from ..database import Row, Tx


# --- stacks -----------------------------------------------------------------------------------
async def add_stack(tx: Tx, player_id: int, item_id: str, qty: int) -> None:
    await tx.execute(
        "INSERT INTO inventory (player_id, item_id, qty) VALUES (?, ?, ?)"
        " ON CONFLICT (player_id, item_id) DO UPDATE SET qty = qty + excluded.qty",
        (player_id, item_id, qty),
    )


async def remove_stack(tx: Tx, player_id: int, item_id: str, qty: int) -> bool:
    """Take ``qty`` items; ``False`` (and nothing changes) when the player has fewer."""
    await tx.execute(
        "UPDATE inventory SET qty = qty - ? WHERE player_id = ? AND item_id = ? AND qty >= ?",
        (qty, player_id, item_id, qty),
    )
    if tx.rowcount == 0:
        return False
    await tx.execute("DELETE FROM inventory WHERE player_id = ? AND item_id = ? AND qty = 0", (player_id, item_id))
    return True


async def stack_qty(tx: Tx, player_id: int, item_id: str) -> int:
    return int(
        await tx.scalar(
            "SELECT qty FROM inventory WHERE player_id = ? AND item_id = ?", (player_id, item_id), 0
        )
    )


async def stacks(tx: Tx, player_id: int) -> list[tuple[str, int]]:
    rows = await tx.fetchall(
        "SELECT item_id, qty FROM inventory WHERE player_id = ? AND qty > 0 ORDER BY item_id", (player_id,)
    )
    return [(r["item_id"], r["qty"]) for r in rows]


# --- gear -------------------------------------------------------------------------------------
# --- daily usage (stepped cooldowns) -----------------------------------------------------------
async def uses_today(tx: Tx, player_id: int, key: str, day: int) -> int:
    row = await tx.fetchone("SELECT day, uses FROM activity_usage WHERE player_id = ? AND key = ?", (player_id, key))
    return int(row["uses"]) if row is not None and row["day"] == day else 0


async def record_use(tx: Tx, player_id: int, key: str, day: int) -> None:
    await tx.execute(
        "INSERT INTO activity_usage (player_id, key, day, uses) VALUES (?, ?, ?, 1)"
        " ON CONFLICT (player_id, key) DO UPDATE SET"
        " uses = CASE WHEN day = excluded.day THEN uses + 1 ELSE 1 END, day = excluded.day",
        (player_id, key, day),
    )


# --- cooldowns --------------------------------------------------------------------------------
async def cooldown_until(tx: Tx, player_id: int, key: str) -> int:
    return int(
        await tx.scalar("SELECT until FROM cooldowns WHERE player_id = ? AND key = ?", (player_id, key), 0)
    )


async def set_cooldown(tx: Tx, player_id: int, key: str, until: int) -> None:
    await tx.execute(
        "INSERT INTO cooldowns (player_id, key, until) VALUES (?, ?, ?)"
        " ON CONFLICT (player_id, key) DO UPDATE SET until = excluded.until",
        (player_id, key, until),
    )
