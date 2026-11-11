"""The ranked season (فصل رتبه‌بندی): four weeks of earning experience, then a ladder, prizes and lasting titles.

Every point of experience a hero earns counts. When a season ends the best ten are rewarded, get a lasting title and
the board starts again from zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import titles
from ...db.repos import wallet
from ...shared.text import fa
from .. import notify
from .inventory import InventoryService

SEASON_DAYS = 28
#: (crystals, chest) by rank, first to tenth
PRIZES: tuple[tuple[int, str], ...] = (
    (30, "royal_chest"), (20, "royal_chest"), (15, "magic_chest"), (10, "magic_chest"), (10, "magic_chest"),
    (6, "magic_chest"), (6, "magic_chest"), (6, "wooden_chest"), (6, "wooden_chest"), (6, "wooden_chest"),
)
MEDALS = ("🥇", "🥈", "🥉")


def day_of(now: int) -> int:
    return (now + 12600) // 86400


def season_of(now: int) -> int:
    return day_of(now) // SEASON_DAYS


#: the first season people see is called «1»: seasons are counted from this one
FIRST_SEASON = 727


def label(number: int) -> int:
    """The number shown to players for a season."""
    return max(1, number - FIRST_SEASON + 1)


def season_end(number: int) -> int:
    """The moment (a Unix time) the season starts counting its last second: midnight Tehran of the next season's first day."""
    return (number + 1) * SEASON_DAYS * 86400 - 12600


@dataclass
class Row:
    rank: int
    player_id: int
    name: str
    score: int
    level: int


@dataclass
class Standing:
    number: int
    ends_in: int
    top: list[Row]
    mine: Row | None


async def add_score(tx: Tx, player_id: int, points: int, now: int) -> None:
    """Count experience earned toward the running season (called whenever a hero earns experience)."""
    if points <= 0:
        return
    await tx.execute(
        "INSERT INTO rank_scores (season, player_id, score) VALUES (?, ?, ?)"
        " ON CONFLICT (season, player_id) DO UPDATE SET score = score + excluded.score",
        (season_of(now), player_id, points),
    )


class LadderService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    # --- reading ----------------------------------------------------------------------------------
    async def _top(self, tx: Tx, number: int, limit: int) -> list[Row]:
        rows = await tx.fetchall(
            "SELECT r.player_id, r.score, p.display_name AS name, p.level AS level FROM rank_scores r"
            " JOIN players p ON p.id = r.player_id WHERE r.season = ? AND p.banned = 0"
            " ORDER BY r.score DESC, r.player_id LIMIT ?", (number, limit),
        )
        return [Row(i, r["player_id"], r["name"], r["score"], r["level"]) for i, r in enumerate(rows, 1)]

    async def standing(self, player_id: int | None = None, limit: int = 10) -> Standing:
        now = self.ctx.now()
        number = season_of(now)
        async with self.ctx.db.read() as tx:
            top = await self._top(tx, number, limit)
            mine = None
            if player_id is not None:
                row = await tx.fetchone(
                    "SELECT r.score, p.display_name AS name, p.level AS level FROM rank_scores r JOIN players p ON p.id = r.player_id"
                    " WHERE r.season = ? AND r.player_id = ?", (number, player_id),
                )
                if row is not None:
                    ahead = int(await tx.scalar(
                        "SELECT COUNT(*) FROM rank_scores r JOIN players p ON p.id = r.player_id WHERE r.season = ? AND p.banned = 0"
                        " AND (r.score > ? OR (r.score = ? AND r.player_id < ?))",
                        (number, row["score"], row["score"], player_id), 0,
                    ))
                    mine = Row(ahead + 1, player_id, row["name"], row["score"], row["level"])
        return Standing(number, max(0, season_end(number) - now), top, mine)

    # --- the season ends ----------------------------------------------------------------------------
    async def close_due(self) -> int:
        """Pay out every season that has ended since the last time. Returns how many were closed."""
        now = self.ctx.now()
        current = season_of(now)
        closed = 0
        async with self.ctx.db.transaction() as tx:
            seen = await tx.scalar("SELECT value FROM app_settings WHERE key = 'ladder_closed'", (), None)
            last = int(seen) if seen is not None else current - 1
            for number in range(last + 1, current):
                await self._close(tx, number, now)
                closed += 1
            if seen is None or closed or last != current - 1:
                await tx.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('ladder_closed', ?)"
                    " ON CONFLICT (key) DO UPDATE SET value = excluded.value", (str(current - 1),),
                )
        return closed

    async def _close(self, tx: Tx, number: int, now: int) -> None:
        from ..data.items import get_item

        winners = await self._top(tx, number, len(PRIZES))
        for row in winners:
            crystal, chest = PRIZES[row.rank - 1]
            await wallet.apply(
                tx, row.player_id, crystal=crystal, reason="ladder", now=now, ref=f"ladder:{number}:{row.player_id}"
            )
            await self.inventory.grant(tx, row.player_id, chest, 1, origin="ladder")
            medal = MEDALS[row.rank - 1] if row.rank <= 3 else "🎖️"
            await titles.award(tx, row.player_id, f"ladder:{number}", f"{medal} رتبه‌ی {fa(row.rank)} فصل {fa(label(number))}", now)
            await notify.queue(
                tx, row.player_id, f"ladder:{number}",
                f"🏆 *فصل رتبه‌بندی {fa(label(number))} تمام شد*\n\n"
                f"{medal} شما در رتبه‌ی {bold_rank(row.rank)} ایستادید با {fa(row.score)} امتیاز.\n\n"
                f"🎁 جایزه: 💎 {fa(crystal)} کریستال و {get_item(chest).name}\n"
                f"🏅 عنوان «رتبه‌ی {fa(row.rank)} فصل {fa(label(number))}» برای همیشه در پروفایل شماست.\n\n"
                "فصل تازه شروع شد؛ دوباره از صفر می‌دوید!", now, "rseason",
            )


def bold_rank(rank: int) -> str:
    return fa(rank)
