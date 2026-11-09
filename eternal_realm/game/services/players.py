"""Player accounts: registration, energy, experience and the daily reward."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import players as repo
from ...config import cooldown_ladder
from ...db.repos import inventory as inv_repo
from ...db.repos import wallet
from ...shared.errors import GameError, NotRegistered
from ...shared.text import duration, fa
from ...shared.validators import clean_name
from ..data.classes import CLASSES
from ..data.races import RACES
from ..engine import progression
from ..models import Player

VIP_COOLDOWN_FACTOR = 0.8
DAY = 24 * 3600


@dataclass
class LevelUp:
    old_level: int
    new_level: int


NEWCOMER_BOOST_DAYS = 3


@dataclass
class DailyReward:
    gold: int
    streak: int
    #: the chest a streak milestone paid out today ("" when none)
    chest: str = ""
    #: days of streak until the next chest
    next_chest_in: int = 0
    #: crystals paid for a full week in a row
    crystal: int = 0


def streak_chest(streak: int) -> str:
    """Streaks pay a chest every week, a better one every two weeks and a royal one every month."""
    if streak % 30 == 0:
        return "royal_chest"
    if streak % 14 == 0:
        return "magic_chest"
    if streak % 7 == 0:
        return "wooden_chest"
    return ""


class PlayerService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        #: run inside the registration transaction (starter items and similar)
        self.after_register: list[Callable[[Tx, Player], Awaitable[None]]] = []

    # --- registration -------------------------------------------------------------------------
    async def name_available(self, raw_name: str) -> str:
        """Validate a name and make sure nobody owns it. Returns the cleaned name."""
        name = clean_name(raw_name)
        async with self.ctx.db.read() as tx:
            if await repo.name_taken(tx, name):
                raise GameError("قهرمان دیگری پیش‌تر این نام را برداشته است. یک نام تازه و یگانه برای خود بنویسید.")
        return name

    async def register(
        self, platform_user_id: int, username: str | None, raw_name: str, race_id: str, class_id: str
    ) -> Player:
        if race_id not in RACES or class_id not in CLASSES:
            raise GameError("این نژاد یا کلاس در قلمرو شناخته نمی‌شود. یکی از دکمه‌ها را انتخاب کنید.")
        name = clean_name(raw_name)
        balance, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            if await repo.get_by_platform(tx, platform_user_id):
                raise GameError("شما پیش‌تر قهرمان خود را ساخته‌اید. هر ماجراجو فقط یک قهرمان دارد!")
            if await repo.name_taken(tx, name):
                raise GameError("قهرمان دیگری پیش‌تر این نام را برداشته است. یک نام تازه و یگانه برای خود بنویسید.")
            player = await repo.create(
                tx,
                platform_user_id=platform_user_id,
                username=username,
                name=name,
                race=race_id,
                char_class=class_id,
                energy=progression.max_energy(1, balance),
                gold=0,
                now=now,
            )
            await wallet.apply(
                tx, player.id, gold=balance.start_gold, reason="start_gift", now=now,
                ref=f"start:{player.id}",
            )
            for hook in self.after_register:
                await hook(tx, player)
            refreshed = await repo.get(tx, player.id)
            assert refreshed is not None
            return refreshed

    # --- lookup -------------------------------------------------------------------------------
    def with_energy(self, player: Player) -> Player:
        """Return the player with energy brought up to date for display (not persisted)."""
        energy, at = progression.regen_energy(
            player.energy, player.energy_at, self.ctx.now(), player.level, self.ctx.balance
        )
        player.energy, player.energy_at = energy, at
        return player

    async def find(self, platform_user_id: int, username: str | None = None) -> Player | None:
        async with self.ctx.db.read() as tx:
            player = await repo.get_by_platform(tx, platform_user_id)
        if player is None:
            return None
        if username is not None and username != player.username:
            async with self.ctx.db.transaction() as tx:
                await repo.touch_username(tx, player.id, username)
            player.username = username
        return self.with_energy(player)

    async def require(self, platform_user_id: int) -> Player:
        player = await self.find(platform_user_id)
        if player is None:
            raise NotRegistered
        return player

    async def get(self, player_id: int) -> Player | None:
        async with self.ctx.db.read() as tx:
            player = await repo.get(tx, player_id)
        return self.with_energy(player) if player else None

    async def get_by_name(self, name: str) -> Player | None:
        async with self.ctx.db.read() as tx:
            player = await repo.get_by_name(tx, name)
        return self.with_energy(player) if player else None

    # --- the 2x boost ---------------------------------------------------------------------------
    async def boost_factor(self, tx: Tx, player_id: int) -> int:
        """2 while the player's bought boost runs, else 1. Used wherever coins, experience or loot are paid."""
        from ..data.packs import BOOST_FACTOR

        until = int(await tx.scalar("SELECT boost_until FROM players WHERE id = ?", (player_id,), 0))
        return BOOST_FACTOR if until > self.ctx.now() else 1

    # --- energy and experience (called inside the caller's transaction) -----------------------
    def is_owner(self, player: Player) -> bool:
        """The realm owner has no waiting times, energy cost or daily limits."""
        return player.platform_user_id == self.ctx.settings.owner_id

    async def spend_energy(self, tx: Tx, player_id: int, cost: int) -> Player:
        """Charge ``cost`` energy or raise. Returns the player as stored after the charge."""
        player = await repo.get(tx, player_id)
        if player is None:
            raise NotRegistered
        if self.is_owner(player):
            return player
        now = self.ctx.now()
        energy, at = progression.regen_energy(
            player.energy, player.energy_at, now, player.level, self.ctx.balance
        )
        if energy < cost:
            wait = progression.seconds_to_next_energy(at, now, self.ctx.balance)
            raise GameError(
                f"⚡ انرژی شما کافی نیست ({fa(energy)} از {fa(cost)}).\n\n"
                f"یک انرژی تازه تا {duration(wait)} دیگر می‌رسد. می‌توانید «استراحت» کنید "
                "یا معجون انرژی بنوشید و دوباره به میدان بیایید!"
            )
        if energy == progression.max_energy(player.level, self.ctx.balance):
            at = now
        await repo.set_energy(tx, player_id, energy - cost, at)
        player.energy, player.energy_at = energy - cost, at
        return player

    async def add_energy(self, tx: Tx, player_id: int, amount: int) -> int:
        player = await repo.get(tx, player_id)
        if player is None:
            raise NotRegistered
        now = self.ctx.now()
        energy, _ = progression.regen_energy(
            player.energy, player.energy_at, now, player.level, self.ctx.balance
        )
        cap = progression.max_energy(player.level, self.ctx.balance)
        new = min(cap, energy + amount)
        await repo.set_energy(tx, player_id, new, now)
        return new - energy

    async def grant_xp(self, tx: Tx, player_id: int, amount: int) -> LevelUp | None:
        player = await repo.get(tx, player_id)
        if player is None:
            raise NotRegistered
        amount = round(amount * player.race.xp_multiplier)
        level, xp, gained = progression.apply_xp(player.level, player.xp, amount, self.ctx.balance)
        await repo.set_progress(tx, player_id, level, xp)
        if gained:
            from ..notify import achievement_check

            await achievement_check(tx, player_id, "level", level, self.ctx.now())
        return LevelUp(player.level, level) if gained else None

    async def schedule_cooldown(self, tx: Tx, player_id: int, key: str) -> int:
        """Start the waiting time after using ``key`` and return it in seconds.

        The wait grows during the day: 5 minutes after the first use, 15 after the second, and so on
        (``Balance.cooldown_ladder``). It starts over every Tehran midnight.
        """
        if int(await tx.scalar("SELECT platform_user_id FROM players WHERE id = ?", (player_id,), 0)) == self.ctx.settings.owner_id:
            return 0
        now = self.ctx.now()
        day = (now + 12600) // 86400
        used = await inv_repo.uses_today(tx, player_id, key, day)
        steps = cooldown_ladder(self.ctx.balance)
        wait = steps[min(used, len(steps) - 1)]
        vip = int(await tx.scalar("SELECT vip_until FROM players WHERE id = ?", (player_id,), 0))
        if vip > now:
            wait = round(wait * VIP_COOLDOWN_FACTOR)
        await inv_repo.record_use(tx, player_id, key, day)
        await inv_repo.set_cooldown(tx, player_id, key, now + wait)
        return wait

    # --- daily reward -------------------------------------------------------------------------
    async def grant_welcome_boost(self, player_id: int) -> None:
        """A newcomer's gift: three days of the 2x boost (given once, when the hero is born through the bot)."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "UPDATE players SET boost_until = MAX(boost_until, ?) + ? WHERE id = ?",
                (now, NEWCOMER_BOOST_DAYS * DAY, player_id),
            )

    async def claim_daily(self, player_id: int) -> DailyReward:
        balance, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            player = await repo.get(tx, player_id)
            if player is None:
                raise NotRegistered
            elapsed = now - player.daily_at
            if player.daily_at and elapsed < DAY:
                raise GameError(f"🎁 گنجینه‌ی روزانه‌ی امروز را برداشته‌اید. {duration(DAY - elapsed)} دیگر بازگردید؛ هدیه‌ی تازه‌ای آماده می‌شود!")
            streak = player.daily_streak + 1 if player.daily_at and elapsed < 2 * DAY else 1
            bonus = min(streak, balance.daily_streak_cap) - 1
            gold = balance.daily_gold + balance.daily_gold_per_level * player.level + 50 * bonus
            gold *= await self.boost_factor(tx, player_id)
            await wallet.apply(
                tx, player_id, gold=gold, reason="daily", now=now, ref=f"daily:{player_id}:{now // DAY}"
            )
            await repo.set_daily(tx, player_id, now, streak)
            chest = streak_chest(streak)
            if chest:
                await inv_repo.add_stack(tx, player_id, chest, 1)
            from ..notify import achievement_check

            await achievement_check(tx, player_id, "streak", streak, now)
            crystal = 3 if streak % 7 == 0 else 0
            if crystal:
                await wallet.apply(
                    tx, player_id, crystal=crystal, reason="daily_week", now=now, ref=f"dailyweek:{player_id}:{now // DAY}"
                )
            from ...db.repos import season as season_repo

            await season_repo.add_points(tx, player_id, "daily", now)
            return DailyReward(gold, streak, chest, 7 - streak % 7, crystal)
