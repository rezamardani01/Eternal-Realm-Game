"""Queries on ``inventory`` (stackable items), ``gear`` (single pieces) and ``cooldowns``."""

from __future__ import annotations

from dataclasses import dataclass

from ..database import Row, Tx


@dataclass
class GearRow:
    id: int
    player_id: int
    item_id: str
    upgrade: int
    slot: str | None
    listed: bool = False

    @classmethod
    def from_row(cls, row: Row) -> GearRow:
        return cls(
            row["id"], row["player_id"], row["item_id"], row["upgrade"], row["slot"], bool(row["listed"])
        )


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
async def add_gear(tx: Tx, player_id: int, item_id: str, now: int, upgrade: int = 0) -> int:
    return await tx.execute(
        "INSERT INTO gear (player_id, item_id, upgrade, created_at) VALUES (?, ?, ?, ?)",
        (player_id, item_id, upgrade, now),
    )


async def get_gear(tx: Tx, gear_id: int) -> GearRow | None:
    row = await tx.fetchone("SELECT * FROM gear WHERE id = ?", (gear_id,))
    return GearRow.from_row(row) if row else None


async def list_gear(tx: Tx, player_id: int) -> list[GearRow]:
    rows = await tx.fetchall(
        "SELECT * FROM gear WHERE player_id = ? AND listed = 0 ORDER BY id", (player_id,)
    )
    return [GearRow.from_row(r) for r in rows]


async def equipped_in_slot(tx: Tx, player_id: int, slot: str) -> GearRow | None:
    row = await tx.fetchone("SELECT * FROM gear WHERE player_id = ? AND slot = ?", (player_id, slot))
    return GearRow.from_row(row) if row else None


async def set_slot(tx: Tx, gear_id: int, slot: str | None) -> None:
    await tx.execute("UPDATE gear SET slot = ? WHERE id = ?", (slot, gear_id))


async def set_upgrade(tx: Tx, gear_id: int, upgrade: int) -> None:
    await tx.execute("UPDATE gear SET upgrade = ? WHERE id = ?", (upgrade, gear_id))


async def delete_gear(tx: Tx, gear_id: int) -> None:
    await tx.execute("DELETE FROM gear WHERE id = ?", (gear_id,))


async def transfer_gear(tx: Tx, gear_id: int, new_owner: int) -> None:
    await tx.execute(
        "UPDATE gear SET player_id = ?, slot = NULL, listed = 0 WHERE id = ?", (new_owner, gear_id)
    )


async def set_listed(tx: Tx, gear_id: int, listed: bool) -> None:
    await tx.execute("UPDATE gear SET listed = ? WHERE id = ?", (int(listed), gear_id))


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
