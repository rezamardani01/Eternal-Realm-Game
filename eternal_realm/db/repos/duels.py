"""Queries on the ``duels`` table."""

from __future__ import annotations

from ..database import Row, Tx

OPEN = ("pending", "active")


async def create(tx: Tx, chat_id: int, challenger_id: int, target_id: int, now: int, expires_at: int) -> int:
    return await tx.execute(
        "INSERT INTO duels (chat_id, challenger_id, target_id, status, created_at, updated_at, expires_at)"
        " VALUES (?, ?, ?, 'pending', ?, ?, ?)",
        (chat_id, challenger_id, target_id, now, now, expires_at),
    )


async def get(tx: Tx, duel_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM duels WHERE id = ?", (duel_id,))


async def set_message(tx: Tx, duel_id: int, message_id: int) -> None:
    await tx.execute("UPDATE duels SET message_id = ? WHERE id = ?", (message_id, duel_id))


async def open_for(tx: Tx, player_ids: tuple[int, int]) -> Row | None:
    a, b = player_ids
    return await tx.fetchone(
        "SELECT * FROM duels WHERE status IN ('pending', 'active')"
        " AND (challenger_id IN (?, ?) OR target_id IN (?, ?)) LIMIT 1",
        (a, b, a, b),
    )


async def expire_pending_for(tx: Tx, player_ids: tuple[int, int], now: int) -> None:
    a, b = player_ids
    await tx.execute(
        "UPDATE duels SET status = 'expired', updated_at = ? WHERE status = 'pending' AND expires_at <= ?"
        " AND (challenger_id IN (?, ?) OR target_id IN (?, ?))",
        (now, now, a, b, a, b),
    )


async def pair_count_since(tx: Tx, a: int, b: int, since: int) -> int:
    return int(
        await tx.scalar(
            "SELECT COUNT(*) FROM duels WHERE status IN ('active', 'finished') AND created_at >= ?"
            " AND ((challenger_id = ? AND target_id = ?) OR (challenger_id = ? AND target_id = ?))",
            (since, a, b, b, a),
            0,
        )
    )


async def finished_count_since(tx: Tx, player_id: int, since: int) -> int:
    return int(
        await tx.scalar(
            "SELECT COUNT(*) FROM duels WHERE status = 'finished' AND updated_at >= ?"
            " AND (challenger_id = ? OR target_id = ?)",
            (since, player_id, player_id),
            0,
        )
    )


async def start(tx: Tx, duel_id: int, state: str, now: int, expires_at: int) -> bool:
    """pending -> active, only if still pending and not expired."""
    await tx.execute(
        "UPDATE duels SET status = 'active', state = ?, updated_at = ?, expires_at = ?"
        " WHERE id = ? AND status = 'pending' AND expires_at > ?",
        (state, now, expires_at, duel_id, now),
    )
    return tx.rowcount == 1


async def save_state(tx: Tx, duel_id: int, state: str, now: int, expires_at: int) -> None:
    await tx.execute(
        "UPDATE duels SET state = ?, updated_at = ?, expires_at = ? WHERE id = ? AND status = 'active'",
        (state, now, expires_at, duel_id),
    )


async def finish(tx: Tx, duel_id: int, state: str, winner_id: int | None, now: int) -> bool:
    """active -> finished exactly once (the guard that makes rewards non-repeatable)."""
    await tx.execute(
        "UPDATE duels SET status = 'finished', state = ?, winner_id = ?, updated_at = ?"
        " WHERE id = ? AND status = 'active'",
        (state, winner_id, now, duel_id),
    )
    return tx.rowcount == 1


async def close_pending(tx: Tx, duel_id: int, status: str, now: int) -> bool:
    await tx.execute(
        "UPDATE duels SET status = ?, updated_at = ? WHERE id = ? AND status = 'pending'",
        (status, now, duel_id),
    )
    return tx.rowcount == 1


async def stale(tx: Tx, now: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT * FROM duels WHERE status IN ('pending', 'active') AND expires_at <= ?", (now,)
    )
