"""Chests: buying with in-game currency and opening."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.chests import CHESTS, Chest, Prize
from ..data.items import Item, Kind, get_item
from ..models import Player
from .inventory import InventoryService


@dataclass
class Opened:
    chest: Item
    prize: Prize
    gold: int
    crystal: int
    item: Item | None
    qty: int


class ChestService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    def odds(self, chest: Chest) -> list[tuple[Prize, float]]:
        total = chest.total_weight
        return [(p, p.weight / total) for p in chest.prizes]

    def roll(self, chest: Chest) -> Prize:
        return self.ctx.rng.choices(chest.prizes, weights=[p.weight for p in chest.prizes], k=1)[0]

    async def buy(self, player: Player, chest_id: str, qty: int = 1) -> tuple[str, int]:
        """Buy chests with gold or crystals. Returns ``(currency, total_price)``."""
        chest = CHESTS.get(chest_id)
        if chest is None or chest.price is None:
            raise GameError("این صندوقچه برای فروش نیست.")
        if not 1 <= qty <= 20:
            raise GameError("تعداد باید بین ۱ تا ۲۰ باشد.")
        currency, unit = chest.price
        total = unit * qty
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(
                tx, player.id, reason="chest_buy", now=self.ctx.now(),
                **{currency: -total},
            )
            await self.inventory.grant(tx, player.id, chest_id, qty)
        return currency, total

    async def open(self, player: Player, item: Item) -> Opened:
        chest = CHESTS.get(item.id)
        if item.kind is not Kind.CHEST or chest is None:
            raise GameError(f"{item.label} صندوقچه نیست.")
        prize = self.roll(chest)
        rng = self.ctx.rng
        gold = rng.randint(*prize.gold) if prize.gold[1] else 0
        crystal = rng.randint(*prize.crystal) if prize.crystal[1] else 0
        qty = rng.randint(*prize.qty) if prize.item_id else 0
        async with self.ctx.db.transaction() as tx:
            await self.inventory.take(tx, player.id, item.id, 1)
            await wallet.apply(
                tx, player.id, gold=gold, crystal=crystal, reason="chest_open", now=self.ctx.now()
            )
            if prize.item_id:
                await self.inventory.grant(tx, player.id, prize.item_id, qty)
        return Opened(item, prize, gold, crystal, get_item(prize.item_id) if prize.item_id else None, qty)
