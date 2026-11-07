"""Real-money purchases through the Bale wallet.

Lifecycle: ``pending`` (invoice sent) -> ``paid`` -> ``delivered``. Payment confirmation and
delivery happen in one transaction, and the order status is the gate that makes a repeated
callback harmless: a second confirmation finds ``delivered`` and changes nothing.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import orders as repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.packs import ORDER_TTL_SECONDS, PACKS, Pack
from ..models import Player
from .inventory import InventoryService

log = logging.getLogger("eternal_realm.payments")


@dataclass
class Order:
    id: int
    player_id: int
    pack: Pack
    amount: int
    status: str
    payload: str


@dataclass
class Delivery:
    order: Order
    player_id: int
    #: this confirmation was a repeat of one already delivered
    duplicate: bool = False


class PaymentService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def create_order(self, player: Player, pack_id: str) -> Order:
        if not self.ctx.settings.payments_enabled:
            raise GameError("پرداخت فعلاً غیرفعال است.")
        pack = PACKS.get(pack_id)
        if pack is None:
            raise GameError("این بسته وجود ندارد.")
        async with self.ctx.db.transaction() as tx:
            payload = f"ER-{secrets.token_hex(8)}"
            order_id = await repo.create(tx, player.id, pack.id, pack.price_rial, payload, self.ctx.now())
        return Order(order_id, player.id, pack, pack.price_rial, "pending", payload)

    async def check_precheckout(self, platform_user_id: int, payload: str, amount: int) -> str | None:
        """``None`` when the payment may go ahead, else the reason shown to the buyer."""
        async with self.ctx.db.read() as tx:
            row = await repo.by_payload(tx, payload)
        if row is None:
            return "این سفارش پیدا نشد."
        if row["platform_user_id"] != platform_user_id:
            return "این سفارش مال حساب دیگری است."
        if row["status"] != "pending":
            return "این سفارش دیگر معتبر نیست؛ دوباره از فروشگاه ویژه سفارش بده."
        if self.ctx.now() - row["created_at"] > ORDER_TTL_SECONDS:
            return "مهلت پرداخت این سفارش تمام شده؛ دوباره سفارش بده."
        if row["amount"] != amount or row["pack_id"] not in PACKS:
            return "مبلغ سفارش با فروشگاه نمی‌خواند."
        return None

    async def complete(self, platform_user_id: int, payload: str, amount: int, charge_id: str | None) -> Delivery:
        """Confirm a successful payment and hand over the goods, exactly once."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.by_payload(tx, payload)
            if row is None:
                log.error("payment for an unknown order payload %r (user %s)", payload, platform_user_id)
                raise GameError("پرداخت شما ثبت شد ولی سفارش پیدا نشد. با پشتیبانی تماس بگیرید.")
            pack = PACKS[row["pack_id"]]
            order = Order(row["id"], row["player_id"], pack, row["amount"], row["status"], payload)
            if row["status"] in ("delivered", "refunded"):
                return Delivery(order, row["player_id"], duplicate=True)
            if row["platform_user_id"] != platform_user_id or row["amount"] != amount:
                log.error("payment mismatch for order %s (user %s, amount %s)", row["id"], platform_user_id, amount)
                raise GameError("اطلاعات پرداخت با سفارش نمی‌خواند. با پشتیبانی تماس بگیرید.")
            if not await repo.mark_paid(tx, order.id, charge_id or f"none:{payload}", now):
                return Delivery(order, row["player_id"], duplicate=True)
            await self._deliver(tx, order, pack, now)
            await repo.mark_delivered(tx, order.id, now)
            order.status = "delivered"
            return Delivery(order, row["player_id"])

    async def _deliver(self, tx, order: Order, pack: Pack, now: int) -> None:  # noqa: ANN001
        if await player_repo.get(tx, order.player_id) is None:
            raise GameError("بازیکن پیدا نشد.")
        await wallet.apply(
            tx, order.player_id, gold=pack.gold, crystal=pack.crystal, reason=f"order:{pack.id}",
            now=now, ref=f"order:{order.id}",
        )
        for item_id, qty in pack.items.items():
            await self.inventory.grant(tx, order.player_id, item_id, qty)

    async def expire_stale(self) -> int:
        async with self.ctx.db.transaction() as tx:
            return await repo.expire_pending(tx, self.ctx.now() - ORDER_TTL_SECONDS)

    async def history(self, player: Player, limit: int = 10) -> list[Order]:
        async with self.ctx.db.read() as tx:
            rows = await repo.recent_for_player(tx, player.id, limit)
        return [
            Order(r["id"], r["player_id"], PACKS[r["pack_id"]], r["amount"], r["status"], r["payload"])
            for r in rows
            if r["pack_id"] in PACKS
        ]
