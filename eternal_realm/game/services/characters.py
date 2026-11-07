"""Derived character data: final stats (base + equipment) used by profiles and combat."""

from __future__ import annotations

from ...context import AppContext
from ..data.stats import Stats
from ..engine import progression
from ..models import Player


class CharacterService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def stats(self, player: Player) -> Stats:
        """Final stats of a character (equipment bonuses are added by the inventory layer)."""
        return progression.base_stats(player.race_id, player.class_id, player.level)

    def xp_needed(self, player: Player) -> int:
        return progression.xp_needed(player.level, self.ctx.balance)

    def max_energy(self, player: Player) -> int:
        return progression.max_energy(player.level, self.ctx.balance)
