"""The NPC shop: buying, selling and upgrading gear."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import inventory as inv_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.items import MAX_UPGRADE, Item, Kind, get_item
from ..models import Player
from .inventory import InventoryService, Piece

MAX_QTY = 99
RARITY_VALUE = {1: 150, 2: 900, 3: 3000, 4: 6000, 5: 12000, 6: 25000}
UPGRADE_CHANCE = (1.0, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.25)


@dataclass(frozen=True)
class UpgradeQuote:
    next_level: int
    gold: int
    materials: dict[str, int]
    chance: float


@dataclass
class UpgradeResult:
    piece: Piece
    success: bool
    quote: UpgradeQuote


def upgrade_quote(item: Item, current: int) -> UpgradeQuote:
    nxt = current + 1
    value = item.buy or RARITY_VALUE[item.rarity]
    materials = {"iron_ore": nxt}
    if nxt >= 6:
        materials["crystal_shard"] = nxt - 4
    return UpgradeQuote(nxt, round(value * 0.35 * nxt), materials, UPGRADE_CHANCE[current])


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
            raise GameError(f"{item.label} در فروشگاه فروخته نمی‌شود.")
        if not 1 <= qty <= MAX_QTY:
            raise GameError(f"تعداد باید بین ۱ تا {MAX_QTY} باشد.")
        total = item.buy * qty
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(tx, player.id, gold=-total, reason="shop_buy", now=self.ctx.now())
            await self.inventory.grant(tx, player.id, item.id, qty)
        return total

    async def sell_stack(self, player: Player, item: Item, qty: int) -> int:
        if item.sell <= 0 or item.is_gear:
            raise GameError(f"{item.label} را نمی‌شود به فروشگاه فروخت.")
        if not 1 <= qty <= 10_000:
            raise GameError("تعداد نامعتبر است.")
        total = item.sell * qty
        async with self.ctx.db.transaction() as tx:
            await self.inventory.take(tx, player.id, item.id, qty)
            await wallet.apply(tx, player.id, gold=total, reason="shop_sell", now=self.ctx.now())
        return total

    async def sell_gear(self, player: Player, gear_id: int) -> tuple[Piece, int]:
        async with self.ctx.db.transaction() as tx:
            piece = await self.inventory.piece(tx, player.id, gear_id)
            if piece.slot is not None:
                raise GameError("اول این تجهیزات را دربیاور.")
            if piece.item.sell <= 0:
                raise GameError(f"{piece.item.label} را فقط در بازار می‌شود فروخت.")
            total = round(piece.item.sell * (1 + 0.5 * piece.upgrade))
            await inv_repo.delete_gear(tx, piece.id)
            await wallet.apply(tx, player.id, gold=total, reason="shop_sell", now=self.ctx.now())
        return piece, total

    async def quote(self, player: Player, gear_id: int) -> tuple[Piece, UpgradeQuote]:
        async with self.ctx.db.read() as tx:
            piece = await self.inventory.piece(tx, player.id, gear_id)
        if piece.upgrade >= MAX_UPGRADE:
            raise GameError("این تجهیزات به بیشترین سطح ارتقا رسیده است.")
        return piece, upgrade_quote(piece.item, piece.upgrade)

    async def upgrade(self, player: Player, gear_id: int, expected_level: int) -> UpgradeResult:
        """Try one upgrade step. A failure costs the materials but never the gear."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            piece = await self.inventory.piece(tx, player.id, gear_id)
            if piece.upgrade >= MAX_UPGRADE:
                raise GameError("این تجهیزات به بیشترین سطح ارتقا رسیده است.")
            if piece.upgrade + 1 != expected_level:
                raise GameError("وضعیت این تجهیزات تغییر کرده؛ دوباره «ارتقا» بزن.")
            quote = upgrade_quote(piece.item, piece.upgrade)
            await wallet.apply(tx, player.id, gold=-quote.gold, reason="upgrade", now=now)
            for item_id, qty in quote.materials.items():
                try:
                    await self.inventory.take(tx, player.id, item_id, qty)
                except GameError as err:
                    raise GameError(f"مواد کافی نداری: {get_item(item_id).label} ×{qty}") from err
            success = self.ctx.rng.random() < quote.chance
            if success:
                await inv_repo.set_upgrade(tx, piece.id, quote.next_level)
                piece.upgrade = quote.next_level
        return UpgradeResult(piece, success, quote)
