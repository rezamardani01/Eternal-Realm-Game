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
    origin: str = ""
    bond_uses: int = 0

    @classmethod
    def from_row(cls, row: Row) -> GearRow:
        return cls(
            row["id"], row["player_id"], row["item_id"], row["upgrade"], row["slot"], bool(row["listed"]),
            row["origin"], row["bond_uses"],
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
async def add_gear(tx: Tx, player_id: int, item_id: str, now: int, upgrade: int = 0, origin: str = "") -> int:
    return await tx.execute(
        "INSERT INTO gear (player_id, item_id, upgrade, created_at, origin) VALUES (?, ?, ?, ?, ?)",
        (player_id, item_id, upgrade, now, origin),
    )


async def add_bond(tx: Tx, player_id: int, uses: int = 1) -> None:
    """The weapon in hand grows closer to its wielder."""
    await tx.execute(
        "UPDATE gear SET bond_uses = bond_uses + ? WHERE player_id = ? AND slot = 'weapon'", (uses, player_id)
    )


async def owns_gear(tx: Tx, player_id: int, item_id: str) -> bool:
    row = await tx.fetchone("SELECT 1 FROM gear WHERE player_id = ? AND item_id = ? LIMIT 1", (player_id, item_id))
    return row is not None


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
    # finished market listings still point at the piece; keep that history (item id stays) but unlink it
    await tx.execute("UPDATE market_listings SET gear_id = NULL WHERE gear_id = ?", (gear_id,))
    await tx.execute("DELETE FROM gear WHERE id = ?", (gear_id,))


async def transfer_gear(tx: Tx, gear_id: int, new_owner: int) -> None:
    """Hand a piece to a new owner and note the previous owner in its history."""
    await tx.execute(
        "UPDATE gear SET origin = origin || CASE WHEN origin = '' THEN '' ELSE char(10) END"
        " || 'دست‌به‌دست شد؛ صاحب قبلی: ' || (SELECT display_name FROM players WHERE id = gear.player_id),"
        " player_id = ?, slot = NULL, listed = 0 WHERE id = ?",
        (new_owner, gear_id),
    )


async def set_listed(tx: Tx, gear_id: int, listed: bool) -> None:
    await tx.execute("UPDATE gear SET listed = ? WHERE id = ?", (int(listed), gear_id))


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
