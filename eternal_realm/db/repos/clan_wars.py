"""Queries on ``clan_wars`` and ``clan_war_attacks``: a declared war between two clans."""

from __future__ import annotations

from ..database import Row, Tx

#: a war that still occupies its two clans
OPEN = ("pending", "active")


async def create(tx: Tx, attacker: Row, defender: Row, stake: int, now: int, deadline: int) -> int:
    return await tx.execute(
        "INSERT INTO clan_wars (attacker_id, defender_id, attacker_name, defender_name, stake, status, created_at, ends_at)"
        " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
        (attacker["id"], defender["id"], attacker["name"], defender["name"], stake, now, deadline),
    )


async def get(tx: Tx, war_id: int) -> Row | None:
    return await tx.fetchone("SELECT * FROM clan_wars WHERE id = ?", (war_id,))


async def open_for(tx: Tx, clan_id: int) -> Row | None:
    """The war (waiting for an answer or running) this clan is busy with."""
    return await tx.fetchone(
        "SELECT * FROM clan_wars WHERE status IN ('pending', 'active') AND (attacker_id = ? OR defender_id = ?)"
        " ORDER BY id DESC LIMIT 1",
        (clan_id, clan_id),
    )


async def busy_ids(tx: Tx) -> set[int]:
    rows = await tx.fetchall("SELECT attacker_id, defender_id FROM clan_wars WHERE status IN ('pending', 'active')")
    return {r["attacker_id"] for r in rows} | {r["defender_id"] for r in rows}


async def history(tx: Tx, clan_id: int, limit: int) -> list[Row]:
    return await tx.fetchall(
        "SELECT * FROM clan_wars WHERE status = 'done' AND (attacker_id = ? OR defender_id = ?) ORDER BY id DESC LIMIT ?",
        (clan_id, clan_id, limit),
    )


async def record(tx: Tx, clan_id: int) -> tuple[int, int, int]:
    """Wins, losses and draws of a clan in every finished war."""
    row = await tx.fetchone(
        "SELECT COALESCE(SUM(winner_id = ?), 0) AS won, COALESCE(SUM(winner_id NOT IN (0, ?)), 0) AS lost,"
        " COALESCE(SUM(winner_id = 0), 0) AS drawn FROM clan_wars"
        " WHERE status = 'done' AND (attacker_id = ? OR defender_id = ?)",
        (clan_id, clan_id, clan_id, clan_id),
    )
    assert row is not None
    return int(row["won"]), int(row["lost"]), int(row["drawn"])


async def last_between(tx: Tx, a: int, b: int) -> int:
    """When the latest finished war between these two clans ended (0 = they never fought)."""
    return int(
        await tx.scalar(
            "SELECT COALESCE(MAX(ends_at), 0) FROM clan_wars WHERE status = 'done'"
            " AND ((attacker_id = ? AND defender_id = ?) OR (attacker_id = ? AND defender_id = ?))",
            (a, b, b, a),
            0,
        )
    )


async def due(tx: Tx, now: int) -> list[Row]:
    """Challenges nobody answered in time and wars whose time is up."""
    return await tx.fetchall(
        "SELECT * FROM clan_wars WHERE status IN ('pending', 'active') AND ends_at <= ? ORDER BY id", (now,)
    )


async def close(tx: Tx, war_id: int, was: str, status: str, winner_id: int = 0, ends_at: int | None = None) -> bool:
    """Move a war out of ``was``; False when somebody else already did (the gate that makes every ending happen once)."""
    await tx.execute(
        "UPDATE clan_wars SET status = ?, winner_id = ?, ends_at = COALESCE(?, ends_at) WHERE id = ? AND status = ?",
        (status, winner_id, ends_at, war_id, was),
    )
    return tx.rowcount == 1


async def begin(tx: Tx, war_id: int, now: int, ends_at: int) -> bool:
    await tx.execute(
        "UPDATE clan_wars SET status = 'active', starts_at = ?, ends_at = ? WHERE id = ? AND status = 'pending'",
        (now, ends_at, war_id),
    )
    return tx.rowcount == 1


async def pay_treasury(tx: Tx, clan_id: int, amount: int) -> None:
    """Gold into a clan's treasury (nothing happens when the clan is gone)."""
    if amount:
        await tx.execute("UPDATE clans SET treasury = treasury + ? WHERE id = ?", (amount, clan_id))


async def take_treasury(tx: Tx, clan_id: int, amount: int) -> bool:
    if amount <= 0:
        return True
    await tx.execute(
        "UPDATE clans SET treasury = treasury - ? WHERE id = ? AND treasury >= ?", (amount, clan_id, amount)
    )
    return tx.rowcount == 1


async def roster(tx: Tx, clan_id: int, before: int) -> list[Row]:
    """The members who fight this war: everybody who was in the clan when it started."""
    return await tx.fetchall(
        "SELECT m.player_id, m.role, p.display_name AS name, p.level AS level, p.platform_user_id AS platform_user_id"
        " FROM clan_members m JOIN players p ON p.id = m.player_id WHERE m.clan_id = ? AND m.joined_at <= ?"
        " ORDER BY p.level DESC, m.player_id",
        (clan_id, before),
    )


async def add_attack(
    tx: Tx, war_id: int, clan_id: int, attacker_id: int, attacker_name: str, target_id: int, target_name: str,
    stars: int, now: int,
) -> None:
    await tx.execute(
        "INSERT INTO clan_war_attacks (war_id, clan_id, attacker_id, attacker_name, target_id, target_name, stars, at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (war_id, clan_id, attacker_id, attacker_name, target_id, target_name, stars, now),
    )


async def attacks(tx: Tx, war_id: int) -> list[Row]:
    return await tx.fetchall("SELECT * FROM clan_war_attacks WHERE war_id = ? ORDER BY id", (war_id,))


async def release_clan(tx: Tx, clan_id: int) -> bool:
    """A clan is being closed: False while it is at war; its unanswered challenges are withdrawn (the stake goes back)."""
    war = await open_for(tx, clan_id)
    if war is None:
        return True
    if war["status"] == "active":
        return False
    if await close(tx, war["id"], "pending", "cancelled") and war["attacker_id"] != clan_id:
        await pay_treasury(tx, war["attacker_id"], war["stake"])
    return True
