"""Owning, buying and choosing companion pets."""

from __future__ import annotations

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.pets import PETS, Pet, get_pet
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

    async def bonus_in(self, tx: Tx, player_id: int) -> Stats:
        row = await tx.fetchone("SELECT pet_id FROM player_pets WHERE player_id = ? AND active = 1", (player_id,))
        return get_pet(row["pet_id"]).bonus if row else Stats()

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
