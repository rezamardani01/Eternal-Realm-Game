"""Queries on the ``players`` table."""

from __future__ import annotations

from ...game.models import Player
from ...shared.text import fa
from ..database import Tx


async def create(
    tx: Tx,
    *,
    platform_user_id: int,
    username: str | None,
    name: str,
    race: str,
    char_class: str,
    energy: int,
    gold: int,
    now: int,
) -> Player:
    player_id = await tx.execute(
        "INSERT INTO players (platform_user_id, username, display_name, race, class,"
        " energy, energy_at, gold, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (platform_user_id, username, name, race, char_class, energy, now, gold, now),
    )
    player = await get(tx, player_id)
    assert player is not None
    return player


async def get(tx: Tx, player_id: int) -> Player | None:
    row = await tx.fetchone("SELECT * FROM players WHERE id = ?", (player_id,))
    return Player.from_row(row) if row else None


async def get_by_platform(tx: Tx, platform_user_id: int) -> Player | None:
    row = await tx.fetchone("SELECT * FROM players WHERE platform_user_id = ?", (platform_user_id,))
    return Player.from_row(row) if row else None


async def get_by_name(tx: Tx, name: str) -> Player | None:
    row = await tx.fetchone("SELECT * FROM players WHERE display_name = ?", (name,))
    return Player.from_row(row) if row else None


async def name_taken(tx: Tx, name: str) -> bool:
    return await tx.fetchone("SELECT 1 FROM players WHERE display_name = ?", (name,)) is not None


async def set_energy(tx: Tx, player_id: int, energy: int, energy_at: int) -> None:
    await tx.execute(
        "UPDATE players SET energy = ?, energy_at = ? WHERE id = ?", (energy, energy_at, player_id)
    )


async def set_progress(tx: Tx, player_id: int, level: int, xp: int) -> None:
    await tx.execute("UPDATE players SET level = ?, xp = ? WHERE id = ?", (level, xp, player_id))


async def touch_username(tx: Tx, player_id: int, username: str | None) -> None:
    await tx.execute(
        "UPDATE players SET username = ? WHERE id = ? AND COALESCE(username, '') != COALESCE(?, '')",
        (username, player_id, username),
    )


async def set_banned(tx: Tx, player_id: int, banned: bool) -> None:
    await tx.execute("UPDATE players SET banned = ? WHERE id = ?", (int(banned), player_id))


async def record_result(tx: Tx, player_id: int, *, won: bool) -> None:
    column = "wins" if won else "losses"
    await tx.execute(f"UPDATE players SET {column} = {column} + 1 WHERE id = ?", (player_id,))  # noqa: S608


async def set_daily(tx: Tx, player_id: int, at: int, streak: int) -> None:
    await tx.execute(
        "UPDATE players SET daily_at = ?, daily_streak = ? WHERE id = ?", (at, streak, player_id)
    )


async def count(tx: Tx) -> int:
    return int(await tx.scalar("SELECT COUNT(*) FROM players", default=0))


async def is_away(tx: Tx, player_id: int, now: int) -> int:
    """Seconds until the hero is back from an expedition (0 when not away)."""
    ends = await tx.scalar("SELECT ends_at FROM expeditions WHERE player_id = ? AND ends_at > ?", (player_id, now), 0)
    return max(0, int(ends) - now) if ends else 0


def away_text(left: int, who: str | None = None) -> str:
    """The refusal shown to someone whose hero (or opponent) is away, with the exact time left."""
    hours, rest = divmod(left, 3600)
    minutes, seconds = divmod(rest, 60)
    units = [(hours, "ساعت"), (minutes, "دقیقه"), (seconds, "ثانیه")]
    parts = " و ".join(f"{fa(n)} {unit}" for i, (n, unit) in enumerate(units) if n or any(v for v, _ in units[:i]) or i == 2)
    if who is None:
        return f"🏕️ *قهرمان شما در اعزام است* و تا بازگشتش نمی‌تواند با بازیکنان دیگر مبارزه کند.\n\n⏳ {parts} دیگر برمی‌گردد."
    return f"🏕️ *{who}* در اعزام است و تا بازگشتش نمی‌شود با او مبارزه کرد.\n\n⏳ {parts} دیگر برمی‌گردد."
