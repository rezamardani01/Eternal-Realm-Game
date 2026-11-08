"""Queries on ``bosses`` and ``boss_hits`` (the fighters of a boss)."""

from __future__ import annotations

from ..database import Row, Tx


async def create(
    tx: Tx, chat_id: int, boss_type: str, level: int, summoner_id: int, now: int, recruit_until: int
) -> int:
    return await tx.execute(
        "INSERT INTO bosses (chat_id, boss_type, level, max_hp, hp, status, summoner_id, created_at, expires_at,"
        " phase, recruit_until) VALUES (?, ?, ?, 1, 1, 'active', ?, ?, ?, 'recruiting', ?)",
        (chat_id, boss_type, level, summoner_id, now, recruit_until, recruit_until),
    )


async def get(tx: Tx, boss_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM bosses WHERE id = ?", (boss_id,))


async def active_in_chat(tx: Tx, chat_id: int) -> Row | None:
    return await tx.fetchone(
        "SELECT * FROM bosses WHERE chat_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1", (chat_id,)
    )


async def all_active(tx: Tx) -> list[Row]:
    return await tx.fetchall("SELECT * FROM bosses WHERE status = 'active' ORDER BY id")


async def last_created(tx: Tx, chat_id: int) -> int:
    return int(await tx.scalar("SELECT MAX(created_at) FROM bosses WHERE chat_id = ?", (chat_id,), 0))


async def set_message(tx: Tx, boss_id: int, message_id: int) -> None:
    await tx.execute("UPDATE bosses SET message_id = ? WHERE id = ?", (message_id, boss_id))


async def begin_fight(
    tx: Tx, boss_id: int, level: int, max_hp: int, state: str, now: int, next_round_at: int, expires_at: int
) -> bool:
    """recruiting -> fighting exactly once."""
    await tx.execute(
        "UPDATE bosses SET phase = 'fighting', level = ?, max_hp = ?, hp = ?, state = ?, last_report_at = ?,"
        " next_round_at = ?, expires_at = ? WHERE id = ? AND status = 'active' AND phase = 'recruiting'",
        (level, max_hp, max_hp, state, now, next_round_at, expires_at, boss_id),
    )
    return tx.rowcount == 1


async def save_fight(
    tx: Tx, boss_id: int, hp: int, state: str, next_round_at: int, last_report_at: int
) -> None:
    await tx.execute(
        "UPDATE bosses SET hp = ?, state = ?, next_round_at = ?, last_report_at = ? WHERE id = ?",
        (hp, state, next_round_at, last_report_at, boss_id),
    )


async def close(tx: Tx, boss_id: int, status: str, now: int) -> bool:
    """active -> defeated/expired exactly once: the gate that makes rewards non-repeatable."""
    await tx.execute(
        "UPDATE bosses SET status = ?, ended_at = ? WHERE id = ? AND status = 'active'", (status, now, boss_id)
    )
    return tx.rowcount == 1


async def add_fighter(tx: Tx, boss_id: int, player_id: int, hp: int) -> bool:
    await tx.execute(
        "INSERT OR IGNORE INTO boss_hits (boss_id, player_id, damage, hits, hp, max_hp, alive)"
        " VALUES (?, ?, 0, 0, ?, ?, 1)",
        (boss_id, player_id, hp, hp),
    )
    return tx.rowcount == 1


async def save_fighter(tx: Tx, boss_id: int, player_id: int, hp: int, alive: bool, damage: int, absorbed: int) -> None:
    await tx.execute(
        "UPDATE boss_hits SET hp = ?, alive = ?, damage = ?, absorbed = ?, hits = hits + 1"
        " WHERE boss_id = ? AND player_id = ?",
        (hp, int(alive), damage, absorbed, boss_id, player_id),
    )


async def fighters(tx: Tx, boss_id: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT h.player_id, h.damage, h.absorbed, h.hp, h.max_hp, h.alive, p.display_name AS name,"
        " p.platform_user_id AS platform_user_id, p.class AS class_id, p.level AS level FROM boss_hits h"
        " JOIN players p ON p.id = h.player_id WHERE h.boss_id = ? ORDER BY h.rowid",
        (boss_id,),
    )
