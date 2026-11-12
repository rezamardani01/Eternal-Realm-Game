"""Moving gold, crystals, items and materials between players."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import inventory as inv_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.items import get_item
from ..models import Player
from .inventory import InventoryService

DAY = 24 * 3600
CRYSTAL_DAILY_LIMIT = 5_000


@dataclass
class Receipt:
    #: what moved, e.g. ``🪙 ۵۰۰ سکه``
    what: str
    #: how much of today's allowance is left (``None`` for items)
    left: int | None = None
    unit: str = ""


class EconomyService:
    def __init__(self, ctx: AppContext, inventory: InventoryService | None = None) -> None:
        self.ctx = ctx
        self.inventory = inventory

    def _check_pair(self, sender: Player, receiver: Player) -> None:
        if sender.id == receiver.id:
            raise GameError("فرمانده، سکه را از یک جیب خودتان به جیب دیگرِ خودتان که نمی‌شود فرستاد! 😄")
        if receiver.banned:
            raise GameError("این بازیکن از قلمرو تبعید شده و نمی‌شود به او چیزی بخشید.")

    async def transfer(self, sender: Player, receiver: Player, amount: int) -> int:
        """Send gold. Returns how much of today's allowance is left afterwards."""
        b, now = self.ctx.balance, self.ctx.now()
        self._check_pair(sender, receiver)
        if amount < b.transfer_min:
            raise GameError(f"هدیه‌ی شما باید دست‌کم {fa(b.transfer_min)} سکه باشد.")
        async with self.ctx.db.transaction() as tx:
            used = await wallet.spent_since(tx, sender.id, "transfer_out", now - DAY)
            if used + amount > b.transfer_daily_limit:
                left = max(0, b.transfer_daily_limit - used)
                raise GameError(f"خزانه‌دار می‌گوید: هر قهرمان در روز تا {fa(b.transfer_daily_limit)} سکه می‌تواند ببخشد. امروز فقط {fa(left)} سکه‌ی دیگر می‌توانید بفرستید.")
            await wallet.apply(tx, sender.id, gold=-amount, reason="transfer_out", now=now)
            await wallet.apply(tx, receiver.id, gold=amount, reason="transfer_in", now=now)
        return b.transfer_daily_limit - used - amount

    async def send(self, sender: Player, receiver: Player, kind: str, qty: int) -> Receipt:
        """Send ``coin``, ``crystal``, a card (``k_<id>``) or a stackable item id."""
        if qty <= 0:
            raise GameError("تعداد باید دست‌کم ۱ باشد.")
        if kind == "coin":
            left = await self.transfer(sender, receiver, qty)
            return Receipt(f"🪙 {fa(qty)} سکه", left, "سکه")
        self._check_pair(sender, receiver)
        now = self.ctx.now()
        if kind == "crystal":
            async with self.ctx.db.transaction() as tx:
                used = await wallet.spent_since(tx, sender.id, "crystal_out", now - DAY, currency="crystal")
                if used + qty > CRYSTAL_DAILY_LIMIT:
                    raise GameError(
                        f"هر قهرمان در روز تا {fa(CRYSTAL_DAILY_LIMIT)} کریستال می‌تواند ببخشد. "
                        f"امروز فقط {fa(max(0, CRYSTAL_DAILY_LIMIT - used))} کریستال‌ی دیگر می‌توانید بفرستید."
                    )
                await wallet.apply(tx, sender.id, crystal=-qty, reason="crystal_out", now=now)
                await wallet.apply(tx, receiver.id, crystal=qty, reason="crystal_in", now=now)
            return Receipt(f"💎 {fa(qty)} کریستال", CRYSTAL_DAILY_LIMIT - used - qty, "کریستال")
        assert self.inventory is not None
        if kind.startswith("k_"):
            from ..data.cards import get_card

            card = get_card(kind[2:])
            async with self.ctx.db.transaction() as tx:
                row = await tx.fetchone(
                    "SELECT qty FROM player_cards WHERE player_id = ? AND card_id = ?", (sender.id, card.id)
                )
                if row is None or row["qty"] - qty < 1:
                    raise GameError("فقط کارت‌های تکراری را می‌شود بخشید؛ یک نسخه همیشه در آلبوم شما می‌ماند.")
                await tx.execute(
                    "UPDATE player_cards SET qty = qty - ? WHERE player_id = ? AND card_id = ?", (qty, sender.id, card.id)
                )
                await tx.execute(
                    "INSERT INTO player_cards (player_id, card_id, qty, first_at) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT (player_id, card_id) DO UPDATE SET qty = qty + excluded.qty",
                    (receiver.id, card.id, qty, now),
                )
            return Receipt(f"🃏 {card.name} ×{fa(qty)}")
        item = get_item(kind)
        if not item.tradable:
            raise GameError(f"{item.label} قابل انتقال نیست.")
        async with self.ctx.db.transaction() as tx:
            await self.inventory.take(tx, sender.id, item.id, qty)
            await self.inventory.grant(tx, receiver.id, item.id, qty)
        return Receipt(f"{item.label} ×{fa(qty)}")
