"""Player accounts: registration, energy, experience and the daily reward."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import players as repo
from ...db.repos import wallet
from ...shared.errors import GameError, NotRegistered
from ...shared.text import duration, fa
from ...shared.validators import clean_name
from ..data.classes import CLASSES
from ..data.races import RACES
from ..engine import progression
from ..models import Player

DAY = 24 * 3600


@dataclass
class LevelUp:
    old_level: int
    new_level: int


@dataclass
class DailyReward:
    gold: int
    streak: int


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

    # --- energy and experience (called inside the caller's transaction) -----------------------
    async def spend_energy(self, tx: Tx, player_id: int, cost: int) -> Player:
        """Charge ``cost`` energy or raise. Returns the player as stored after the charge."""
        player = await repo.get(tx, player_id)
        if player is None:
            raise NotRegistered
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
        return LevelUp(player.level, level) if gained else None

    # --- daily reward -------------------------------------------------------------------------
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
            await wallet.apply(
                tx, player_id, gold=gold, reason="daily", now=now, ref=f"daily:{player_id}:{now // DAY}"
            )
            await repo.set_daily(tx, player_id, now, streak)
            return DailyReward(gold, streak)
