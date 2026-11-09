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
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def sweep(self) -> None:
        """Queue the news that no action causes: a boost or a VIP subscription that has just run out."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
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
