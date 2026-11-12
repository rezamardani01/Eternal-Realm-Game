"""Derived character data: final stats (base + equipment) used by profiles and combat."""

from __future__ import annotations

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.classes import CLASSES
from ..data.pets import get_pet
from ..data.stats import Stats
from ..engine import progression
from ..engine.combat import Fighter
from ..models import Player
from .arms import ArmsService
from .growth import GrowthService
from .inventory import InventoryService


class CharacterService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory
        self.arms = ArmsService(ctx, inventory)
        self.growth = GrowthService(ctx, self.arms)

    async def stats(self, player: Player) -> Stats:
        """Final stats of a character: race + class + level + equipped gear."""
        async with self.ctx.db.read() as tx:
            return await self.stats_in(tx, player)

    async def stats_in(self, tx: Tx, player: Player) -> Stats:
        """Same as :meth:`stats` inside an open transaction (the DB lock is not re-entrant)."""
        base = progression.base_stats(
            player.race_id, player.class_id, player.level, player.class2_id, player.awakened
        )
        pet = await tx.fetchone(
            "SELECT pet_id FROM player_pets WHERE player_id = ? AND active = 1", (player.id,)
        )
        extra = get_pet(pet["pet_id"]).bonus if pet else Stats()
        loadout = await self.arms.loadout_in(tx, player.id)
        total = base + extra + loadout.stats
        total = total + await self.growth.bonus_in(tx, player)
        from .effects import EffectService

        return await EffectService(self.ctx).apply_to(tx, player.id, total)

    async def fighter_from(self, tx: Tx, player: Player, stats: Stats, mention: str = "") -> Fighter:
        """The hero as a fighter: his stats, his three skills (race and class) and the traits of his four pieces."""
        loadout = await self.arms.loadout_in(tx, player.id)
        traits = [*loadout.traits, *await self.growth.traits_in(tx, player)]
        return Fighter.for_player(
            player.id, player.name, player.char_class, stats, mention, race_id=player.race_id, traits=traits,
            level=player.level,
        )

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

    # --- paid services: each one uses up a ticket ----------------------------------------------------
    async def change_race(self, player: Player, race_id: str) -> Player:
        from ..data.races import RACES

        if race_id not in RACES:
            raise GameError("این نژاد در قلمرو شناخته نمی‌شود.")
        if race_id == player.race_id:
            raise GameError("این همان نژاد فعلی شماست؛ یکی دیگر را انتخاب کنید.")
        async with self.ctx.db.transaction() as tx:
            await self.inventory.take(tx, player.id, "race_ticket", 1)
            await tx.execute("UPDATE players SET race = ? WHERE id = ?", (race_id, player.id))
            after = await player_repo.get(tx, player.id)
            assert after is not None
            return after

    async def change_class(self, player: Player, class_id: str) -> Player:
        if class_id not in CLASSES:
            raise GameError("این کلاس در قلمرو شناخته نمی‌شود.")
        if class_id == player.class_id:
            raise GameError("این همان کلاس فعلی شماست؛ یکی دیگر را انتخاب کنید.")
        async with self.ctx.db.transaction() as tx:
            await self.inventory.take(tx, player.id, "class_ticket", 1)
            await tx.execute("UPDATE players SET class = ? WHERE id = ?", (class_id, player.id))
            if player.class2_id == class_id:  # the second class must differ from the first
                await tx.execute("UPDATE players SET class2 = '' WHERE id = ?", (player.id,))
            after = await player_repo.get(tx, player.id)
            assert after is not None
            return after

    async def rename(self, player: Player, raw_name: str) -> Player:
        from ...shared.validators import clean_name

        name = clean_name(raw_name)
        async with self.ctx.db.transaction() as tx:
            if await player_repo.name_taken(tx, name):
                raise GameError("قهرمان دیگری پیش‌تر این نام را برداشته است. یک نام تازه و یگانه بنویسید.")
            await self.inventory.take(tx, player.id, "rename_ticket", 1)
            await tx.execute("UPDATE players SET display_name = ? WHERE id = ?", (name, player.id))
            after = await player_repo.get(tx, player.id)
            assert after is not None
            return after
