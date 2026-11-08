"""Queries on ``group_events`` and the event schedule kept on ``groups``."""

from __future__ import annotations

from ..database import Row, Tx


async def create(tx: Tx, chat_id: int, kind: str, state: str, now: int, expires_at: int) -> int:
    return await tx.execute(
        "INSERT INTO group_events (chat_id, kind, status, state, created_at, expires_at)"
        " VALUES (?, ?, 'active', ?, ?, ?)",
        (chat_id, kind, state, now, expires_at),
    )


async def get(tx: Tx, event_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM group_events WHERE id = ?", (event_id,))


async def active_in_chat(tx: Tx, chat_id: int, now: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT * FROM group_events WHERE chat_id = ? AND status = 'active' AND expires_at > ? ORDER BY id",
        (chat_id, now),
    )


async def set_message(tx: Tx, event_id: int, message_id: int) -> None:
    await tx.execute("UPDATE group_events SET message_id = ? WHERE id = ?", (message_id, event_id))


async def save_state(tx: Tx, event_id: int, state: str) -> None:
    await tx.execute("UPDATE group_events SET state = ? WHERE id = ?", (state, event_id))


async def finish(tx: Tx, event_id: int, status: str) -> bool:
    """active -> done/expired exactly once (also decides who won a race for the prize)."""
    await tx.execute(
        "UPDATE group_events SET status = ? WHERE id = ? AND status = 'active'", (status, event_id)
    )
    return tx.rowcount == 1


async def lapsed(tx: Tx, now: int) -> list[Row]:
    return await tx.fetchall("SELECT * FROM group_events WHERE status = 'active' AND expires_at <= ?", (now,))


async def double_xp_active(tx: Tx, chat_id: int, now: int) -> bool:
    row = await tx.fetchone(
        "SELECT 1 FROM group_events WHERE chat_id = ? AND kind = 'double_xp' AND status = 'active'"
        " AND expires_at > ?",
        (chat_id, now),
    )
    return row is not None


async def due_groups(tx: Tx, now: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT chat_id FROM groups WHERE enabled = 1 AND next_event_at <= ? AND last_seen >= ?"
        " AND (',' || disabled_cmds || ',') NOT LIKE '%,events,%'",
        (now, now - 86400),
    )


async def schedule(tx: Tx, chat_id: int, at: int) -> None:
    await tx.execute("UPDATE groups SET next_event_at = ? WHERE chat_id = ?", (at, chat_id))


async def active_members(tx: Tx, chat_id: int, since: int) -> int:
    return int(
        await tx.scalar(
            "SELECT COUNT(*) FROM group_members WHERE chat_id = ? AND last_active >= ?", (chat_id, since), 0
        )
    )


async def most_recent_member(tx: Tx, chat_id: int) -> int | None:
    row = await tx.fetchone(
        "SELECT player_id FROM group_members WHERE chat_id = ? ORDER BY last_active DESC LIMIT 1", (chat_id,)
    )
    return int(row["player_id"]) if row else None
