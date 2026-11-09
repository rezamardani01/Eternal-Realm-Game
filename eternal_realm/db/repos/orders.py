"""Queries on the ``orders`` table."""

from __future__ import annotations

from ..database import Row, Tx


async def create(
    tx: Tx, player_id: int, pack_id: str, amount: int, payload: str, now: int, *, gift_to: int | None = None, qty: int = 1
) -> int:
    return await tx.execute(
        "INSERT INTO orders (player_id, pack_id, amount, status, payload, created_at, gift_to, qty)"
        " VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)",
        (player_id, pack_id, amount, payload, now, gift_to, qty),
    )


async def get(tx: Tx, order_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))


async def by_payload(tx: Tx, payload: str) -> Row | None:
    return await tx.fetchone(
        "SELECT o.*, p.platform_user_id AS platform_user_id FROM orders o"
        " JOIN players p ON p.id = o.player_id WHERE o.payload = ?",
        (payload,),
    )


async def mark_paid(tx: Tx, order_id: int, charge_id: str, now: int) -> bool:
    """pending/failed -> paid exactly once (a late payment of an expired order is still honoured)."""
    await tx.execute(
        "UPDATE orders SET status = 'paid', charge_id = ?, paid_at = ?"
        " WHERE id = ? AND status IN ('pending', 'failed')",
        (charge_id, now, order_id),
    )
    return tx.rowcount == 1


async def mark_delivered(tx: Tx, order_id: int, now: int) -> bool:
    await tx.execute(
        "UPDATE orders SET status = 'delivered', delivered_at = ? WHERE id = ? AND status = 'paid'",
        (now, order_id),
    )
    return tx.rowcount == 1


async def mark_failed(tx: Tx, order_id: int) -> None:
    await tx.execute("UPDATE orders SET status = 'failed' WHERE id = ? AND status = 'pending'", (order_id,))


async def expire_pending(tx: Tx, older_than: int) -> int:
    await tx.execute(
        "UPDATE orders SET status = 'failed' WHERE status = 'pending' AND created_at < ?", (older_than,)
    )
    return tx.rowcount


async def recent_for_player(tx: Tx, player_id: int, limit: int = 10) -> list[Row]:
    return await tx.fetchall(
        "SELECT * FROM orders WHERE player_id = ? ORDER BY id DESC LIMIT ?", (player_id, limit)
    )


async def stats(tx: Tx) -> Row | None:
    return await tx.fetchone(
        "SELECT COUNT(*) AS delivered, COALESCE(SUM(amount), 0) AS revenue FROM orders"
        " WHERE status = 'delivered'"
    )
