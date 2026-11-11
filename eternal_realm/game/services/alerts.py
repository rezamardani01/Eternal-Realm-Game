"""Delivery side of the heroes' own messages (see :mod:`..notify`)."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...shared.text import fa
from ..data.expedition import get_kind
from ..notify import queue


async def queue_once(tx, player_id: int, key: str, now: int) -> bool:  # noqa: ANN001 - Tx
    """The daily gift is ready: one message per gift."""
    if await tx.scalar("SELECT 1 FROM player_alerts WHERE player_id = ? AND key = ?", (player_id, key), 0):
        return False
    await queue(
        tx, player_id, key,
        "🎁 *گنجینه‌ی روزانه‌تان آماده است!*\n\nامروز هم سر بزنید و جایزه‌تان را بردارید؛ پشت‌سرهم گرفتنش جایزه را بزرگ‌تر می‌کند.",
        now, "daily",
    )
    return True


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
        self._waiting_at = 0

    async def sweep(self) -> None:
        """Queue the news that no action causes: a boost or a VIP subscription that has just run out, a hero back from away."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            for r in await tx.fetchall("SELECT player_id, started_at, kind, hours FROM expeditions WHERE ends_at <= ?", (now,)):
                try:
                    kind = get_kind(r["kind"])
                    where = f"{kind.emoji} {kind.name}"
                except KeyError:
                    where = "اعزام"
                await queue(
                    tx, r["player_id"], f"expedition:{r['started_at']}",
                    "🏕️ *قهرمان شما از اعزام برگشت!*\n\n"
                    f"📍 مأموریت: {where}\n"
                    f"⏳ مدت: {fa(r['hours'])} ساعت\n\n"
                    "🎁 گزارش و پاداشش آماده است؛ همین حالا بگیرید.", now, "expd",
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

    async def waiting(self) -> int:
        """«Your hero is waiting»: the energy bar is full again, the daily gift can be taken. Returns how many were queued."""
        from ..engine import progression

        now = self.ctx.now()
        hour = ((now + 12600) % 86400) // 3600
        if hour >= 23 or hour < 8 or now - self._waiting_at < 240:
            return 0
        self._waiting_at = now
        balance = self.ctx.balance
        queued = 0
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT id, level, energy, energy_at, daily_at FROM players WHERE banned = 0 AND offers_off = 0 AND energy_at >= ?"
                " ORDER BY id LIMIT 500", (now - 3 * 86400,),
            )
            for r in rows:
                cap = progression.max_energy(r["level"], balance)
                if r["energy"] < cap and progression.regen_energy(r["energy"], r["energy_at"], now, r["level"], balance)[0] >= cap:
                    recent = await tx.scalar(
                        "SELECT 1 FROM player_alerts WHERE player_id = ? AND key LIKE 'energyfull:%' AND created_at > ?",
                        (r["id"], now - 8 * 3600), 0,
                    )
                    if not recent:
                        await queue(
                            tx, r["id"], f"energyfull:{r['energy_at']}",
                            f"⚡ *انرژی‌تان پر شد!*\n\nنوار انرژی {fa(cap)} تایی کامل است؛ قهرمانتان آماده‌ی ماجراجویی است.", now, "adv",
                        )
                        queued += 1
                since = now - r["daily_at"]
                if r["daily_at"] and 86400 <= since < 4 * 86400:
                    ready = await queue_once(tx, r["id"], f"dailyready:{r['daily_at']}", now)
                    queued += 1 if ready else 0
        return queued

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
