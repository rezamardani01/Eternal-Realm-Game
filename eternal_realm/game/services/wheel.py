"""The wheel of fortune: spins come from paid packs, every spin pays its prize at once."""

from __future__ import annotations

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data import wheel as data
from ..models import Player
from .inventory import InventoryService


class WheelService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def spins(self, player_id: int) -> int:
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT wheel_spins FROM players WHERE id = ?", (player_id,), 0))

    async def spin(self, player: Player) -> tuple[data.Slice, int]:
        """Use one spin. Returns the slice that came up and how many spins are left."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "UPDATE players SET wheel_spins = wheel_spins - 1 WHERE id = ? AND wheel_spins > 0", (player.id,)
            )
            if tx.rowcount == 0:
                raise GameError("فرصت گردونه ندارید؛ از همین صفحه فرصت بخرید و بچرخانید.")
            prize = data.spin(self.ctx.rng)
            await wallet.apply(tx, player.id, gold=prize.gold, crystal=prize.crystal, reason="wheel", now=now)
            for item_id, qty in prize.items:
                await self.inventory.grant(tx, player.id, item_id, qty, origin="wheel")
            await tx.execute(
                "INSERT INTO wheel_log (player_id, slice, at) VALUES (?, ?, ?)", (player.id, prize.id, now)
            )
            left = int(await tx.scalar("SELECT wheel_spins FROM players WHERE id = ?", (player.id,), 0))
        return prize, left
