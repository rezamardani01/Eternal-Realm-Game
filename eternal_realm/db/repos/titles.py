"""Lasting badges a hero collects (``player_titles``); the newest one is also shown as the profile's honor line."""

from __future__ import annotations

from ..database import Row, Tx


async def award(tx: Tx, player_id: int, key: str, text: str, now: int) -> bool:
    """Give a badge once. Returns whether it is new. The hero's honor line shows it when they have none yet."""
    await tx.execute(
        "INSERT OR IGNORE INTO player_titles (player_id, key, text, at) VALUES (?, ?, ?, ?)", (player_id, key, text, now)
    )
    if tx.rowcount == 0:
        return False
    await tx.execute("UPDATE players SET title = ? WHERE id = ? AND title = ''", (text, player_id))
    return True


async def of_player(tx: Tx, player_id: int, limit: int = 12) -> list[Row]:
    return await tx.fetchall(
        "SELECT key, text, at FROM player_titles WHERE player_id = ? ORDER BY at DESC, rowid DESC LIMIT ?", (player_id, limit)
    )
