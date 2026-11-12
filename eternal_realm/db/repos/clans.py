"""Queries on ``clans`` and ``clan_members``."""

from __future__ import annotations

from ..database import Row, Tx


async def create(tx: Tx, name: str, leader_id: int, now: int) -> int:
    clan_id = await tx.execute(
        "INSERT INTO clans (name, leader_id, created_at) VALUES (?, ?, ?)", (name, leader_id, now)
    )
    await add_member(tx, leader_id, clan_id, "leader", now)
    return clan_id


async def get(tx: Tx, clan_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM clans WHERE id = ?", (clan_id,))


async def by_name(tx: Tx, name: str) -> Row | None:
    return await tx.fetchone("SELECT * FROM clans WHERE name = ?", (name,))


async def membership(tx: Tx, player_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM clan_members WHERE player_id = ?", (player_id,))


async def add_member(tx: Tx, player_id: int, clan_id: int, role: str, now: int) -> None:
    await tx.execute(
        "INSERT INTO clan_members (player_id, clan_id, role, joined_at) VALUES (?, ?, ?, ?)",
        (player_id, clan_id, role, now),
    )


async def remove_member(tx: Tx, player_id: int) -> bool:
    await tx.execute("DELETE FROM clan_members WHERE player_id = ?", (player_id,))
    return tx.rowcount == 1


async def set_role(tx: Tx, player_id: int, role: str) -> None:
    await tx.execute("UPDATE clan_members SET role = ? WHERE player_id = ?", (role, player_id))


async def set_leader(tx: Tx, clan_id: int, player_id: int) -> None:
    await tx.execute("UPDATE clans SET leader_id = ? WHERE id = ?", (player_id, clan_id))


async def set_open(tx: Tx, clan_id: int, value: bool) -> None:
    await tx.execute("UPDATE clans SET open = ? WHERE id = ?", (int(value), clan_id))


async def count_members(tx: Tx, clan_id: int) -> int:
    return int(await tx.scalar("SELECT COUNT(*) FROM clan_members WHERE clan_id = ?", (clan_id,), 0))


async def members(tx: Tx, clan_id: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT m.player_id, m.role, m.donated, m.joined_at, p.display_name AS name, p.level AS level,"
        " p.platform_user_id AS platform_user_id FROM clan_members m JOIN players p ON p.id = m.player_id"
        " WHERE m.clan_id = ? ORDER BY CASE m.role WHEN 'leader' THEN 0 WHEN 'deputy' THEN 1 WHEN 'elder' THEN 2"
        " ELSE 3 END, p.level DESC, m.joined_at",
        (clan_id,),
    )


async def donate(tx: Tx, clan_id: int, player_id: int, amount: int) -> None:
    await tx.execute(
        "UPDATE clans SET treasury = treasury + ?, donated = donated + ? WHERE id = ?", (amount, amount, clan_id)
    )
    await tx.execute("UPDATE clan_members SET donated = donated + ? WHERE player_id = ?", (amount, player_id))


async def delete(tx: Tx, clan_id: int) -> None:
    await tx.execute("DELETE FROM clan_members WHERE clan_id = ?", (clan_id,))
    await tx.execute("DELETE FROM clan_war WHERE clan_id = ?", (clan_id,))
    await tx.execute("DELETE FROM clan_withdrawals WHERE clan_id = ?", (clan_id,))
    await tx.execute("DELETE FROM clans WHERE id = ?", (clan_id,))


async def listing(tx: Tx, limit: int, offset: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT c.* FROM clans c ORDER BY (SELECT COALESCE(SUM(p.level), 0) FROM clan_members m"
        " JOIN players p ON p.id = m.player_id WHERE m.clan_id = c.id) DESC, c.donated DESC, c.id LIMIT ? OFFSET ?",
        (limit, offset),
    )


WEEK = 7 * 86400


def week_of(now: int) -> int:
    """Clan-war week number (weeks start on Saturday, Tehran time)."""
    return (now + 12600 + 2 * 86400) // WEEK


async def add_war_points(tx: Tx, player_id: int, points: int, now: int) -> None:
    member = await membership(tx, player_id)
    if member is not None:
        await add_clan_points(tx, member["clan_id"], points, now)


async def add_clan_points(tx: Tx, clan_id: int, points: int, now: int) -> None:
    """Points of a clan in this week's league."""
    if points <= 0:
        return
    await tx.execute(
        "INSERT INTO clan_war (week, clan_id, points) VALUES (?, ?, ?)"
        " ON CONFLICT (week, clan_id) DO UPDATE SET points = points + excluded.points",
        (week_of(now), clan_id, points),
    )


async def award_khan(tx: Tx, winner_id: int, loser_id: int) -> None:
    """Khan points for a duel between members of two different clans."""
    from ...game.data.khan_shop import DUEL_LOSE_POINTS, DUEL_WIN_POINTS

    won, lost = await membership(tx, winner_id), await membership(tx, loser_id)
    if won is None or lost is None or won["clan_id"] == lost["clan_id"]:
        return
    await tx.execute("UPDATE players SET khan_points = khan_points + ? WHERE id = ?", (DUEL_WIN_POINTS, winner_id))
    await tx.execute("UPDATE players SET khan_points = khan_points + ? WHERE id = ?", (DUEL_LOSE_POINTS, loser_id))


async def war_board(tx: Tx, week: int, limit: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT w.clan_id, w.points, c.name FROM clan_war w JOIN clans c ON c.id = w.clan_id"
        " WHERE w.week = ? ORDER BY w.points DESC, w.clan_id LIMIT ?",
        (week, limit),
    )
