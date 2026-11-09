"""Bet duels: a player puts something on the table, anyone who can match it accepts, the winner takes the pot.

Both stakes are locked (taken from the players) the moment they are put down, so nobody can win something the
loser no longer has. A bet that nobody accepts is refunded; a drawn duel refunds both.

A bet can also be a piece of gear. The opponent does not need to own one: they pay its value (twice in coins, or a
fraction of it in crystals) or, when they have the same piece, put that up instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import inventory as inv_repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.items import Kind, get_item, item_value
from ..models import Player

OPEN_SECONDS = 300
FEE_PERCENT = 5  # of the pot, on coins and crystals only
LIMITS = {"gold": (10, 1_000_000), "crystal": (1, 500), "item": (1, 1_000), "gear": (1, 1)}
#: matching a gear bet in coins costs this many times the piece's value ...
GOLD_MULTIPLIER = 2
#: ... and in crystals the value divided by this (crystals are worth far more than coins)
CRYSTAL_RATIO = 100


@dataclass
class Bet:
    id: int
    chat_id: int
    message_id: int | None
    challenger_id: int
    accepter_id: int | None
    kind: str
    item_id: str
    amount: int
    status: str
    duel_id: int | None
    expires_at: int
    gear_id: int | None = None
    gear_upgrade: int = 0
    pay_kind: str = ""
    pay_amount: int = 0
    pay_gear_id: int | None = None

    @classmethod
    def from_row(cls, row: Row) -> Bet:
        return cls(
            row["id"], row["chat_id"], row["message_id"], row["challenger_id"], row["accepter_id"], row["kind"],
            row["item_id"], row["amount"], row["status"], row["duel_id"], row["expires_at"], row["gear_id"],
            row["gear_upgrade"], row["pay_kind"], row["pay_amount"], row["pay_gear_id"],
        )

    @property
    def label(self) -> str:
        if self.kind == "gear":
            return gear_label(self.item_id, self.gear_upgrade)
        return stake_label(self.kind, self.item_id, self.amount)

    @property
    def value(self) -> int:
        """What a gear bet is worth in coins."""
        return item_value(get_item(self.item_id), self.gear_upgrade) if self.kind == "gear" else 0

    @property
    def pay_gold(self) -> int:
        return GOLD_MULTIPLIER * self.value

    @property
    def pay_crystal(self) -> int:
        return max(1, math.ceil(self.value / CRYSTAL_RATIO))


@dataclass
class BetOutcome:
    kind: str
    item_id: str
    amount: int
    #: the winner's player id, ``None`` when the stakes went back to both
    winner_id: int | None
    prize: int = 0
    fee: int = 0
    #: gear bets: the piece, what the opponent put against it, and who won (creator or accepter)
    gear: str = ""
    payment: str = ""
    winner_is_creator: bool = False
    fee_label: str = ""

    @property
    def prize_label(self) -> str:
        return stake_label(self.kind, self.item_id, self.prize)


def gear_label(item_id: str, upgrade: int) -> str:
    item = get_item(item_id)
    return f"{item.emoji} {item.name}" + (f" +{fa(upgrade)}" if upgrade else "")


def stake_label(kind: str, item_id: str, amount: int) -> str:
    if kind == "gold":
        return f"🪙 {fa(amount)} سکه"
    if kind == "crystal":
        return f"💎 {fa(amount)} کریستال"
    return f"{get_item(item_id).label} ×{fa(amount)}"


def prize_for(kind: str, amount: int) -> tuple[int, int]:
    """(prize, fee) for the winner of a pot made of two stakes."""
    pot = 2 * amount
    fee = pot * FEE_PERCENT // 100 if kind in ("gold", "crystal") else 0
    return pot - fee, fee


async def _take(tx: Tx, player_id: int, kind: str, item_id: str, amount: int, now: int) -> None:
    if kind == "item":
        if not await inv_repo.remove_stack(tx, player_id, item_id, amount):
            raise GameError(f"{get_item(item_id).label} به اندازه‌ی کافی ندارید.")
        return
    await wallet.apply(tx, player_id, **{kind: -amount}, reason="bet_stake", now=now)


async def _give(tx: Tx, player_id: int, kind: str, item_id: str, amount: int, reason: str, now: int) -> None:
    if kind == "item":
        await inv_repo.add_stack(tx, player_id, item_id, amount)
        return
    await wallet.apply(tx, player_id, **{kind: amount}, reason=reason, now=now)


async def _release_creator(tx: Tx, bet: Bet, now: int) -> None:
    """Give the maker back what they put down (a locked piece is unlocked, coins and resources return)."""
    if bet.kind == "gear":
        await inv_repo.set_listed(tx, bet.gear_id or 0, False)
    else:
        await _give(tx, bet.challenger_id, bet.kind, bet.item_id, bet.amount, "bet_refund", now)


async def _release_payment(tx: Tx, bet: Bet, now: int) -> None:
    """Give the opponent back what they paid or put up."""
    if bet.pay_kind == "gear":
        await inv_repo.set_listed(tx, bet.pay_gear_id or 0, False)
    elif bet.pay_kind in ("gold", "crystal"):
        await _give(tx, int(bet.accepter_id or 0), bet.pay_kind, "", bet.pay_amount, "bet_refund", now)


async def settle(tx: Tx, ctx: AppContext, duel_id: int, winner_player_id: int | None, now: int) -> BetOutcome | None:
    """Called when a duel ends: pay the winner (or refund both on a draw). ``None`` when it was no bet duel."""
    row = await tx.fetchone("SELECT * FROM bet_duels WHERE duel_id = ? AND status = 'active'", (duel_id,))
    if row is None:
        return None
    bet = Bet.from_row(row)
    await tx.execute("UPDATE bet_duels SET status = 'done' WHERE id = ?", (bet.id,))
    if bet.kind == "gear":
        return await _settle_gear(tx, bet, winner_player_id, now)
    if winner_player_id is None:
        for pid in (bet.challenger_id, bet.accepter_id):
            await _give(tx, int(pid), bet.kind, bet.item_id, bet.amount, "bet_refund", now)
        return BetOutcome(bet.kind, bet.item_id, bet.amount, None, bet.amount, 0)
    prize, fee = prize_for(bet.kind, bet.amount)
    await _give(tx, winner_player_id, bet.kind, bet.item_id, prize, "bet_win", now)
    return BetOutcome(bet.kind, bet.item_id, bet.amount, winner_player_id, prize, fee)


async def _settle_gear(tx: Tx, bet: Bet, winner: int | None, now: int) -> BetOutcome:
    gear = bet.label
    payment = {
        "gold": f"🪙 {fa(bet.pay_amount)} سکه", "crystal": f"💎 {fa(bet.pay_amount)} کریستال", "gear": "",
    }.get(bet.pay_kind, "")
    if bet.pay_kind == "gear" and bet.pay_gear_id:
        row = await inv_repo.get_gear(tx, bet.pay_gear_id)
        payment = gear_label(row.item_id, row.upgrade) if row else ""
    out = BetOutcome("gear", bet.item_id, 1, winner, gear=gear, payment=payment)
    if winner is None:
        await _release_creator(tx, bet, now)
        await _release_payment(tx, bet, now)
        return out
    if winner == bet.challenger_id:
        out.winner_is_creator = True
        await _release_creator(tx, bet, now)  # the piece goes home ...
        if bet.pay_kind == "gear":
            await inv_repo.transfer_gear(tx, bet.pay_gear_id or 0, winner)  # ... and takes the opponent's too
        else:
            fee = bet.pay_amount * FEE_PERCENT // 100
            await _give(tx, winner, bet.pay_kind, "", bet.pay_amount - fee, "bet_win", now)
            unit = "سکه" if bet.pay_kind == "gold" else "کریستال"
            out.fee = fee
            out.fee_label = f"{fa(fee)} {unit}"
            out.prize = bet.pay_amount - fee
            out.payment = f"{'🪙' if bet.pay_kind == 'gold' else '💎'} {fa(bet.pay_amount - fee)} {unit}"
        return out
    await inv_repo.transfer_gear(tx, bet.gear_id or 0, winner)  # the opponent wins the piece ...
    await _release_payment(tx, bet, now)  # ... and keeps what they put up
    return out


class BetService:
    def __init__(self, ctx: AppContext, duels) -> None:  # noqa: ANN001 - DuelService
        self.ctx = ctx
        self.duels = duels

    # --- what a player could put down ----------------------------------------------------------------
    async def holdings(self, player_id: int, kind: str, item_id: str = "") -> int:
        async with self.ctx.db.read() as tx:
            if kind == "item":
                return await inv_repo.stack_qty(tx, player_id, item_id)
            player = await player_repo.get(tx, player_id)
        return 0 if player is None else (player.gold if kind == "gold" else player.crystal)

    async def stackable_resources(self, player_id: int) -> list[tuple[str, int]]:
        """The materials the player owns and may bet: ``(item id, quantity)``."""
        async with self.ctx.db.read() as tx:
            stacks = await inv_repo.stacks(tx, player_id)
        return [(i, q) for i, q in stacks if get_item(i).kind is Kind.MATERIAL and get_item(i).tradable and q > 0]

    async def bettable_gear(self, player_id: int) -> list[tuple[int, str, int]]:
        """Pieces that are not worn and not already on the table: ``(gear id, item id, upgrade)``."""
        async with self.ctx.db.read() as tx:
            rows = await inv_repo.list_gear(tx, player_id)
        return [(r.id, r.item_id, r.upgrade) for r in rows if r.slot is None and get_item(r.item_id).tradable]

    def _validate(self, kind: str, item_id: str, amount: int) -> None:
        if kind not in LIMITS:
            raise GameError("نوع شرط درست نیست.")
        low, high = LIMITS[kind]
        if not low <= amount <= high:
            raise GameError(f"مقدار شرط باید بین {fa(low)} تا {fa(high)} باشد.")
        if kind == "item":
            item = get_item(item_id)
            if item.kind is not Kind.MATERIAL or not item.tradable:
                raise GameError("فقط منابع و تجهیزات را می‌شود شرط گذاشت.")

    # --- the bet itself ----------------------------------------------------------------------------------
    async def get(self, bet_id: int) -> Bet | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM bet_duels WHERE id = ?", (bet_id,))
        return Bet.from_row(row) if row else None

    async def open_for(self, player_id: int) -> Bet | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone(
                "SELECT * FROM bet_duels WHERE challenger_id = ? AND status IN ('open', 'active') ORDER BY id DESC LIMIT 1",
                (player_id,),
            )
        return Bet.from_row(row) if row else None

    async def create(
        self, player: Player, chat_id: int, kind: str, item_id: str, amount: int, gear_id: int | None = None
    ) -> Bet:
        now = self.ctx.now()
        if kind == "gear":
            amount = 1
        self._validate(kind, item_id, amount)
        async with self.ctx.db.transaction() as tx:
            left = await player_repo.is_away(tx, player.id, now)
            if left is not None:
                raise player_repo.away_error(left)
            if await tx.fetchone(
                "SELECT 1 FROM bet_duels WHERE challenger_id = ? AND status IN ('open', 'active')", (player.id,)
            ):
                raise GameError("شما همین حالا یک شرط باز دارید؛ اول آن تمام شود یا لغوش کنید.")
            upgrade = 0
            if kind == "gear":
                piece = await inv_repo.get_gear(tx, gear_id or 0)
                if piece is None or piece.player_id != player.id:
                    raise GameError("این تجهیزات در کوله‌پشتی شما نیست.")
                if piece.slot is not None:
                    raise GameError("اول این تجهیزات را از تن خود دربیاورید.")
                if piece.listed:
                    raise GameError("این تجهیزات همین حالا روی تخته‌ی بازار یا شرط دیگری است.")
                if not get_item(piece.item_id).tradable:
                    raise GameError("این آیتم ویژه است و نمی‌شود آن را شرط گذاشت.")
                item_id, upgrade = piece.item_id, piece.upgrade
                await inv_repo.set_listed(tx, piece.id, True)  # locked on the table
            else:
                await _take(tx, player.id, kind, item_id, amount, now)
            bet_id = await tx.execute(
                "INSERT INTO bet_duels (chat_id, challenger_id, kind, item_id, amount, status, created_at, expires_at,"
                " gear_id, gear_upgrade) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)",
                (chat_id, player.id, kind, item_id if kind in ("item", "gear") else "", amount, now, now + OPEN_SECONDS,
                 gear_id if kind == "gear" else None, upgrade),
            )
            row = await tx.fetchone("SELECT * FROM bet_duels WHERE id = ?", (bet_id,))
        assert row is not None
        return Bet.from_row(row)

    async def attach_message(self, bet_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE bet_duels SET message_id = ? WHERE id = ?", (message_id, bet_id))

    async def cancel(self, bet_id: int, player: Player) -> Bet:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM bet_duels WHERE id = ?", (bet_id,))
            if row is None or row["challenger_id"] != player.id:
                raise GameError("فقط سازنده‌ی شرط می‌تواند آن را لغو کند.")
            if row["status"] != "open":
                raise GameError("این شرط دیگر باز نیست.")
            await tx.execute("UPDATE bet_duels SET status = 'cancelled' WHERE id = ?", (bet_id,))
            bet = Bet.from_row(row)
            await _release_creator(tx, bet, now)
        bet.status = "cancelled"
        return bet

    async def _pay_for_gear(self, tx: Tx, bet: Bet, player: Player, pay: str, now: int) -> tuple[str, int, int | None]:
        """Take what the opponent puts against a gear bet: ``(kind, amount, locked gear id)``."""
        if pay == "gold":
            await wallet.apply(tx, player.id, gold=-bet.pay_gold, reason="bet_stake", now=now)
            return "gold", bet.pay_gold, None
        if pay == "crystal":
            await wallet.apply(tx, player.id, crystal=-bet.pay_crystal, reason="bet_stake", now=now)
            return "crystal", bet.pay_crystal, None
        if pay == "gear":
            mine = [r for r in await inv_repo.list_gear(tx, player.id) if r.item_id == bet.item_id and r.slot is None]
            if not mine:
                raise GameError(f"{get_item(bet.item_id).label} را ندارید یا پوشیده‌اید؛ با سکه یا کریستال قبول کنید.")
            piece = min(mine, key=lambda r: r.upgrade)  # the plainest copy goes on the table
            await inv_repo.set_listed(tx, piece.id, True)
            return "gear", 1, piece.id
        raise GameError("روش پرداخت درست نیست.")

    async def accept(self, bet_id: int, player: Player, pay: str = "gold"):  # noqa: ANN201 -> (Bet, Duel, DuelUpdate)
        """Match the stake and start the duel at once. Everything is undone if the duel cannot start.

        For gear bets ``pay`` is how the opponent matches: ``gold``, ``crystal`` or ``gear`` (the same piece).
        """
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM bet_duels WHERE id = ?", (bet_id,))
            if row is None or row["status"] != "open" or row["expires_at"] <= now:
                raise GameError("این شرط دیگر باز نیست؛ یا قبول شده یا مهلتش تمام شده است.")
            if row["challenger_id"] == player.id:
                raise GameError("شرطی را که خودتان بسته‌اید نمی‌توانید قبول کنید؛ منتظر یک حریف بمانید.")
            for pid in (player.id, row["challenger_id"]):
                left = await player_repo.is_away(tx, pid, now)
                if left is not None:
                    raise player_repo.away_error(left, None if pid == player.id else "حریف شرط")
            bet = Bet.from_row(row)
            if bet.kind == "gear":
                kind, amount, gear_id = await self._pay_for_gear(tx, bet, player, pay, now)
                bet.pay_kind, bet.pay_amount, bet.pay_gear_id = kind, amount, gear_id
            else:
                await _take(tx, player.id, bet.kind, bet.item_id, bet.amount, now)
            await tx.execute(
                "UPDATE bet_duels SET status = 'active', accepter_id = ?, pay_kind = ?, pay_amount = ?, pay_gear_id = ?"
                " WHERE id = ?", (player.id, bet.pay_kind, bet.pay_amount, bet.pay_gear_id, bet.id),
            )
            challenger = await player_repo.get(tx, bet.challenger_id)
        assert challenger is not None
        bet.accepter_id = player.id
        try:
            duel = await self.duels.challenge(bet.chat_id, challenger, player)
            update = await self.duels.accept(duel.id, player)
        except Exception:
            async with self.ctx.db.transaction() as tx:  # the duel could not start: give the stake back, reopen the bet
                if bet.kind == "gear":
                    await _release_payment(tx, bet, now)
                else:
                    await _give(tx, player.id, bet.kind, bet.item_id, bet.amount, "bet_refund", now)
                await tx.execute(
                    "UPDATE bet_duels SET status = 'open', accepter_id = NULL, pay_kind = '', pay_amount = 0,"
                    " pay_gear_id = NULL WHERE id = ?", (bet.id,),
                )
            raise
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE bet_duels SET duel_id = ? WHERE id = ?", (duel.id, bet.id))
        bet.duel_id, bet.status = duel.id, "active"
        return bet, duel, update

    async def expire_stale(self) -> list[Bet]:
        """Bets nobody accepted in time: refund the maker."""
        now = self.ctx.now()
        out: list[Bet] = []
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall("SELECT * FROM bet_duels WHERE status = 'open' AND expires_at <= ?", (now,))
            for row in rows:
                bet = Bet.from_row(row)
                await tx.execute("UPDATE bet_duels SET status = 'expired' WHERE id = ?", (bet.id,))
                await _release_creator(tx, bet, now)
                bet.status = "expired"
                out.append(bet)
        return out
