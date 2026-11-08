"""Performing activities: cooldown + energy + loot + experience in one transaction."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import events as event_repo
from ...db.repos import inventory as inv_repo
from ...db.repos import players as player_repo
from ...db.repos import season as season_repo
from ...db.repos import wallet
from ...shared.errors import GameError, NotRegistered
from ...shared.text import duration
from ..data.activities import ACTIVITIES, Activity
from ..data.items import get_item
from ..engine import loot, progression
from ..models import Player
from .inventory import InventoryService
from .players import LevelUp, PlayerService


@dataclass
class ActivityResult:
    activity: Activity
    rolled: loot.Rolled
    level_up: LevelUp | None
    player: Player
    items: list[tuple[str, int, str]]
    #: seconds until this activity may be used again
    next_in: int = 0
    double_xp: bool = False
    #: the player's bought 2x boost was running
    boosted: bool = False


class ActivityService:
    def __init__(self, ctx: AppContext, players: PlayerService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory

    async def rest(self, player_id: int) -> int:
        """Rest to regain some energy now. Returns the energy actually restored."""
        balance, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            until = await inv_repo.cooldown_until(tx, player_id, "rest")
            if until > now:
                raise GameError(f"😴 همین تازگی کنار آتش نشسته‌اید. {duration(until - now)} دیگر دوباره می‌توانید استراحت کنید.")
            restored = await self.players.add_energy(tx, player_id, balance.rest_energy)
            if restored <= 0:
                raise GameError("شما سرشار از انرژی هستید، فرمانده! وقتی خسته شدید، کنار آتش استراحت کنید.")
            await inv_repo.set_cooldown(tx, player_id, "rest", now + balance.rest_cooldown_seconds)
        return restored

    async def perform(self, player_id: int, activity_id: str, chat_id: int | None = None) -> ActivityResult:
        activity = ACTIVITIES[activity_id]
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            player = await player_repo.get(tx, player_id)
            if player is None:
                raise NotRegistered
            key = f"act:{activity.id}"
            until = await inv_repo.cooldown_until(tx, player_id, key)
            if until > now:
                raise GameError(
                    f"⏳ دست‌هایتان هنوز خسته است، فرمانده!\n\nتا {duration(until - now)} دیگر می‌توانید دوباره "
                    f"{activity.title} کنید."
                )
            await self.players.spend_energy(tx, player_id, activity.energy)

            stats = progression.base_stats(
                player.race_id, player.class_id, player.level, player.class2_id, player.awakened
            )
            luck = stats.luck + (await self.inventory.equipped_stats(tx, player_id)).luck
            perk = player.race.perks.get(activity.id, 1.0)
            rolled = loot.roll(activity, player.level, luck, perk, self.ctx.rng)

            double = chat_id is not None and await event_repo.double_xp_active(tx, chat_id, now)
            if double:
                rolled.xp *= 2
            boost = await self.players.boost_factor(tx, player_id)
            if boost > 1:  # coins, experience and every item are doubled (crystals are not)
                rolled.gold *= boost
                rolled.xp *= boost
                rolled.items = {item_id: qty * boost for item_id, qty in rolled.items.items()}
            await wallet.apply(
                tx, player_id, gold=rolled.gold, crystal=rolled.crystal,
                reason=f"activity:{activity.id}", now=now,
            )
            for item_id, qty in rolled.items.items():
                await self.inventory.grant(tx, player_id, item_id, qty)
            level_up = await self.players.grant_xp(tx, player_id, rolled.xp) if rolled.xp else None
            wait = await self.players.schedule_cooldown(tx, player_id, key)
            await season_repo.add_points(tx, player_id, "activity", now)

            after = await player_repo.get(tx, player_id)
            assert after is not None
        items = [(get_item(i).label, q, i) for i, q in rolled.items.items()]
        return ActivityResult(activity, rolled, level_up, self.players.with_energy(after), items, wait, double, boost > 1)
