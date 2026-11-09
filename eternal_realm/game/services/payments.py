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
from ..data import lucky
from ..data.items import get_item
from ..data.deals import find_deal
from ..data.packs import ORDER_TTL_SECONDS, PACKS, Pack
from ..engine import progression
from ...shared.text import fa
from ..models import Player
from .inventory import InventoryService

log = logging.getLogger("eternal_realm.payments")


def describe_haul(gold: int, crystal: int, items: dict[str, int]) -> str:
    """One line per kind of reward, e.g. for the buyer's receipt."""
    from ...shared.text import fa

    lines = []
    if gold:
        lines.append(f"🪙 {fa(gold)} سکه")
    if crystal:
        lines.append(f"💎 {fa(crystal)} کریستال")
    lines += [f"{get_item(i).label} ×{fa(q)}" for i, q in items.items()]
    return "\n".join(lines)


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
    #: what a lucky bundle turned out to contain (empty for fixed packs)
    granted: str = ""


XP_PACK_IDS = tuple(p.id for p in PACKS.values() if p.xp)


class PaymentService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def create_order(self, player: Player, pack_id: str, *, deal: bool = False) -> Order:
        if not self.ctx.settings.payments_enabled:
            raise GameError("دروازه‌ی پرداخت فعلاً بسته است. کمی بعد دوباره سر بزنید.")
        pack = PACKS.get(pack_id)
        if pack is None:
            raise GameError("چنین بسته‌ای در خزانه نیست.")
        amount = pack.price_rial
        if pack.season:
            from ...db.repos import season as season_repo

            async with self.ctx.db.read() as tx:
                st = await season_repo.state(tx, player.id, self.ctx.now())
            if st.premium:
                raise GameError("بلیط این فصل را از قبل دارید؛ خرید دوباره لازم نیست و پولی کسر نشد.")
        if pack.xp:
            await self._check_xp_pack(player, pack)
        if pack.pet:
            async with self.ctx.db.read() as tx:
                have = await tx.fetchone(
                    "SELECT 1 FROM player_pets WHERE player_id = ? AND pet_id = ?", (player.id, pack.pet)
                )
            if have is not None:
                raise GameError("این حیوان همراه از قبل مال شماست؛ خرید دوباره لازم نیست و از شما پولی کسر نشد.")
        if deal:
            todays = find_deal(self.ctx.now(), pack_id)
            if todays is None:
                raise GameError("این تخفیف مال امروز نیست یا تمام شده است. «تخفیف‌های امروز» را دوباره باز کنید.")
            amount = todays.price_rial
        async with self.ctx.db.transaction() as tx:
            payload = f"ER-{secrets.token_hex(8)}"
            order_id = await repo.create(tx, player.id, pack.id, amount, payload, self.ctx.now())
        return Order(order_id, player.id, pack, amount, "pending", payload)

    async def _check_xp_pack(self, player: Player, pack: Pack) -> None:
        """Experience packs are for climbing, not for the top: a level limit and a few per week."""
        from ..data.packs import XP_PACK_MAX_LEVEL, XP_PACK_WEEKLY_LIMIT

        if player.level > XP_PACK_MAX_LEVEL:
            raise GameError(
                f"⭐ بسته‌های تجربه برای قهرمان‌های تا سطح {fa(XP_PACK_MAX_LEVEL)} است؛ شما سطح {fa(player.level)} هستید. "
                "پولی از شما کسر نشد."
            )
        week_ago = self.ctx.now() - 7 * 86400
        async with self.ctx.db.read() as tx:
            bought = int(await tx.scalar(
                "SELECT COUNT(*) FROM orders WHERE player_id = ? AND status = 'delivered' AND delivered_at >= ?"
                " AND pack_id IN (" + ",".join("?" * len(XP_PACK_IDS)) + ")",
                (player.id, week_ago, *XP_PACK_IDS), 0,
            ))
        if bought >= XP_PACK_WEEKLY_LIMIT:
            raise GameError(
                f"⭐ در هر هفته حداکثر {fa(XP_PACK_WEEKLY_LIMIT)} بسته‌ی تجربه می‌شود خرید و شما سهمیه‌ی این هفته را "
                "گرفته‌اید. پولی از شما کسر نشد؛ هفته‌ی بعد دوباره بیایید."
            )

    async def check_precheckout(self, platform_user_id: int, payload: str, amount: int) -> str | None:
        """``None`` when the payment may go ahead, else the reason shown to the buyer."""
        async with self.ctx.db.read() as tx:
            row = await repo.by_payload(tx, payload)
        if row is None:
            return "این سفارش در دفتر خزانه پیدا نشد."
        if row["platform_user_id"] != platform_user_id:
            return "این سفارش برای قهرمان دیگری ثبت شده است."
        if row["status"] != "pending":
            return "این سفارش دیگر معتبر نیست؛ از «خزانه قلمرو» دوباره سفارش بدهید."
        if self.ctx.now() - row["created_at"] > ORDER_TTL_SECONDS:
            return "مهلت پرداخت این سفارش تمام شده است؛ دوباره سفارش بدهید."
        if row["amount"] != amount or row["pack_id"] not in PACKS:
            return "مبلغ پرداخت با قیمت بسته نمی‌خواند؛ از «خزانه قلمرو» دوباره سفارش بدهید."
        return None

    async def complete(self, platform_user_id: int, payload: str, amount: int, charge_id: str | None) -> Delivery:
        """Confirm a successful payment and hand over the goods, exactly once."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.by_payload(tx, payload)
            if row is None:
                log.error("payment for an unknown order payload %r (user %s)", payload, platform_user_id)
                raise GameError("پرداخت شما رسید اما سفارش پیدا نشد. نگران نباشید، با پشتیبانی تماس بگیرید تا درستش کنیم.")
            pack = PACKS[row["pack_id"]]
            order = Order(row["id"], row["player_id"], pack, row["amount"], row["status"], payload)
            if row["status"] in ("delivered", "refunded"):
                return Delivery(order, row["player_id"], duplicate=True)
            if row["platform_user_id"] != platform_user_id or row["amount"] != amount:
                log.error("payment mismatch for order %s (user %s, amount %s)", row["id"], platform_user_id, amount)
                raise GameError("اطلاعات پرداخت با سفارش نمی‌خواند. نگران نباشید، با پشتیبانی تماس بگیرید تا بررسی کنیم.")
            if not await repo.mark_paid(tx, order.id, charge_id or f"none:{payload}", now):
                return Delivery(order, row["player_id"], duplicate=True)
            granted = await self._deliver(tx, order, pack, now)
            await repo.mark_delivered(tx, order.id, now)
            order.status = "delivered"
            return Delivery(order, row["player_id"], granted=granted)

    async def _deliver(self, tx, order: Order, pack: Pack, now: int) -> str:  # noqa: ANN001
        """Grant the goods; returns a description of what a lucky bundle contained."""
        if await player_repo.get(tx, order.player_id) is None:
            raise GameError("بازیکن پیدا نشد.")
        gold, crystal, items, granted = pack.gold, pack.crystal, dict(pack.items), ""
        if pack.lucky:
            haul = lucky.roll(pack.id, lucky.theme_of_day(now), self.ctx.rng)
            gold, crystal, items = haul.gold, haul.crystal, haul.items
            granted = describe_haul(gold, crystal, items)
        await wallet.apply(
            tx, order.player_id, gold=gold, crystal=crystal, reason=f"order:{pack.id}",
            now=now, ref=f"order:{order.id}",
        )
        for item_id, qty in items.items():
            await self.inventory.grant(tx, order.player_id, item_id, qty)
        if pack.boost_hours:
            await tx.execute(
                "UPDATE players SET boost_until = MAX(boost_until, ?) + ? WHERE id = ?",
                (now, pack.boost_hours * 3600, order.player_id),
            )
        if pack.xp:
            buyer = await player_repo.get(tx, order.player_id)
            assert buyer is not None
            level, xp, gained = progression.apply_xp(buyer.level, buyer.xp, pack.xp, self.ctx.balance)
            await player_repo.set_progress(tx, order.player_id, level, xp)
            granted = f"⭐ {fa(pack.xp)} تجربه به شما رسید\n" + (
                f"🎉 از سطح {fa(buyer.level)} به سطح {fa(level)} رسیدید" if gained else "هنوز به سطح بعد نرسیده‌اید؛ ادامه بدهید"
            )
        if pack.spins:
            await tx.execute("UPDATE players SET wheel_spins = wheel_spins + ? WHERE id = ?", (pack.spins, order.player_id))
            granted = f"🎡 {fa(pack.spins)} فرصت گردونه شانس به شما رسید؛ همین حالا بچرخانید!"
        if pack.vip_days:
            await tx.execute(
                "UPDATE players SET vip_until = MAX(vip_until, ?) + ? WHERE id = ?",
                (now, pack.vip_days * 86400, order.player_id),
            )
        if pack.season:
            from ...db.repos import season as season_repo

            if not await season_repo.grant_ticket(tx, order.player_id, now):
                await wallet.apply(
                    tx, order.player_id, crystal=100, reason=f"order:{pack.id}:duplicate_ticket", now=now,
                    ref=f"order:{order.id}:ticket",
                )
                granted = "بلیط این فصل را داشتید؛ ۱۰۰ کریستال جایگزین شد."
        if pack.pet:
            from .pets import PetService

            if not await PetService(self.ctx).grant(tx, order.player_id, pack.pet):
                # bought twice in flight: pay it back in crystals instead of losing the money
                await wallet.apply(
                    tx, order.player_id, crystal=20, reason=f"order:{pack.id}:duplicate_pet", now=now,
                    ref=f"order:{order.id}:pet",
                )
                granted = "حیوان از قبل را داشتید؛ ۲۰ کریستال جایگزین شد."
        return granted

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
