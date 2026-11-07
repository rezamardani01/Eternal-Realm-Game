"""Derived character data: final stats (base + equipment) used by profiles and combat."""

from __future__ import annotations

from ...context import AppContext
from ..data.stats import Stats
from ..engine import progression
from ..models import Player
from .inventory import InventoryService


class CharacterService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def stats(self, player: Player) -> Stats:
        """Final stats of a character: race + class + level + equipped gear."""
        base = progression.base_stats(player.race_id, player.class_id, player.level)
        async with self.ctx.db.read() as tx:
            return base + await self.inventory.equipped_stats(tx, player.id)

    def xp_needed(self, player: Player) -> int:
        return progression.xp_needed(player.level, self.ctx.balance)

    def max_energy(self, player: Player) -> int:
        return progression.max_energy(player.level, self.ctx.balance)
