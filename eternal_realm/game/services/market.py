"""The player market: escrowed listings, atomic purchases, a fee that leaves the economy."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import market as repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.items import ITEMS, Item, Kind, get_item, item_value
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

    @property
    def label(self) -> str:
        qty = f" ×{self.qty}" if self.qty > 1 else ""
        return f"{self.item.emoji} {self.item.name}{qty}"


def _listing(row) -> Listing:  # noqa: ANN001
    return Listing(
        row["id"], row["seller_id"], row["seller_name"] if "seller_name" in row.keys() else "",
        get_item(row["item_id"]), row["qty"], row["price"],
    )


class MarketService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    #: the week's best seller pays this share instead of the usual fee for the whole next week
    TOP_SELLER_FEE_PERCENT = 2

    def fee_for(self, price: int, top_seller: bool = False) -> int:
        percent = min(self.TOP_SELLER_FEE_PERCENT, self.ctx.balance.market_fee_percent) if top_seller else self.ctx.balance.market_fee_percent
        return max(1, price * percent // 100)

    @staticmethod
    def _week(now: int) -> int:
        return ((now + 12600) // 86400 + 5) // 7

    async def _best_last_week(self, tx, now: int) -> int | None:  # noqa: ANN001
        """The hero who sold the most coins' worth last week (at least MIN_WEEKLY_SALES), else ``None``."""
        week = self._week(now)
        start = (week - 1) * 7 * 86400 - 5 * 86400 - 12600
        row = await tx.fetchone(
            "SELECT seller_id, SUM(amount) AS total FROM market_sales WHERE at >= ? AND at < ? GROUP BY seller_id"
            " ORDER BY total DESC, seller_id LIMIT 1", (start, start + 7 * 86400),
        )
        return row["seller_id"] if row is not None and row["total"] >= self.MIN_WEEKLY_SALES else None

    MIN_WEEKLY_SALES = 1_000

    async def is_top_seller(self, player_id: int) -> bool:
        async with self.ctx.db.read() as tx:
            return await self._best_last_week(tx, self.ctx.now()) == player_id

    async def weekly_sellers(self) -> int | None:
        """Once a week: crown the best seller of the week that just ended (a badge and a message). Returns who."""
        from ...db.repos import titles
        from ..notify import queue

        now = self.ctx.now()
        week = self._week(now)
        async with self.ctx.db.transaction() as tx:
            done = int(await tx.scalar("SELECT value FROM app_settings WHERE key = 'seller_week'", (), 0))
            if done >= week:
                return None
            await tx.execute(
                "INSERT INTO app_settings (key, value) VALUES ('seller_week', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (str(week),),
            )
            best = await self._best_last_week(tx, now)
            if best is None:
                return None
            await titles.award(tx, best, f"seller:{week - 1}", "🛒 فروشنده‌ی برتر بازار", now)
            await queue(
                tx, best, f"seller:{week - 1}",
                "🛒 *فروشنده‌ی برتر هفته شدید!*\n\nنشان «فروشنده‌ی برتر بازار» برای همیشه در پروفایلتان است "
                f"و این هفته کارمزد آگهی‌هایتان فقط {self.TOP_SELLER_FEE_PERCENT}٪ است.", now, "market",
            )
            return best

    def price_range(self, item: Item, qty: int = 1) -> tuple[int, int]:
        """The cheapest and dearest price a listing of this may ask: half to one and a fifth of its real worth."""
        b = self.ctx.balance
        worth = item_value(item) * qty
        low = max(1, -(-worth * b.market_min_percent // 100))
        high = min(b.market_max_price, max(low, worth * b.market_max_percent // 100))
        return low, high

    def _check_price(self, price: int, item: Item, qty: int = 1) -> None:
        if not 1 <= price <= self.ctx.balance.market_max_price:
            raise GameError(f"بها را درست بنویسید: عددی بین ۱ تا {fa(self.ctx.balance.market_max_price)} سکه.")
        low, high = self.price_range(item, qty)
        if not low <= price <= high:
            raise GameError(
                f"بهای این آگهی باید میان {fa(low)} تا {fa(high)} سکه باشد "
                f"(از {fa(self.ctx.balance.market_min_percent)}٪ تا {fa(self.ctx.balance.market_max_percent)}٪ ارزش واقعی)."
            )

    async def _check_slots(self, tx, seller: Player) -> None:  # noqa: ANN001
        if await repo.count_active(tx, seller.id) >= self.ctx.balance.market_max_listings:
            raise GameError(f"روی تخته‌ی بازار حداکثر {self.ctx.balance.market_max_listings} آگهی فعال می‌توانید داشته باشید. یکی را لغو کنید یا صبر کنید تا فروخته شود.")

    async def list_stack(self, seller: Player, item: Item, qty: int, price: int) -> Listing:
        if not item.tradable:
            raise GameError("این آیتم ویژه است و نمی‌شود آن را به دیگران فروخت.")
        if not 1 <= qty <= 10_000:
            raise GameError("تعداد را درست بنویسید؛ مثلاً: 5")
        self._check_price(price, item, qty)
        async with self.ctx.db.transaction() as tx:
            await self._check_slots(tx, seller)
            await self.inventory.take(tx, seller.id, item.id, qty)
            listing_id = await repo.create(tx, seller.id, item.id, qty, None, price, self.ctx.now())
            return Listing(listing_id, seller.id, seller.name, item, qty, price)

    async def browse(
        self, item: Item | None = None, limit: int = 15, offset: int = 0, kinds: set[Kind] | None = None
    ) -> list[Listing]:
        ids = [i.id for i in ITEMS.values() if i.kind in kinds] if kinds is not None else None
        async with self.ctx.db.read() as tx:
            rows = await repo.browse(tx, item.id if item else None, limit, offset, ids)
        return [_listing(r) for r in rows]

    async def page(
        self, kinds: set[Kind] | None, sort: str, page: int, per: int
    ) -> tuple[list[Listing], bool]:
        """One page of active listings. ``sort``: new | cheap | expensive | rare."""
        ids = [i.id for i in ITEMS.values() if i.kind in kinds] if kinds is not None else None
        async with self.ctx.db.read() as tx:
            rows = await repo.browse(tx, None, 500, 0, ids)
        found = [_listing(r) for r in rows]
        keys = {
            "new": lambda x: -x.id,
            "cheap": lambda x: (x.price, -x.id),
            "expensive": lambda x: (-x.price, -x.id),
            "rare": lambda x: (-x.item.rarity, x.price, -x.id),
        }
        found.sort(key=keys.get(sort, keys["new"]))
        start = max(0, page) * per
        return found[start : start + per], len(found) > start + per

    async def get(self, listing_id: int) -> Listing | None:
        """One active listing, with the seller's name (``None`` once it is sold or cancelled)."""
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone(
                "SELECT m.*, p.display_name AS seller_name FROM market_listings m"
                " JOIN players p ON p.id = m.seller_id WHERE m.id = ? AND m.status = 'active'",
                (listing_id,),
            )
        return _listing(row) if row else None

    async def mine(self, seller: Player) -> list[Listing]:
        async with self.ctx.db.read() as tx:
            return [_listing(r) for r in await repo.of_seller(tx, seller.id)]

    async def buy(self, buyer: Player, listing_id: int) -> Listing:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, listing_id)
            if row is None or row["status"] != "active":
                raise GameError("این آگهی دیگر روی تخته نیست؛ یا فروخته شده یا برداشته شده. «بازار» را بنویسید تا آگهی‌های تازه را ببینید.")
            if row["seller_id"] == buyer.id:
                raise GameError("این آگهی خود شماست، فرمانده! اگر پشیمان شدید «لغو شماره» را بنویسید.")
            price = row["price"]
            fee = self.fee_for(price, await self._best_last_week(tx, now) == row["seller_id"])
            # the status flip is the single gate: only one buyer can ever pass it
            if not await repo.close(tx, listing_id, "sold", buyer.id, now):
                raise GameError("افسوس! یک نفر لحظه‌ای زودتر آن را خرید.")
            await wallet.apply(
                tx, buyer.id, gold=-price, reason="market_buy", now=now, ref=f"market:{listing_id}:buy"
            )
            await wallet.apply(
                tx, row["seller_id"], gold=price - fee, reason="market_sell", now=now,
                ref=f"market:{listing_id}:sell",
            )
            await self.inventory.grant(tx, buyer.id, row["item_id"], row["qty"])
            from ..notify import queue

            await tx.execute("INSERT INTO market_sales (seller_id, amount, at) VALUES (?, ?, ?)", (row["seller_id"], price, now))
            sold = get_item(row["item_id"])
            await queue(
                tx, row["seller_id"], f"sold:{listing_id}",
                "🏪 *آگهی شما فروخته شد!*\n\n"
                f"{sold.label}" + (f" ×{fa(row['qty'])}" if row["qty"] > 1 else "") + "\n\n"
                f"🛒 خریدار: {buyer.mention}\n"
                f"🏷️ قیمت آگهی: {fa(price)} سکه\n"
                f"🧾 کارمزد بازار: {fa(fee)} سکه\n"
                f"💰 دریافتی شما: {fa(price - fee)} سکه\n\n"
                "پول به کیف شما رسید؛ آگهی تازه‌ای بگذارید تا بازار گرم بماند.", now,
            )
            return Listing(listing_id, row["seller_id"], "", get_item(row["item_id"]), row["qty"], price)

    async def cancel(self, seller: Player, listing_id: int) -> Listing:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, listing_id)
            if row is None or row["seller_id"] != seller.id:
                raise GameError("چنین آگهی‌ای از شما پیدا نشد. «آگهی‌های من» را بنویسید تا شماره‌ها را ببینید.")
            if not await repo.close(tx, listing_id, "cancelled", None, now):
                raise GameError("این آگهی دیگر روی تخته نیست.")
            await self.inventory.grant(tx, seller.id, row["item_id"], row["qty"])
            return Listing(listing_id, seller.id, seller.name, get_item(row["item_id"]), row["qty"], row["price"])
