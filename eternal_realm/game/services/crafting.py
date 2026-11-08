"""The forge: turn a base piece plus materials into a better piece of gear."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import inventory as inv_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.items import Item, get_item
from ..data.recipes import RECIPES, Recipe, get_recipe
from ..models import Player
from .inventory import InventoryService


@dataclass
class Need:
    item: Item
    have: int
    need: int

    @property
    def ok(self) -> bool:
        return self.have >= self.need


@dataclass
class CraftView:
    recipe: Recipe
    result: Item
    base: Need | None
    materials: list[Need]
    gold_have: int
    already_owned: bool

    @property
    def ready(self) -> bool:
        return (
            not self.already_owned
            and (self.base is None or self.base.ok)
            and all(n.ok for n in self.materials)
            and self.gold_have >= self.recipe.gold
        )


class CraftingService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def view(self, player: Player, recipe_id: str) -> CraftView:
        recipe = get_recipe(recipe_id)
        async with self.ctx.db.read() as tx:
            gear = await inv_repo.list_gear(tx, player.id)
            owned = await inv_repo.owns_gear(tx, player.id, recipe.result)
            mats = [
                Need(get_item(i), await inv_repo.stack_qty(tx, player.id, i), q) for i, q in recipe.materials.items()
            ]
            fresh = await tx.fetchone("SELECT gold FROM players WHERE id = ?", (player.id,))
        base = None
        if recipe.base:
            spare = sum(1 for g in gear if g.item_id == recipe.base and g.slot is None)
            base = Need(get_item(recipe.base), spare, 1)
        return CraftView(recipe, get_item(recipe.result), base, mats, fresh["gold"], owned)

    async def craft(self, player: Player, recipe_id: str) -> Item:
        recipe = get_recipe(recipe_id)
        async with self.ctx.db.transaction() as tx:
            if await inv_repo.owns_gear(tx, player.id, recipe.result):
                raise GameError(f"شما از قبل {get_item(recipe.result).label} را دارید؛ ساختن دوباره لازم نیست.")
            if recipe.base:
                gear = [g for g in await inv_repo.list_gear(tx, player.id) if g.item_id == recipe.base and g.slot is None]
                if not gear:
                    raise GameError(
                        f"برای ساختن، {get_item(recipe.base).label} آزاد لازم دارید (نه پوشیده و نه در بازار)."
                    )
                await inv_repo.delete_gear(tx, gear[0].id)
            for item_id, qty in recipe.materials.items():
                await self.inventory.take(tx, player.id, item_id, qty)
            await wallet.apply(tx, player.id, gold=-recipe.gold, reason=f"craft:{recipe.id}", now=self.ctx.now())
            await self.inventory.grant(tx, player.id, recipe.result, 1, origin="ساخته‌شده در کوره‌ی آهنگری")
        return get_item(recipe.result)


__all__ = ["CraftView", "CraftingService", "Need", "RECIPES"]
