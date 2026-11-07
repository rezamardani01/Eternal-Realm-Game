"""Moving gold between players."""

from __future__ import annotations

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..models import Player

DAY = 24 * 3600


class EconomyService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def transfer(self, sender: Player, receiver: Player, amount: int) -> int:
        """Send gold. Returns how much of today's allowance is left afterwards."""
        b, now = self.ctx.balance, self.ctx.now()
        if sender.id == receiver.id:
            raise GameError("فرمانده، سکه را از یک جیب خودتان به جیب دیگرِ خودتان که نمی‌شود فرستاد! 😄")
        if receiver.banned:
            raise GameError("این بازیکن از قلمرو تبعید شده و نمی‌شود به او چیزی بخشید.")
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
