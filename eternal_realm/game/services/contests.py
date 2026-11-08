"""Weekly contests: who did the most of something this week. Prizes are paid the week after."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import clans as clan_repo
from ...db.repos import wallet
from ...db.repos.wallet import DuplicateOperation
from ...shared.errors import GameError
from ..models import Player

#: contest id -> (emoji, title, the deeds that count)
CONTESTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "duel": ("⚔️", "بیشترین پیروزی دوئل", ("duel_win",)),
    "hunt": ("🏹", "بیشترین شکار هیولا", ("hunt",)),
    "boss": ("🐉", "بیشترین باس شکست‌خورده", ("boss_win",)),
    "mission": ("📅", "بیشترین مأموریت تمام‌شده", ("mission",)),
    "dungeon": ("🕳️", "بیشترین سیاه‌چال", ("dungeon", "dungeon_win")),
}
PRIZES = (1000, 600, 300)
TOP = 10


@dataclass
class Row:
    name: str
    uid: int
    count: int


@dataclass
class Standing:
    contest: str
    rows: list[Row]
    my_count: int
    my_place: int | None


async def count_deed(tx, player_id: int, deed: str, now: int) -> None:  # noqa: ANN001
    """Called for every deed (see season repo); only deeds some contest watches are stored."""
    for contest, (_, _, deeds) in CONTESTS.items():
        if deed in deeds:
            await tx.execute(
                "INSERT INTO weekly_stats (week, contest, player_id, count) VALUES (?, ?, ?, 1)"
                " ON CONFLICT (week, contest, player_id) DO UPDATE SET count = count + 1",
                (clan_repo.week_of(now), contest, player_id),
            )


class ContestService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def _rows(self, tx, contest: str, week: int, limit: int) -> list[Row]:  # noqa: ANN001
        rows = await tx.fetchall(
            "SELECT p.display_name AS name, p.platform_user_id AS uid, w.count FROM weekly_stats w"
            " JOIN players p ON p.id = w.player_id WHERE w.week = ? AND w.contest = ? AND p.banned = 0"
            " ORDER BY w.count DESC, w.player_id LIMIT ?",
            (week, contest, limit),
        )
        return [Row(r["name"], r["uid"], r["count"]) for r in rows]

    async def standing(self, player: Player, contest: str) -> Standing:
        if contest not in CONTESTS:
            raise GameError("این مسابقه وجود ندارد.")
        week = clan_repo.week_of(self.ctx.now())
        async with self.ctx.db.read() as tx:
            rows = await self._rows(tx, contest, week, TOP)
            mine = int(await tx.scalar(
                "SELECT count FROM weekly_stats WHERE week = ? AND contest = ? AND player_id = ?",
                (week, contest, player.id), 0))
            place = None
            if mine:
                place = 1 + int(await tx.scalar(
                    "SELECT COUNT(*) FROM weekly_stats WHERE week = ? AND contest = ? AND count > ?",
                    (week, contest, mine), 0))
        return Standing(contest, rows, mine, place)

    async def prizes(self, player: Player) -> list[tuple[str, int, int]]:
        """Unclaimed prizes from last week: ``(contest, place, gold)``."""
        week = clan_repo.week_of(self.ctx.now()) - 1
        out = []
        async with self.ctx.db.read() as tx:
            for contest in CONTESTS:
                top = await tx.fetchall(
                    "SELECT player_id FROM weekly_stats WHERE week = ? AND contest = ?"
                    " ORDER BY count DESC, player_id LIMIT 3", (week, contest))
                for place, r in enumerate(top):
                    if r["player_id"] != player.id:
                        continue
                    done = await tx.fetchone("SELECT 1 FROM transactions WHERE ref = ?", (f"contest:{week}:{contest}:{player.id}",))
                    if not done:
                        out.append((contest, place + 1, PRIZES[place]))
        return out

    async def claim(self, player: Player) -> int:
        now, week = self.ctx.now(), clan_repo.week_of(self.ctx.now()) - 1
        due = await self.prizes(player)
        if not due:
            raise GameError("جایزه‌ای برای گرفتن ندارید. هفته‌ی پیش در سه‌ی اول هیچ مسابقه‌ای نبودید، یا جایزه‌ها را گرفته‌اید.")
        total = 0
        async with self.ctx.db.transaction() as tx:
            for contest, place, gold in due:
                try:
                    await wallet.apply(tx, player.id, gold=gold, reason="contest", now=now,
                                       ref=f"contest:{week}:{contest}:{player.id}")
                except DuplicateOperation:
                    continue
                total += gold
                if place == 1:
                    await tx.execute("UPDATE players SET title = ? WHERE id = ?", (f"{CONTESTS[contest][1]} · هفته", player.id))
        return total
