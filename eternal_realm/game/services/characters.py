"""Derived character data: final stats (base + equipment) used by profiles and combat."""

from __future__ import annotations

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.classes import CLASSES
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
        async with self.ctx.db.read() as tx:
            return await self.stats_in(tx, player)

    async def stats_in(self, tx: Tx, player: Player) -> Stats:
        """Same as :meth:`stats` inside an open transaction (the DB lock is not re-entrant)."""
        base = progression.base_stats(
            player.race_id, player.class_id, player.level, player.class2_id, player.awakened
        )
        return base + await self.inventory.equipped_stats(tx, player.id)

    def xp_needed(self, player: Player) -> int:
        return progression.xp_needed(player.level, self.ctx.balance)

    def max_energy(self, player: Player) -> int:
        return progression.max_energy(player.level, self.ctx.balance)

    # --- growing beyond the first class ------------------------------------------------------------
    async def choose_second_class(self, player: Player, class_id: str) -> Player:
        b = self.ctx.balance
        if class_id not in CLASSES or class_id == player.class_id:
            raise GameError("این کلاس را نمی‌توانید به‌عنوان کلاس دوم انتخاب کنید؛ یکی از کلاس‌های دیگر را بردارید.")
        async with self.ctx.db.transaction() as tx:
            fresh = await player_repo.get(tx, player.id)
            assert fresh is not None
            if fresh.class2_id:
                raise GameError("شما کلاس دوم دارید. هر قهرمان فقط یک کلاس دوم می‌تواند داشته باشد.")
            if fresh.level < b.second_class_level:
                raise GameError(
                    f"کلاس دوم از سطح {fa(b.second_class_level)} باز می‌شود. شما سطح {fa(fresh.level)} هستید؛ "
                    f"{fa(b.second_class_level - fresh.level)} سطح دیگر مانده."
                )
            await wallet.apply(tx, player.id, gold=-b.second_class_gold, reason="second_class", now=self.ctx.now())
            await tx.execute("UPDATE players SET class2 = ? WHERE id = ?", (class_id, player.id))
            after = await player_repo.get(tx, player.id)
            assert after is not None
            return after

    async def awaken(self, player: Player) -> Player:
        b = self.ctx.balance
        async with self.ctx.db.transaction() as tx:
            fresh = await player_repo.get(tx, player.id)
            assert fresh is not None
            if fresh.awakened:
                raise GameError("قدرت پنهان شما از قبل بیدار شده است!")
            if fresh.level < b.awaken_level:
                raise GameError(
                    f"بیداری قدرت از سطح {fa(b.awaken_level)} ممکن است. شما سطح {fa(fresh.level)} هستید؛ "
                    f"{fa(b.awaken_level - fresh.level)} سطح دیگر مانده."
                )
            await wallet.apply(
                tx, player.id, gold=-b.awaken_gold, crystal=-b.awaken_crystal, reason="awakening", now=self.ctx.now()
            )
            await tx.execute("UPDATE players SET awakened = 1 WHERE id = ?", (player.id,))
            after = await player_repo.get(tx, player.id)
            assert after is not None
            return after
