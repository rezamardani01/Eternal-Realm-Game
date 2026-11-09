"""A hero who starts or joins a new fight leaves every request still open: pending duel invitations and lobby seats."""

from __future__ import annotations

from ..database import Tx


async def close_all(tx: Tx, player_id: int, now: int, keep_lobby: int | None = None, keep_duel: int | None = None) -> None:
    """Close the invitations the hero sent and leave (or, as the maker, cancel) team lobbies still waiting for fighters."""
    await tx.execute(
        "UPDATE duels SET status = 'expired', updated_at = ? WHERE status = 'pending' AND challenger_id = ? AND id != ?",
        (now, player_id, keep_duel or 0),
    )
    lobbies = await tx.fetchall(
        "SELECT b.id, b.creator_id FROM team_battles b JOIN team_battle_members m ON m.battle_id = b.id"
        " WHERE m.player_id = ? AND b.status = 'lobby' AND b.expires_at > ?", (player_id, now),
    )
    for row in lobbies:
        if row["id"] == keep_lobby:
            continue
        if row["creator_id"] == player_id:
            await tx.execute("UPDATE team_battles SET status = 'cancelled', updated_at = ? WHERE id = ?", (now, row["id"]))
        else:
            await tx.execute("DELETE FROM team_battle_members WHERE battle_id = ? AND player_id = ?", (row["id"], player_id))
