"""The NPC shop: buying, selling and upgrading gear."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import inventory as inv_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.items import MAX_UPGRADE, Item, Kind
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
            raise GameError(f"{item.label} در بازارچه موجود نیست. شاید در «بازار» از دست بازیکنی پیدا شود یا از هیولاها غنیمت گرفته شود.")
        if not 1 <= qty <= MAX_QTY:
            raise GameError(f"هر بار فقط می‌توانید بین ۱ تا {MAX_QTY} عدد بخرید.")
        total = item.buy * qty
        async with self.ctx.db.transaction() as tx:
            if item.is_gear:
                if qty != 1:
                    raise GameError("از هر تجهیزات فقط یکی لازم دارید؛ تعداد را ۱ بگذارید.")
                if await inv_repo.owns_gear(tx, player.id, item.id):
                    raise GameError(
                        f"شما از قبل {item.label} را دارید، فرمانده! خرید دوباره لازم نیست.\n\n"
                        "اگر آن را فروخته‌اید یا در بازار گذاشته‌اید، بعد از برگشتن به کوله‌پشتی می‌توانید دوباره بخرید."
                    )
            await wallet.apply(tx, player.id, gold=-total, reason="shop_buy", now=self.ctx.now())
            await self.inventory.grant(tx, player.id, item.id, qty)
        return total

    async def sell_stack(self, player: Player, item: Item, qty: int) -> int:
        if item.sell <= 0 or item.is_gear:
            raise GameError(f"فروشنده‌ی بازارچه {item.label} را نمی‌خرد. شاید در «بازار» خریداری برایش پیدا شود.")
        if not 1 <= qty <= 10_000:
            raise GameError("تعداد را درست بنویسید؛ مثلاً: 5")
        total = item.sell * qty
        async with self.ctx.db.transaction() as tx:
            await self.inventory.take(tx, player.id, item.id, qty)
            await wallet.apply(tx, player.id, gold=total, reason="shop_sell", now=self.ctx.now())
        return total

    async def sell_gear(self, player: Player, gear_id: int) -> tuple[Piece, int]:
        async with self.ctx.db.transaction() as tx:
            piece = await self.inventory.piece(tx, player.id, gear_id)
            if piece.slot is not None:
                raise GameError("اول این تجهیزات را از تن خود دربیاورید؛ با «درآوردن شماره».")
            if piece.item.sell <= 0:
                raise GameError(f"فروشنده‌ی بازارچه {piece.item.label} را نمی‌خرد؛ آن‌قدر ارزشمند است که فقط در «بازار» می‌توانید بفروشیدش.")
            total = round(piece.item.sell * (1 + 0.5 * piece.upgrade))
            await inv_repo.delete_gear(tx, piece.id)
            await wallet.apply(tx, player.id, gold=total, reason="shop_sell", now=self.ctx.now())
        return piece, total

    async def quote(self, player: Player, gear_id: int) -> tuple[Piece, UpgradeQuote]:
        async with self.ctx.db.read() as tx:
            piece = await self.inventory.piece(tx, player.id, gear_id)
        if piece.upgrade >= MAX_UPGRADE:
            raise GameError("این تجهیزات به بالاترین مرتبه‌ی آهنگری رسیده و دیگر قوی‌تر نمی‌شود. شکوهش را به رخ بکشید!")
        return piece, upgrade_quote(piece.item, piece.upgrade)

    async def upgrade(self, player: Player, gear_id: int, expected_level: int) -> UpgradeResult:
        """Try one upgrade step. A failure costs the materials but never the gear."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            piece = await self.inventory.piece(tx, player.id, gear_id)
            if piece.upgrade >= MAX_UPGRADE:
                raise GameError("این تجهیزات به بالاترین مرتبه‌ی آهنگری رسیده و دیگر قوی‌تر نمی‌شود. شکوهش را به رخ بکشید!")
            if piece.upgrade + 1 != expected_level:
                raise GameError("حال این تجهیزات تغییر کرده است؛ دوباره «ارتقا» و شماره‌اش را بنویسید.")
            quote = upgrade_quote(piece.item, piece.upgrade)
            await wallet.apply(tx, player.id, gold=-quote.gold, reason="upgrade", now=now)
            for item_id, qty in quote.materials.items():
                await self.inventory.take(tx, player.id, item_id, qty)
            success = self.ctx.rng.random() < quote.chance
            if success:
                await inv_repo.set_upgrade(tx, piece.id, quote.next_level)
                piece.upgrade = quote.next_level
        return UpgradeResult(piece, success, quote)
