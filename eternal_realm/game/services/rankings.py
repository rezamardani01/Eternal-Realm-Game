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
    "level": ("🏆 تالار بزرگان (بالاترین سطح)", "level DESC, xp DESC", "level", "سطح"),
    "rich": ("💰 تالار ثروتمندان", "gold DESC, level DESC", "gold", "🪙"),
    "wins": ("⚔️ تالار قهرمانان دوئل", "wins DESC, level DESC", "wins", "پیروزی"),
    "rating": ("🏅 لیگ مبارزان", "rating DESC, level DESC", "rating", "امتیاز"),
}


@dataclass
class Entry:
    name: str
    badge: str
    value: int
    level: int
    uid: int = 0

    @property
    def mention(self) -> str:
        return f"[{self.name}](uid:{self.uid})" if self.uid else self.name


@dataclass
class Board:
    title: str
    unit: str
    entries: list[Entry]
    my_position: int | None = None


@dataclass
class BattleRecord:
    boss_name: str
    boss_emoji: str
    won: bool
    ended_at: int
    fighters: int
    top_name: str
    top_damage: int


class RankingService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def global_board(self, board: str, me: Player | None = None, limit: int = 10) -> Board:
        title, order, column, unit = BOARDS[board]
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                f"SELECT display_name, platform_user_id AS uid, race, class, level, {column} AS value FROM players"  # noqa: S608
                f" WHERE banned = 0 ORDER BY {order} LIMIT ?",
                (limit,),
            )
            position = None
            if me is not None:
                position = 1 + int(
                    await tx.scalar(
                        f"SELECT COUNT(*) FROM players WHERE banned = 0 AND {column} >"  # noqa: S608
                        f" (SELECT {column} FROM players WHERE id = ?)",
                        (me.id,),
                        0,
                    )
                )
        entries = [
            Entry(r["display_name"], _badge(r["race"], r["class"]), r["value"], r["level"], r["uid"]) for r in rows
        ]
        return Board(title, unit, entries, position)

    async def path_board(self, me: Player | None = None, limit: int = 10) -> Board:
        """The season's hero path: whoever has climbed to the highest tier is first."""
        from ..data.season import POINTS_PER_TIER, TIERS, season_of

        season = season_of(self.ctx.now())
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.display_name, p.platform_user_id AS uid, p.race, p.class, p.level, s.points AS points"
                " FROM season_progress s JOIN players p ON p.id = s.player_id"
                " WHERE s.season = ? AND p.banned = 0 AND s.points >= ? ORDER BY s.points DESC, p.level DESC LIMIT ?",
                (season, POINTS_PER_TIER, limit),
            )
            position = None
            if me is not None:
                mine = int(await tx.scalar(
                    "SELECT points FROM season_progress WHERE player_id = ? AND season = ?", (me.id, season), 0
                ))
                if mine >= POINTS_PER_TIER:
                    position = 1 + int(await tx.scalar(
                        "SELECT COUNT(*) FROM season_progress s JOIN players p ON p.id = s.player_id"
                        " WHERE s.season = ? AND p.banned = 0 AND s.points > ?", (season, mine), 0,
                    ))
        entries = [
            Entry(r["display_name"], _badge(r["race"], r["class"]), min(TIERS, r["points"] // POINTS_PER_TIER), r["level"], r["uid"])
            for r in rows
        ]
        return Board("🎟️ تالار مسیر قهرمانی (این فصل)", "مرحله", entries, position)

    async def boss_hunters(self, me: Player | None = None, limit: int = 10) -> Board:
        """Everybody's total damage against group bosses."""
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.display_name, p.platform_user_id AS uid, p.race, p.class, p.level, SUM(h.damage) AS value FROM boss_hits h"
                " JOIN players p ON p.id = h.player_id WHERE p.banned = 0 GROUP BY p.id"
                " HAVING value > 0 ORDER BY value DESC LIMIT ?",
                (limit,),
            )
            position = None
            if me is not None:
                mine = int(await tx.scalar("SELECT COALESCE(SUM(damage), 0) FROM boss_hits WHERE player_id = ?", (me.id,), 0))
                if mine:
                    position = 1 + int(
                        await tx.scalar(
                            "SELECT COUNT(*) FROM (SELECT SUM(damage) AS t FROM boss_hits GROUP BY player_id"
                            " HAVING t > ?)", (mine,), 0,
                        )
                    )
        entries = [Entry(r["display_name"], _badge(r["race"], r["class"]), r["value"], r["level"], r["uid"]) for r in rows]
        return Board("🐉 شکارچیان باس (کل آسیب)", "آسیب", entries, position)

    async def hero_of_the_week(self, chat_id: int, limit: int = 5) -> Board:
        """Who hurt this group's bosses the most during the last seven days."""
        since = self.ctx.now() - 7 * 86400
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.display_name, p.platform_user_id AS uid, p.race, p.class, p.level, SUM(h.damage) AS value FROM boss_hits h"
                " JOIN bosses b ON b.id = h.boss_id JOIN players p ON p.id = h.player_id"
                " WHERE b.chat_id = ? AND b.created_at >= ? GROUP BY p.id HAVING value > 0"
                " ORDER BY value DESC LIMIT ?",
                (chat_id, since, limit),
            )
        entries = [Entry(r["display_name"], _badge(r["race"], r["class"]), r["value"], r["level"], r["uid"]) for r in rows]
        return Board("🌟 قهرمانان این هفته", "آسیب", entries)

    async def battle_history(self, chat_id: int, limit: int = 5) -> list[BattleRecord]:
        from ..data.bosses import boss_by_id

        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT id, boss_type, status, ended_at FROM bosses WHERE chat_id = ? AND status != 'active'"
                " ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            )
            records = []
            for row in rows:
                fighters = await tx.fetchall(
                    "SELECT p.display_name AS name, p.platform_user_id AS uid, h.damage FROM boss_hits h JOIN players p ON p.id = h.player_id"
                    " WHERE h.boss_id = ? ORDER BY h.damage DESC", (row["id"],),
                )
                kind = boss_by_id(row["boss_type"])
                top = fighters[0] if fighters else None
                records.append(
                    BattleRecord(
                        kind.name, kind.emoji, row["status"] == "defeated", row["ended_at"] or 0, len(fighters),
                        f"[{top['name']}](uid:{top['uid']})" if top else "-", top["damage"] if top else 0,
                    )
                )
        return records

    async def group_board(self, chat_id: int, limit: int = 10) -> Board:
        rows = await _top(self.ctx, chat_id, limit)
        entries = [
            Entry(r["display_name"], _badge(r["race"], r["class"]), r["points"], r["level"], r["uid"]) for r in rows
        ]
        return Board("🏰 دلاورترین‌های همین گروه", "امتیاز", entries)


async def _top(ctx: AppContext, chat_id: int, limit: int):  # noqa: ANN202
    async with ctx.db.read() as tx:
        return await group_repo.top_members(tx, chat_id, limit)


def _badge(race_id: str, class_id: str) -> str:
    return f"{RACES[race_id].emoji}{CLASSES[class_id].emoji}"
