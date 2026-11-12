"""The NPC shop: buying and selling potions and materials."""

from __future__ import annotations

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.items import Item, Kind
from ..models import Player
from .inventory import InventoryService

MAX_QTY = 99


def shop_items() -> list[Item]:
    from ..data.items import ITEMS

    return [i for i in ITEMS.values() if i.buy > 0 and i.kind is not Kind.CHEST]


class ShopService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def buy(self, player: Player, item: Item, qty: int) -> int:
        """Buy ``qty`` of an item from the NPC. Returns the gold paid."""
        if item.buy <= 0:
            raise GameError(f"{item.label} در بازارچه موجود نیست. شاید در «بازار» از دست بازیکنی پیدا شود یا از هیولاها غنیمت گرفته شود.")
        if not 1 <= qty <= MAX_QTY:
            raise GameError(f"هر بار فقط می‌توانید بین ۱ تا {MAX_QTY} عدد بخرید.")
        total = item.buy * qty
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(tx, player.id, gold=-total, reason="shop_buy", now=self.ctx.now())
            await self.inventory.grant(tx, player.id, item.id, qty)
        return total

    async def sell_stack(self, player: Player, item: Item, qty: int) -> int:
        if item.sell <= 0:
            raise GameError(f"فروشنده‌ی بازارچه {item.label} را نمی‌خرد. شاید در «بازار» خریداری برایش پیدا شود.")
        if not 1 <= qty <= 10_000:
            raise GameError("تعداد را درست بنویسید؛ مثلاً: 5")
        total = item.sell * qty
        async with self.ctx.db.transaction() as tx:
            await self.inventory.take(tx, player.id, item.id, qty)
            await wallet.apply(tx, player.id, gold=total, reason="shop_sell", now=self.ctx.now())
        return total
