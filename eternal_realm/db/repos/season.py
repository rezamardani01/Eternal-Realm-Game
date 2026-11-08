"""Queries on ``season_progress`` and ``season_claims``."""

from __future__ import annotations

from ...game.data.season import POINTS, PathState, season_of
from ..database import Tx


async def add_points(tx: Tx, player_id: int, deed: str, now: int) -> int:
    """Credit the path points of a deed. Returns the points added (0 for an unknown deed)."""
    points = POINTS.get(deed, 0)
    if not points:
        return 0
    await tx.execute(
        "INSERT INTO season_progress (player_id, season, points, premium) VALUES (?, ?, ?, 0)"
        " ON CONFLICT (player_id, season) DO UPDATE SET points = points + excluded.points",
        (player_id, season_of(now), points),
    )
    return points


async def state(tx: Tx, player_id: int, now: int) -> PathState:
    season = season_of(now)
    row = await tx.fetchone(
        "SELECT points, premium FROM season_progress WHERE player_id = ? AND season = ?", (player_id, season)
    )
    claims = await tx.fetchall(
        "SELECT track, tier FROM season_claims WHERE player_id = ? AND season = ?", (player_id, season)
    )
    return PathState(
        season, row["points"] if row else 0, bool(row["premium"]) if row else False,
        {(r["track"], r["tier"]) for r in claims},
    )


async def grant_ticket(tx: Tx, player_id: int, now: int) -> bool:
    """Mark the current season's ticket as bought. ``False`` when it already was."""
    season = season_of(now)
    await tx.execute(
        "INSERT INTO season_progress (player_id, season, points, premium) VALUES (?, ?, 0, 1)"
        " ON CONFLICT (player_id, season) DO UPDATE SET premium = 1 WHERE premium = 0",
        (player_id, season),
    )
    return tx.rowcount == 1
