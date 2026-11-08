"""The hero-path ticket: progress, claiming tier rewards and buying the season ticket."""

from __future__ import annotations

from ...context import AppContext
from ...db.repos import season as repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.season import TIERS, PathState, TierReward, reward_for
from ..models import Player
from .inventory import InventoryService


class SeasonService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def state(self, player: Player) -> PathState:
        async with self.ctx.db.read() as tx:
            return await repo.state(tx, player.id, self.ctx.now())

    async def claim(self, player: Player, track: str, tier: int) -> TierReward:
        """Collect one tier reward. Safe against double taps: each (season, track, tier) pays once."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            return await self._claim_in(tx, player.id, track, tier, now)

    async def _claim_in(self, tx, player_id: int, track: str, tier: int, now: int) -> TierReward:  # noqa: ANN001
        if track not in ("free", "ticket") or not 1 <= tier <= TIERS:
            raise GameError("این جایزه وجود ندارد.")
        st = await repo.state(tx, player_id, now)
        if tier > st.tier:
            raise GameError("هنوز به این مرحله نرسیده‌اید. با ماجراجویی و نبرد امتیاز مسیر جمع کنید!")
        if track == "ticket" and not st.premium:
            raise GameError("این جایزه مال دارندگان «بلیط مسیر قهرمانی» است.")
        if (track, tier) in st.claimed:
            raise GameError("این جایزه را قبلاً گرفته‌اید.")
        reward = reward_for(track, tier)
        await tx.execute(
            "INSERT INTO season_claims (player_id, season, track, tier, claimed_at) VALUES (?, ?, ?, ?, ?)",
            (player_id, st.season, track, tier, now),
        )
        if reward.gold or reward.crystal:
            await wallet.apply(
                tx, player_id, gold=reward.gold, crystal=reward.crystal, reason=f"path:{track}", now=now,
                ref=f"path:{st.season}:{track}:{tier}:{player_id}",
            )
        for item_id, qty in reward.items:
            await self.inventory.grant(tx, player_id, item_id, qty)
        if reward.title:
            await tx.execute("UPDATE players SET title = ? WHERE id = ?", (reward.title, player_id))
        return reward

    async def claim_all(self, player: Player) -> list[tuple[str, int, TierReward]]:
        now = self.ctx.now()
        done = []
        async with self.ctx.db.transaction() as tx:
            st = await repo.state(tx, player.id, now)
            for track, tier in st.available():
                done.append((track, tier, await self._claim_in(tx, player.id, track, tier, now)))
        if not done:
            raise GameError("جایزه‌ی آماده‌ای برای گرفتن نیست. امتیاز بیشتری جمع کنید!")
        return done
