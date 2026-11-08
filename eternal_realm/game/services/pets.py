"""Owning, buying and choosing companion pets."""

from __future__ import annotations

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.pets import MAX_PET_LEVEL, PETS, Pet, bonus_at, get_pet, upgrade_cost
from ..data.stats import Stats
from ..models import Player


class PetService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def owned_in(self, tx: Tx, player_id: int) -> dict[str, bool]:
        """pet id -> is it the active one."""
        rows = await tx.fetchall("SELECT pet_id, active FROM player_pets WHERE player_id = ?", (player_id,))
        return {r["pet_id"]: bool(r["active"]) for r in rows}

    async def owned(self, player_id: int) -> dict[str, bool]:
        async with self.ctx.db.read() as tx:
            return await self.owned_in(tx, player_id)

    async def levels(self, player_id: int) -> dict[str, int]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT pet_id, level FROM player_pets WHERE player_id = ?", (player_id,))
        return {r["pet_id"]: r["level"] for r in rows}

    async def bonus_in(self, tx: Tx, player_id: int) -> Stats:
        row = await tx.fetchone(
            "SELECT pet_id, level FROM player_pets WHERE player_id = ? AND active = 1", (player_id,)
        )
        return bonus_at(get_pet(row["pet_id"]), row["level"]) if row else Stats()

    async def striker_in(self, tx: Tx, player_id: int, atk: int) -> tuple[str, str, int] | None:
        """``(emoji, name, strike power)`` of the active pet, for fights where it joins in."""
        row = await tx.fetchone(
            "SELECT pet_id, level FROM player_pets WHERE player_id = ? AND active = 1", (player_id,)
        )
        if row is None:
            return None
        pet = get_pet(row["pet_id"])
        power = max(3, round(atk * 0.20 * (1 + 0.15 * (row["level"] - 1)) + pet.rarity * 2))
        return pet.emoji, pet.name, power

    async def upgrade(self, player: Player, pet_id: str) -> tuple[Pet, int]:
        """Spend crystals to raise a pet one level. Returns the pet and its new level."""
        pet = get_pet(pet_id)
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT level FROM player_pets WHERE player_id = ? AND pet_id = ?", (player.id, pet_id)
            )
            if row is None:
                raise GameError("این حیوان خانگی مال شما نیست.")
            if row["level"] >= MAX_PET_LEVEL:
                raise GameError(f"{pet.name} به بالاترین سطح رسیده است!")
            cost = upgrade_cost(row["level"])
            await wallet.apply(tx, player.id, crystal=-cost, reason=f"pet_up:{pet_id}", now=self.ctx.now())
            await tx.execute(
                "UPDATE player_pets SET level = level + 1 WHERE player_id = ? AND pet_id = ?", (player.id, pet_id)
            )
        return pet, row["level"] + 1

    async def grant(self, tx: Tx, player_id: int, pet_id: str) -> bool:
        """Give a pet. ``False`` when the player already has it. The first pet becomes active."""
        owned = await self.owned_in(tx, player_id)
        if pet_id in owned:
            return False
        await tx.execute(
            "INSERT INTO player_pets (player_id, pet_id, active, got_at) VALUES (?, ?, ?, ?)",
            (player_id, pet_id, int(not owned), self.ctx.now()),
        )
        return True

    async def buy_with_gold(self, player: Player, pet_id: str) -> Pet:
        pet = get_pet(pet_id)
        if pet.price_gold <= 0:
            raise GameError("این حیوان همراه فقط از «خزانه‌ی ویژه» خریداری می‌شود.")
        async with self.ctx.db.transaction() as tx:
            if pet_id in await self.owned_in(tx, player.id):
                raise GameError(f"{pet.name} از قبل همراه شماست؛ خرید دوباره لازم نیست.")
            await wallet.apply(tx, player.id, gold=-pet.price_gold, reason=f"pet:{pet_id}", now=self.ctx.now())
            await self.grant(tx, player.id, pet_id)
        return pet

    async def activate(self, player: Player, pet_id: str) -> Pet:
        pet = get_pet(pet_id)
        async with self.ctx.db.transaction() as tx:
            if pet_id not in await self.owned_in(tx, player.id):
                raise GameError("این حیوان همراه مال شما نیست.")
            await tx.execute("UPDATE player_pets SET active = 0 WHERE player_id = ?", (player.id,))
            await tx.execute(
                "UPDATE player_pets SET active = 1 WHERE player_id = ? AND pet_id = ?", (player.id, pet_id)
            )
        return pet


__all__ = ["PETS", "PetService", "fa"]
