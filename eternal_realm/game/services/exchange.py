"""The exchange centre: gold for crystals and crystals for gold, at a fixed rate with a fee the bot keeps."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..models import Player

#: the crystal amounts offered on the buttons
STEPS = (1, 5, 10, 25, 50)
DAY = 24 * 3600


@dataclass
class Quote:
    """What one trade costs and pays."""

    crystals: int
    #: gold the player pays (buying) or receives (selling), the fee already inside
    gold: int
    fee: int


class ExchangeService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # --- prices ---------------------------------------------------------------------------------
    @property
    def rate(self) -> int:
        return self.ctx.balance.exchange_rate

    @property
    def fee_percent(self) -> int:
        return self.ctx.balance.exchange_fee_percent

    def _fee(self, crystals: int) -> int:
        return -(-crystals * self.rate * self.fee_percent // 100)  # rounded up: the bot never loses a coin

    def buy_quote(self, crystals: int) -> Quote:
        fee = self._fee(crystals)
        return Quote(crystals, crystals * self.rate + fee, fee)

    def sell_quote(self, crystals: int) -> Quote:
        fee = self._fee(crystals)
        return Quote(crystals, crystals * self.rate - fee, fee)

    async def bought_today(self, player_id: int) -> int:
        since = self.ctx.now() - DAY
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar(
                "SELECT COALESCE(SUM(crystals), 0) FROM exchange_log WHERE player_id = ? AND direction = 'buy' AND at > ?",
                (player_id, since), 0,
            ))

    async def left_today(self, player_id: int) -> int:
        return max(0, self.ctx.balance.exchange_daily_buy_limit - await self.bought_today(player_id))

    # --- trading --------------------------------------------------------------------------------
    def _check_amount(self, crystals: int) -> None:
        if crystals not in STEPS:
            raise GameError("این مقدار در مرکز مبادله نیست؛ یکی از دکمه‌ها را بزنید.")

    async def buy(self, player: Player, crystals: int) -> Quote:
        """Gold in, crystals out."""
        self._check_amount(crystals)
        quote, now = self.buy_quote(crystals), self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            bought = int(await tx.scalar(
                "SELECT COALESCE(SUM(crystals), 0) FROM exchange_log WHERE player_id = ? AND direction = 'buy' AND at > ?",
                (player.id, now - DAY), 0,
            ))
            limit = self.ctx.balance.exchange_daily_buy_limit
            if bought + crystals > limit:
                raise GameError(
                    f"سقف خرید کریستال در هر شبانه‌روز {fa(limit)} عدد است و شما {fa(bought)} عدد خریده‌اید. "
                    "کمی بعد دوباره بیایید."
                )
            await wallet.apply(tx, player.id, gold=-quote.gold, crystal=crystals, reason="exchange_buy", now=now)
            await self._log(tx, player.id, "buy", quote, now)
        return quote

    async def sell(self, player: Player, crystals: int) -> Quote:
        """Crystals in, gold out."""
        self._check_amount(crystals)
        quote, now = self.sell_quote(crystals), self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(tx, player.id, gold=quote.gold, crystal=-crystals, reason="exchange_sell", now=now)
            await self._log(tx, player.id, "sell", quote, now)
        return quote

    async def _log(self, tx, player_id: int, direction: str, quote: Quote, now: int) -> None:  # noqa: ANN001
        await tx.execute(
            "INSERT INTO exchange_log (player_id, direction, crystals, gold, fee, at) VALUES (?, ?, ?, ?, ?, ?)",
            (player_id, direction, quote.crystals, quote.gold, quote.fee, now),
        )

    async def fees_collected(self) -> int:
        """Everything the bot has kept as fees so far (gold)."""
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT COALESCE(SUM(fee), 0) FROM exchange_log", (), 0))
