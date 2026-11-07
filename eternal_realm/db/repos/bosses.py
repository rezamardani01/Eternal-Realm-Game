"""Queries on ``bosses`` and ``boss_hits``."""

from __future__ import annotations

from ..database import Row, Tx


async def create(
    tx: Tx, chat_id: int, boss_type: str, level: int, max_hp: int, summoner_id: int, now: int, expires_at: int
) -> int:
    return await tx.execute(
        "INSERT INTO bosses (chat_id, boss_type, level, max_hp, hp, status, summoner_id, created_at, expires_at)"
        " VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
        (chat_id, boss_type, level, max_hp, max_hp, summoner_id, now, expires_at),
    )


async def get(tx: Tx, boss_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM bosses WHERE id = ?", (boss_id,))


async def active_in_chat(tx: Tx, chat_id: int) -> Row | None:
    return await tx.fetchone(
        "SELECT * FROM bosses WHERE chat_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1", (chat_id,)
    )


async def last_created(tx: Tx, chat_id: int) -> int:
    return int(await tx.scalar("SELECT MAX(created_at) FROM bosses WHERE chat_id = ?", (chat_id,), 0))


async def set_message(tx: Tx, boss_id: int, message_id: int) -> None:
    await tx.execute("UPDATE bosses SET message_id = ? WHERE id = ?", (message_id, boss_id))


async def damage(tx: Tx, boss_id: int, amount: int) -> bool:
    """Take health from an active boss; ``False`` when it was already gone."""
    await tx.execute(
        "UPDATE bosses SET hp = hp - ? WHERE id = ? AND status = 'active' AND hp >= ? AND hp > 0",
        (amount, boss_id, amount),
    )
    return tx.rowcount == 1


async def close(tx: Tx, boss_id: int, status: str, now: int) -> bool:
    """active -> defeated/expired exactly once: the gate that makes rewards non-repeatable."""
    await tx.execute(
        "UPDATE bosses SET status = ?, ended_at = ? WHERE id = ? AND status = 'active'", (status, now, boss_id)
    )
    return tx.rowcount == 1


async def add_hit(tx: Tx, boss_id: int, player_id: int, amount: int) -> None:
    await tx.execute(
        "INSERT INTO boss_hits (boss_id, player_id, damage, hits) VALUES (?, ?, ?, 1)"
        " ON CONFLICT (boss_id, player_id) DO UPDATE SET damage = damage + excluded.damage, hits = hits + 1",
        (boss_id, player_id, amount),
    )


async def hitters(tx: Tx, boss_id: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT h.player_id, h.damage, h.hits, p.display_name AS name FROM boss_hits h"
        " JOIN players p ON p.id = h.player_id WHERE h.boss_id = ? ORDER BY h.damage DESC, h.player_id",
        (boss_id,),
    )


async def stale(tx: Tx, now: int) -> list[Row]:
    return await tx.fetchall("SELECT * FROM bosses WHERE status = 'active' AND expires_at <= ?", (now,))
