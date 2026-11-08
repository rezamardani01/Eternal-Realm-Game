"""Queries on ``groups`` and ``group_members``."""

from __future__ import annotations

from ..database import Row, Tx


async def touch(tx: Tx, chat_id: int, title: str, now: int) -> None:
    await tx.execute(
        "INSERT INTO groups (chat_id, title, created_at, last_seen, next_event_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT (chat_id) DO UPDATE SET title = excluded.title, last_seen = excluded.last_seen",
        (chat_id, title, now, now, now + 2700),  # a first surprise about 45 minutes after we meet a group
    )


async def get(tx: Tx, chat_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))


async def set_enabled(tx: Tx, chat_id: int, enabled: bool) -> None:
    await tx.execute("UPDATE groups SET enabled = ? WHERE chat_id = ?", (int(enabled), chat_id))


async def set_disabled_commands(tx: Tx, chat_id: int, names: set[str]) -> None:
    await tx.execute(
        "UPDATE groups SET disabled_cmds = ? WHERE chat_id = ?", (",".join(sorted(names)), chat_id)
    )


async def add_points(tx: Tx, chat_id: int, player_id: int, points: int, now: int) -> None:
    await tx.execute(
        "INSERT INTO group_members (chat_id, player_id, points, last_active) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (chat_id, player_id) DO UPDATE SET"
        " points = points + excluded.points, last_active = excluded.last_active",
        (chat_id, player_id, points, now),
    )


async def top_members(tx: Tx, chat_id: int, limit: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT p.display_name, p.platform_user_id AS uid, p.race, p.class, p.level, m.points FROM group_members m"
        " JOIN players p ON p.id = m.player_id WHERE m.chat_id = ? AND m.points > 0"
        " ORDER BY m.points DESC, p.level DESC LIMIT ?",
        (chat_id, limit),
    )


async def count_groups(tx: Tx) -> int:
    return int(await tx.scalar("SELECT COUNT(*) FROM groups", default=0))
