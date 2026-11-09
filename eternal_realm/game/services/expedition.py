"""Expeditions: the hero is away for hours; the report and the prize are collected on return."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import duration, fa
from ..data import expedition as data
from ..data.items import get_item
from ..engine import loot
from ..models import Player
from .inventory import InventoryService
from .players import LevelUp, PlayerService


@dataclass
class Trip:
    kind: str
    started_at: int
    ends_at: int
    hours: int


@dataclass
class Report:
    kind: data.Kind
    hours: int
    lines: list[str]
    gold: int = 0
    xp: int = 0
    items: dict[str, int] = field(default_factory=dict)
    crystal: int = 0
    level_up: LevelUp | None = None


class ExpeditionService:
    def __init__(self, ctx: AppContext, players: PlayerService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory

    async def current(self, player_id: int) -> Trip | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM expeditions WHERE player_id = ?", (player_id,))
        return Trip(row["kind"], row["started_at"], row["ends_at"], row["hours"]) if row else None

    async def today(self, player_id: int) -> int:
        day = (self.ctx.now() + 12600) // 86400
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT n FROM solo_daily WHERE player_id = ? AND day = ? AND key = 'expedition'", (player_id, day), 0))

    async def start(self, player: Player, kind_id: str, hours: int) -> Trip:
        try:
            data.get_kind(kind_id)
        except KeyError:
            raise GameError("چنین اعزامی نیست.") from None
        if hours not in data.HOURS:
            raise GameError("این مدت وجود ندارد؛ ۱، ۴ یا ۸ ساعت.")
        now = self.ctx.now()
        day = (now + 12600) // 86400
        async with self.ctx.db.transaction() as tx:
            if await tx.scalar("SELECT 1 FROM expeditions WHERE player_id = ?", (player.id,), 0):
                raise GameError("قهرمان شما هم‌اکنون در اعزام است؛ اول گزارشش را بگیرید.")
            if await tx.scalar(
                "SELECT 1 FROM duels WHERE status IN ('pending', 'active') AND (challenger_id = ? OR target_id = ?)",
                (player.id, player.id), 0,
            ) or await tx.scalar(
                "SELECT 1 FROM team_battle_members m JOIN team_battles b ON b.id = m.battle_id"
                " WHERE m.player_id = ? AND (b.status = 'active' OR (b.status = 'lobby' AND b.expires_at > ?))", (player.id, now), 0,
            ):
                raise GameError("در یک مبارزه با بازیکنان دیگر هستید؛ اول آن را تمام کنید، بعد قهرمان را به اعزام بفرستید.")
            if not self.players.is_owner(player):
                used = int(await tx.scalar("SELECT n FROM solo_daily WHERE player_id = ? AND day = ? AND key = 'expedition'", (player.id, day), 0))
                if used >= data.DAILY_LIMIT:
                    raise GameError(f"هر روز فقط {fa(data.DAILY_LIMIT)} اعزام می‌شود؛ فردا دوباره بفرستید.")
            await tx.execute(
                "INSERT INTO solo_daily (player_id, day, key, n) VALUES (?, ?, 'expedition', 1)"
                " ON CONFLICT (player_id, day, key) DO UPDATE SET n = n + 1", (player.id, day),
            )
            await tx.execute(
                "INSERT INTO expeditions (player_id, kind, started_at, ends_at, hours) VALUES (?, ?, ?, ?, ?)",
                (player.id, kind_id, now, now + hours * 3600, hours),
            )
        return Trip(kind_id, now, now + hours * 3600, hours)

    @staticmethod
    def recall_cost(left_seconds: int) -> int:
        """Crystals to bring the hero home at once: one for every hour still to go (at least one)."""
        return max(1, -(-left_seconds // 3600))

    async def recall(self, player: Player) -> int:
        """Pay crystals and the hero is back now; the report is then collected as usual. Returns the price."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM expeditions WHERE player_id = ?", (player.id,))
            if row is None:
                raise GameError("قهرمان شما در اعزام نیست.")
            if row["ends_at"] <= now:
                raise GameError("قهرمان شما همین حالا هم برگشته؛ گزارشش را بگیرید.")
            cost = self.recall_cost(row["ends_at"] - now)
            await wallet.apply(tx, player.id, crystal=-cost, reason="expedition_recall", now=now)
            await tx.execute("UPDATE expeditions SET ends_at = ? WHERE player_id = ?", (now, player.id))
        return cost

    async def claim(self, player: Player) -> Report:
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM expeditions WHERE player_id = ?", (player.id,))
            if row is None:
                raise GameError("قهرمان شما در اعزام نیست.")
            if row["ends_at"] > now and not self.players.is_owner(player):
                raise GameError(f"قهرمان شما هنوز برنگشته؛ {duration(row['ends_at'] - now)} دیگر.")
            kind, hours = data.get_kind(row["kind"]), row["hours"]
            await tx.execute("DELETE FROM expeditions WHERE player_id = ?", (player.id,))
            level = int((await tx.scalar("SELECT level FROM players WHERE id = ?", (player.id,), player.level)))
            report = Report(kind, hours, [])
            boost = await self.players.boost_factor(tx, player.id)
            report.gold = round(kind.gold * hours * loot.level_scale(level) * rng.uniform(0.9, 1.1)) * boost
            report.xp = round(kind.xp * hours * loot.xp_scale(level) * rng.uniform(0.9, 1.1)) * boost
            for item_id, per_hour, chance in kind.items:
                if rng.random() <= chance:
                    qty = max(1, round(per_hour * hours * rng.uniform(0.8, 1.2))) if per_hour >= 1 else int(rng.random() < per_hour * hours)
                    if qty:
                        report.items[item_id] = qty * boost
            for text, chance in kind.finds:
                if rng.random() < chance:
                    report.lines.append(text)
                    if rng.random() < 0.3:
                        report.crystal += 1
            if report.gold or report.crystal:
                await wallet.apply(tx, player.id, gold=report.gold, crystal=report.crystal, reason="expedition", now=now)
            for item_id, qty in report.items.items():
                await self.inventory.grant(tx, player.id, item_id, qty, origin="expedition")
            if report.xp:
                report.level_up = await self.players.grant_xp(tx, player.id, report.xp)
            summary = []
            if report.gold:
                summary.append(f"کسب {fa(report.gold)} سکه")
            if report.xp:
                summary.append(f"کسب {fa(report.xp)} تجربه‌ی تمرینی")
            summary += [f"جمع‌آوری {fa(q)} عدد {get_item(i).name}" for i, q in report.items.items()]
            report.lines = summary + report.lines
            return report
