"""Leaderboards: global (level, wealth, wins) and per group (activity points)."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import groups as group_repo
from ..data.classes import CLASSES
from ..data.races import RACES
from ..models import Player

#: board id -> (title, SQL ordering, value column, value label)
BOARDS: dict[str, tuple[str, str, str, str]] = {
    "level": ("🏆 برترین سطح‌ها", "level DESC, xp DESC", "level", "سطح"),
    "rich": ("💰 ثروتمندترین‌ها", "gold DESC, level DESC", "gold", "🪙"),
    "wins": ("⚔️ قهرمانان دوئل", "wins DESC, level DESC", "wins", "پیروزی"),
}


@dataclass
class Entry:
    name: str
    badge: str
    value: int
    level: int


@dataclass
class Board:
    title: str
    unit: str
    entries: list[Entry]
    my_position: int | None = None


class RankingService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def global_board(self, board: str, me: Player | None = None, limit: int = 10) -> Board:
        title, order, column, unit = BOARDS[board]
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                f"SELECT display_name, race, class, level, {column} AS value FROM players"  # noqa: S608
                f" WHERE banned = 0 ORDER BY {order} LIMIT ?",
                (limit,),
            )
            position = None
            if me is not None:
                position = 1 + int(
                    await tx.scalar(
                        f"SELECT COUNT(*) FROM players WHERE banned = 0 AND {column} > ?",  # noqa: S608
                        (getattr(me, column),),
                        0,
                    )
                )
        entries = [
            Entry(r["display_name"], _badge(r["race"], r["class"]), r["value"], r["level"]) for r in rows
        ]
        return Board(title, unit, entries, position)

    async def group_board(self, chat_id: int, limit: int = 10) -> Board:
        rows = await _top(self.ctx, chat_id, limit)
        entries = [
            Entry(r["display_name"], _badge(r["race"], r["class"]), r["points"], r["level"]) for r in rows
        ]
        return Board("🏰 فعال‌ترین‌های این گروه", "امتیاز", entries)


async def _top(ctx: AppContext, chat_id: int, limit: int):  # noqa: ANN202
    async with ctx.db.read() as tx:
        return await group_repo.top_members(tx, chat_id, limit)


def _badge(race_id: str, class_id: str) -> str:
    return f"{RACES[race_id].emoji}{CLASSES[class_id].emoji}"
