"""Operator tools. Every action is written to ``admin_log``."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import groups as group_repo
from ...db.repos import orders as order_repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.items import Item
from ..engine import progression
from ..models import Player
from .inventory import InventoryService


@dataclass
class Stats:
    players: int
    groups: int
    active_duels: int
    orders: int
    revenue_rial: int
    gold_in_circulation: int


class AdminService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def _log(self, tx, admin_id: int, action: str, detail: str) -> None:  # noqa: ANN001
        await tx.execute(
            "INSERT INTO admin_log (admin_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (admin_id, action, detail, self.ctx.now()),
        )

    async def _find(self, tx, name: str) -> Player:  # noqa: ANN001
        player = await player_repo.get_by_name(tx, name.strip())
        if player is None:
            raise GameError(f"بازیکنی با نام «{name.strip()}» پیدا نشد.")
        return player

    async def stats(self) -> Stats:
        async with self.ctx.db.read() as tx:
            order_row = await order_repo.stats(tx)
            return Stats(
                players=await player_repo.count(tx),
                groups=await group_repo.count_groups(tx),
                active_duels=int(await tx.scalar("SELECT COUNT(*) FROM duels WHERE status = 'active'", default=0)),
                orders=int(order_row["delivered"]) if order_row else 0,
                revenue_rial=int(order_row["revenue"]) if order_row else 0,
                gold_in_circulation=int(await tx.scalar("SELECT SUM(gold) FROM players", default=0)),
            )

    async def give_currency(self, admin_id: int, name: str, *, gold: int = 0, crystal: int = 0) -> Player:
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await wallet.apply(tx, player.id, gold=gold, crystal=crystal, reason="admin", now=self.ctx.now())
            await self._log(tx, admin_id, "give_currency", f"{player.name} gold={gold} crystal={crystal}")
            return player

    async def give_item(self, admin_id: int, name: str, item: Item, qty: int) -> Player:
        if not 1 <= qty <= 1000:
            raise GameError("تعداد باید بین ۱ تا ۱۰۰۰ باشد.")
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await self.inventory.grant(tx, player.id, item.id, qty)
            await self._log(tx, admin_id, "give_item", f"{player.name} {item.id} x{qty}")
            return player

    async def set_ban(self, admin_id: int, name: str, banned: bool) -> Player:
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await player_repo.set_banned(tx, player.id, banned)
            await self._log(tx, admin_id, "ban" if banned else "unban", player.name)
            return player

    async def set_level(self, admin_id: int, name: str, level: int) -> Player:
        if not 1 <= level <= self.ctx.balance.max_level:
            raise GameError(f"سطح باید بین ۱ تا {self.ctx.balance.max_level} باشد.")
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await player_repo.set_progress(tx, player.id, level, 0)
            await player_repo.set_energy(tx, player.id, progression.max_energy(level, self.ctx.balance), self.ctx.now())
            await self._log(tx, admin_id, "set_level", f"{player.name} -> {level}")
            return player

    async def group_ids(self) -> list[int]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT chat_id FROM groups WHERE enabled = 1")
        return [r["chat_id"] for r in rows]

    async def log_action(self, admin_id: int, action: str, detail: str = "") -> None:
        async with self.ctx.db.transaction() as tx:
            await self._log(tx, admin_id, action, detail)
