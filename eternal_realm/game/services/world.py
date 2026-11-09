"""The living world: lazily updated regions and one world event at a time. No loop simulates anything."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.text import fa
from ..data import world as data
from ..engine import loot
from ..notify import queue
from .inventory import InventoryService
from .players import PlayerService


@dataclass
class RegionView:
    region: data.Region
    darkness: float

    @property
    def status(self) -> str:
        return data.status_of(self.darkness)


@dataclass
class EventView:
    id: int
    kind: data.EventKind
    points: int
    max_points: int
    ends_at: int
    status: str
    top: list[tuple[str, int]] = field(default_factory=list)
    mine: int = 0


class WorldService:
    def __init__(self, ctx: AppContext, players: PlayerService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory

    # --- regions -------------------------------------------------------------------------------------------------
    async def _darkness(self, tx: Tx, region: str) -> float:
        """Bring one region up to date (darkness creeps on while nobody looks) and return its darkness."""
        now = self.ctx.now()
        row = await tx.fetchone("SELECT darkness, calc FROM world_regions WHERE id = ?", (region,))
        if row is None:
            await tx.execute("INSERT INTO world_regions (id, darkness, calc) VALUES (?, ?, ?)", (region, data.START_DARKNESS, now))
            return data.START_DARKNESS
        value = min(100.0, row["darkness"] + max(0, now - row["calc"]) / 3600 * data.DARKNESS_PER_HOUR)
        await tx.execute("UPDATE world_regions SET darkness = ?, calc = ? WHERE id = ?", (value, now, region))
        return value

    async def effect(self, tx: Tx, region: str) -> tuple[float, float]:
        return data.effect_of(await self._darkness(tx, region))

    async def relieve(self, tx: Tx, region: str, amount: float) -> None:
        value = await self._darkness(tx, region)
        await tx.execute("UPDATE world_regions SET darkness = ? WHERE id = ?", (max(0.0, value - amount), region))

    async def regions(self) -> list[RegionView]:
        async with self.ctx.db.transaction() as tx:
            return [RegionView(r, await self._darkness(tx, r.id)) for r in data.REGIONS]

    # --- events --------------------------------------------------------------------------------------------------
    async def tick(self) -> None:
        """Close an event that is over and open the next one when it is time."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM world_events WHERE status = 'active' LIMIT 1")
            if row is not None:
                if row["points"] >= row["max_points"] or row["ends_at"] <= now:
                    await self._settle(tx, row["id"])
                return
            last = await tx.fetchone("SELECT kind, ends_at FROM world_events ORDER BY id DESC LIMIT 1")
            if last is not None and now - last["ends_at"] < data.GAP_HOURS * 3600:
                return
            kinds = [k for k in data.EVENT_KINDS if last is None or k.id != last["kind"]]
            kind = self.ctx.rng.choice(kinds)
            await tx.execute(
                "INSERT INTO world_events (kind, region, foe, max_points, points, starts_at, ends_at, status)"
                " VALUES (?, ?, ?, ?, 0, ?, ?, 'active')",
                (kind.id, kind.region, kind.foe, data.EVENT_POINTS, now, now + data.EVENT_HOURS * 3600),
            )

    async def active(self, player_id: int | None = None) -> EventView | None:
        await self.tick()
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM world_events WHERE status = 'active' LIMIT 1")
            if row is None:
                return None
            return await self._view(tx, row, player_id)

    async def last_result(self) -> EventView | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM world_events WHERE status != 'active' ORDER BY id DESC LIMIT 1")
            return await self._view(tx, row, None) if row else None

    async def _view(self, tx: Tx, row, player_id: int | None) -> EventView:  # noqa: ANN001
        top = [
            (r["display_name"], r["points"]) for r in await tx.fetchall(
                "SELECT p.display_name, c.points FROM world_contrib c JOIN players p ON p.id = c.player_id"
                " WHERE c.event_id = ? ORDER BY c.points DESC LIMIT 3", (row["id"],),
            )
        ]
        mine = int(await tx.scalar(
            "SELECT points FROM world_contrib WHERE event_id = ? AND player_id = ?", (row["id"], player_id or 0), 0
        ))
        return EventView(row["id"], data.get_kind(row["kind"]), row["points"], row["max_points"], row["ends_at"], row["status"], top, mine)

    async def contribute(self, tx: Tx, event_id: int, player_id: int, points: int) -> list[str]:
        """Add a hero's share to the event; the event is settled the moment it is full."""
        row = await tx.fetchone("SELECT * FROM world_events WHERE id = ?", (event_id,))
        if row is None or row["status"] != "active" or row["ends_at"] <= self.ctx.now():
            return ["این رویداد تمام شده بود؛ سهمتان ثبت نشد."]
        await tx.execute(
            "INSERT INTO world_contrib (event_id, player_id, points) VALUES (?, ?, ?)"
            " ON CONFLICT (event_id, player_id) DO UPDATE SET points = points + excluded.points", (event_id, player_id, points),
        )
        await tx.execute("UPDATE world_events SET points = points + ? WHERE id = ?", (points, event_id))
        notes = [f"سهم شما در رویداد جهانی: {fa(points)} امتیاز"]
        if row["points"] + points >= row["max_points"]:
            await self._settle(tx, event_id)
            notes.append("رویداد با همت همه به پایان رسید! پاداش‌ها فرستاده شد.")
        return notes

    async def _settle(self, tx: Tx, event_id: int) -> None:
        row = await tx.fetchone("SELECT * FROM world_events WHERE id = ?", (event_id,))
        if row is None or row["status"] != "active":
            return
        now = self.ctx.now()
        won = row["points"] >= row["max_points"]
        # an event finished early ends now, so the pause before the next one counts from the real end
        await tx.execute(
            "UPDATE world_events SET status = ?, ends_at = MIN(ends_at, ?) WHERE id = ?", ("won" if won else "lost", now, event_id)
        )
        kind = data.get_kind(row["kind"])
        await self.relieve(tx, row["region"], 30) if won else await self._darken(tx, row["region"], 25)
        contributors = await tx.fetchall(
            "SELECT c.player_id, c.points, p.level FROM world_contrib c JOIN players p ON p.id = c.player_id"
            " WHERE c.event_id = ? ORDER BY c.points DESC", (event_id,),
        )
        for rank, c in enumerate(contributors):
            level = c["level"]
            gold = round((400 if won else 100) * loot.level_scale(level))
            xp = round((300 if won else 60) * loot.xp_scale(level))
            crystal = (2 if won else 0) + ((5, 3, 2)[rank] if won and rank < 3 else 0)
            await wallet.apply(tx, c["player_id"], gold=gold, crystal=crystal, reason="world_event", now=now, ref=f"world:{event_id}:{c['player_id']}")
            await self.players.grant_xp(tx, c["player_id"], xp)
            lines = [f"🪙 {fa(gold)} سکه", f"⭐ {fa(xp)} تجربه"]
            if crystal:
                lines.append(f"💎 {fa(crystal)} کریستال")
            if won and rank == 0:
                await self.inventory.grant(tx, c["player_id"], "magic_chest", 1, origin="world")
                lines.append("🎁 صندوقچه‌ی جادویی (برای برترین مشارکت‌کننده)")
            head = (
                f"🌍 *{kind.title} به پایان رسید!*\n\nبا همت فرمانروایان، خطر دفع شد و منطقه نفس کشید." if won
                else f"🌍 *{kind.title} فروکش کرد*\n\nزمان تمام شد و خطر دفع نشد؛ تاریکی منطقه بیشتر شد. تلاش شما بی‌پاداش نماند."
            )
            await queue(
                tx, c["player_id"], f"world:{event_id}", f"{head}\n\nسهم شما: {fa(c['points'])} امتیاز (رتبه‌ی {fa(rank + 1)})\n" + "\n".join(lines),
                now, "world",
            )

    async def _darken(self, tx: Tx, region: str, amount: float) -> None:
        value = await self._darkness(tx, region)
        await tx.execute("UPDATE world_regions SET darkness = ? WHERE id = ?", (min(100.0, value + amount), region))
