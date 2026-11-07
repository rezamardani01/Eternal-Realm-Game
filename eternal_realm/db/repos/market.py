"""Queries on ``market_listings``."""

from __future__ import annotations

from ..database import Row, Tx


async def create(
    tx: Tx, seller_id: int, item_id: str, qty: int, gear_id: int | None, price: int, now: int
) -> int:
    return await tx.execute(
        "INSERT INTO market_listings (seller_id, item_id, qty, gear_id, price, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, 'active', ?)",
        (seller_id, item_id, qty, gear_id, price, now),
    )


async def get(tx: Tx, listing_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM market_listings WHERE id = ?", (listing_id,))


async def close(tx: Tx, listing_id: int, status: str, buyer_id: int | None, now: int) -> bool:
    """active -> sold/cancelled exactly once; ``False`` if somebody else got there first."""
    await tx.execute(
        "UPDATE market_listings SET status = ?, buyer_id = ?, closed_at = ?"
        " WHERE id = ? AND status = 'active'",
        (status, buyer_id, now, listing_id),
    )
    return tx.rowcount == 1


async def count_active(tx: Tx, seller_id: int) -> int:
    return int(
        await tx.scalar(
            "SELECT COUNT(*) FROM market_listings WHERE seller_id = ? AND status = 'active'", (seller_id,), 0
        )
    )


async def browse(
    tx: Tx, item_id: str | None, limit: int, offset: int = 0, item_ids: list[str] | None = None
) -> list[Row]:
    sql = (
        "SELECT m.*, p.display_name AS seller_name, g.upgrade AS upgrade FROM market_listings m"
        " JOIN players p ON p.id = m.seller_id LEFT JOIN gear g ON g.id = m.gear_id"
        " WHERE m.status = 'active'"
    )
    params: list[object] = []
    if item_id:
        sql += " AND m.item_id = ?"
        params.append(item_id)
    if item_ids is not None:
        if not item_ids:
            return []
        sql += " AND m.item_id IN (" + ",".join("?" * len(item_ids)) + ")"
        params += item_ids
    sql += " ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    return await tx.fetchall(sql, params)


async def of_seller(tx: Tx, seller_id: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT m.*, p.display_name AS seller_name, g.upgrade AS upgrade FROM market_listings m"
        " JOIN players p ON p.id = m.seller_id LEFT JOIN gear g ON g.id = m.gear_id"
        " WHERE m.seller_id = ? AND m.status = 'active' ORDER BY m.id",
        (seller_id,),
    )
