"""The player market: escrowed listings, atomic purchases, a fee that leaves the economy."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import inventory as inv_repo
from ...db.repos import market as repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.items import Item, get_item
from ..models import Player
from .inventory import InventoryService


@dataclass
class Listing:
    id: int
    seller_id: int
    seller_name: str
    item: Item
    qty: int
    price: int
    gear_id: int | None
    upgrade: int

    @property
    def label(self) -> str:
        plus = f" +{self.upgrade}" if self.upgrade else ""
        qty = f" ×{self.qty}" if self.qty > 1 else ""
        return f"{self.item.emoji} {self.item.name}{plus}{qty}"


def _listing(row) -> Listing:  # noqa: ANN001
    return Listing(
        row["id"], row["seller_id"], row["seller_name"] if "seller_name" in row.keys() else "",
        get_item(row["item_id"]), row["qty"], row["price"], row["gear_id"],
        (row["upgrade"] if "upgrade" in row.keys() and row["upgrade"] else 0),
    )


class MarketService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    def fee_for(self, price: int) -> int:
        return max(1, price * self.ctx.balance.market_fee_percent // 100)

    def _check_price(self, price: int) -> None:
        if not 1 <= price <= self.ctx.balance.market_max_price:
            raise GameError(f"قیمت باید بین ۱ تا {fa(self.ctx.balance.market_max_price)} سکه باشد.")

    async def _check_slots(self, tx, seller: Player) -> None:  # noqa: ANN001
        if await repo.count_active(tx, seller.id) >= self.ctx.balance.market_max_listings:
            raise GameError(f"حداکثر {self.ctx.balance.market_max_listings} آگهی فعال می‌توانی داشته باشی.")

    async def list_gear(self, seller: Player, gear_id: int, price: int) -> Listing:
        self._check_price(price)
        async with self.ctx.db.transaction() as tx:
            await self._check_slots(tx, seller)
            piece = await self.inventory.piece(tx, seller.id, gear_id)
            if piece.slot is not None:
                raise GameError("اول این تجهیزات را دربیاور.")
            if not piece.item.tradable:
                raise GameError("این آیتم قابل معامله نیست.")
            await inv_repo.set_listed(tx, piece.id, True)
            listing_id = await repo.create(tx, seller.id, piece.item.id, 1, piece.id, price, self.ctx.now())
            return Listing(listing_id, seller.id, seller.name, piece.item, 1, price, piece.id, piece.upgrade)

    async def list_stack(self, seller: Player, item: Item, qty: int, price: int) -> Listing:
        self._check_price(price)
        if item.is_gear:
            raise GameError("برای تجهیزات از شماره‌شان استفاده کن: عرضه #شماره قیمت")
        if not item.tradable:
            raise GameError("این آیتم قابل معامله نیست.")
        if not 1 <= qty <= 10_000:
            raise GameError("تعداد نامعتبر است.")
        async with self.ctx.db.transaction() as tx:
            await self._check_slots(tx, seller)
            await self.inventory.take(tx, seller.id, item.id, qty)
            listing_id = await repo.create(tx, seller.id, item.id, qty, None, price, self.ctx.now())
            return Listing(listing_id, seller.id, seller.name, item, qty, price, None, 0)

    async def browse(self, item: Item | None = None, limit: int = 15) -> list[Listing]:
        async with self.ctx.db.read() as tx:
            return [_listing(r) for r in await repo.browse(tx, item.id if item else None, limit)]

    async def mine(self, seller: Player) -> list[Listing]:
        async with self.ctx.db.read() as tx:
            return [_listing(r) for r in await repo.of_seller(tx, seller.id)]

    async def buy(self, buyer: Player, listing_id: int) -> Listing:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, listing_id)
            if row is None or row["status"] != "active":
                raise GameError("این آگهی دیگر فعال نیست (فروخته یا لغو شده).")
            if row["seller_id"] == buyer.id:
                raise GameError("این آگهی خودت است! برای برداشتنش «لغو <شماره>» بزن.")
            price, fee = row["price"], self.fee_for(row["price"])
            # the status flip is the single gate: only one buyer can ever pass it
            if not await repo.close(tx, listing_id, "sold", buyer.id, now):
                raise GameError("این آگهی همین الان فروخته شد.")
            await wallet.apply(
                tx, buyer.id, gold=-price, reason="market_buy", now=now, ref=f"market:{listing_id}:buy"
            )
            await wallet.apply(
                tx, row["seller_id"], gold=price - fee, reason="market_sell", now=now,
                ref=f"market:{listing_id}:sell",
            )
            if row["gear_id"] is not None:
                await inv_repo.transfer_gear(tx, row["gear_id"], buyer.id)
            else:
                await self.inventory.grant(tx, buyer.id, row["item_id"], row["qty"])
            return Listing(
                listing_id, row["seller_id"], "", get_item(row["item_id"]), row["qty"], price,
                row["gear_id"], 0,
            )

    async def cancel(self, seller: Player, listing_id: int) -> Listing:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, listing_id)
            if row is None or row["seller_id"] != seller.id:
                raise GameError("چنین آگهی‌ای از تو پیدا نشد.")
            if not await repo.close(tx, listing_id, "cancelled", None, now):
                raise GameError("این آگهی دیگر فعال نیست.")
            if row["gear_id"] is not None:
                await inv_repo.set_listed(tx, row["gear_id"], False)
            else:
                await self.inventory.grant(tx, seller.id, row["item_id"], row["qty"])
            return Listing(
                listing_id, seller.id, seller.name, get_item(row["item_id"]), row["qty"], row["price"],
                row["gear_id"], 0,
            )
