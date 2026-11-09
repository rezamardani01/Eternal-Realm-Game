"""Delivery side of the heroes' own messages (see :mod:`..notify`)."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ..notify import queue


@dataclass
class Alert:
    uid: int
    text: str
    screen: str = ""
    arg: str = ""


class AlertService:
    def __init__(self, ctx: AppContext, players=None) -> None:  # noqa: ANN001 - PlayerService
        self.ctx = ctx
        self.players = players
        self._tips_at = 0

    async def sweep(self) -> None:
        """Queue the news that no action causes: a boost or a VIP subscription that has just run out, a hero back from away."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            for r in await tx.fetchall("SELECT player_id, started_at FROM expeditions WHERE ends_at <= ?", (now,)):
                await queue(
                    tx, r["player_id"], f"expedition:{r['started_at']}",
                    "🏕️ *قهرمان شما از اعزام برگشت!*\n\nگزارش و پاداشش آماده است؛ همین حالا بگیرید.", now, "expd",
                )
            for column, name, emoji in (("boost_until", "بوست دو برابر", "🚀"), ("vip_until", "اشتراک VIP", "💠")):
                rows = await tx.fetchall(
                    f"SELECT id, {column} AS until FROM players WHERE {column} > ? AND {column} <= ?",  # noqa: S608
                    (now - 86400, now),
                )
                for r in rows:
                    await queue(
                        tx, r["id"], f"{column}:{r['until']}", f"{emoji} *{name} شما تمام شد.*\n\n"
                        "هر وقت خواستید از «خزانه قلمرو» دوباره فعالش کنید.", now, "premium",
                    )

    async def tips(self, advisor) -> int:  # noqa: ANN001 - AdvisorService
        """One friendly suggestion a day for every recently active hero (never at night). Returns how many were queued."""
        now = self.ctx.now()
        if now - self._tips_at < 600:
            return 0
        self._tips_at = now
        hour = ((now + 12600) % 86400) // 3600
        if hour >= 23 or hour < 8:
            return 0
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT id FROM players WHERE banned = 0 AND energy_at > ? AND NOT EXISTS"
                " (SELECT 1 FROM player_alerts a WHERE a.player_id = players.id AND a.key LIKE 'tip:%' AND a.created_at > ?)"
                " ORDER BY id LIMIT 100",
                (now - 3 * 86400, now - 20 * 3600),
            )
        queued = 0
        for r in rows:
            player = await self.players.get(r["id"])
            if player is None:
                continue
            tips = await advisor.for_player(player, 1)
            if not tips:
                continue
            tip = tips[0]
            async with self.ctx.db.transaction() as tx:
                await queue(
                    tx, player.id, f"tip:{(now + 12600) // 86400}",
                    f"💡 *پیشنهاد فرمانده*\n\n{tip.emoji} {tip.text}", now, tip.screen, tip.arg,
                )
            queued += 1
        return queued

    async def pending(self, limit: int = 100) -> list[Alert]:
        """Messages waiting to be sent; each is handed out once."""
        out: list[Alert] = []
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT a.id, a.text, a.screen, a.arg, p.platform_user_id AS uid FROM player_alerts a"
                " JOIN players p ON p.id = a.player_id WHERE a.sent = 0 AND p.banned = 0 ORDER BY a.id LIMIT ?",
                (limit,),
            )
            for r in rows:
                out.append(Alert(r["uid"], r["text"], r["screen"], r["arg"]))
                await tx.execute("UPDATE player_alerts SET sent = 1 WHERE id = ?", (r["id"],))
        return out
