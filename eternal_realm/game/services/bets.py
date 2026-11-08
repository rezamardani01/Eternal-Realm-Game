"""Bet duels: a player puts something on the table, anyone who can match it accepts, the winner takes the pot.

Both stakes are locked (taken from the players) the moment they are put down, so nobody can win something the
loser no longer has. A bet that nobody accepts is refunded; a drawn duel refunds both.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import inventory as inv_repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.items import Kind, get_item
from ..models import Player

OPEN_SECONDS = 300
FEE_PERCENT = 5  # of the pot, on coins and crystals only
LIMITS = {"gold": (10, 1_000_000), "crystal": (1, 500), "item": (1, 1_000)}


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

    @classmethod
    def from_row(cls, row: Row) -> Bet:
        return cls(
            row["id"], row["chat_id"], row["message_id"], row["challenger_id"], row["accepter_id"], row["kind"],
            row["item_id"], row["amount"], row["status"], row["duel_id"], row["expires_at"],
        )

    @property
    def label(self) -> str:
        return stake_label(self.kind, self.item_id, self.amount)


@dataclass
class BetOutcome:
    kind: str
    item_id: str
    amount: int
    #: the winner's player id, ``None`` when the stakes went back to both
    winner_id: int | None
    prize: int = 0
    fee: int = 0

    @property
    def prize_label(self) -> str:
        return stake_label(self.kind, self.item_id, self.prize)


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


async def _take(tx: Tx, player_id: int, kind: str, item_id: str, amount: int, bet_id: int, now: int) -> None:
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


async def settle(tx: Tx, ctx: AppContext, duel_id: int, winner_player_id: int | None, now: int) -> BetOutcome | None:
    """Called when a duel ends: pay the winner (or refund both on a draw). ``None`` when it was no bet duel."""
    row = await tx.fetchone("SELECT * FROM bet_duels WHERE duel_id = ? AND status = 'active'", (duel_id,))
    if row is None:
        return None
    bet = Bet.from_row(row)
    await tx.execute("UPDATE bet_duels SET status = 'done' WHERE id = ?", (bet.id,))
    if winner_player_id is None:
        for pid in (bet.challenger_id, bet.accepter_id):
            await _give(tx, int(pid), bet.kind, bet.item_id, bet.amount, "bet_refund", now)
        return BetOutcome(bet.kind, bet.item_id, bet.amount, None, bet.amount, 0)
    prize, fee = prize_for(bet.kind, bet.amount)
    await _give(tx, winner_player_id, bet.kind, bet.item_id, prize, "bet_win", now)
    return BetOutcome(bet.kind, bet.item_id, bet.amount, winner_player_id, prize, fee)


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

    def _validate(self, kind: str, item_id: str, amount: int) -> None:
        if kind not in LIMITS:
            raise GameError("نوع شرط درست نیست.")
        low, high = LIMITS[kind]
        if not low <= amount <= high:
            raise GameError(f"مقدار شرط باید بین {fa(low)} تا {fa(high)} باشد.")
        if kind == "item":
            item = get_item(item_id)
            if item.kind is not Kind.MATERIAL or not item.tradable:
                raise GameError("فقط منابع را می‌شود شرط گذاشت.")

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

    async def create(self, player: Player, chat_id: int, kind: str, item_id: str, amount: int) -> Bet:
        self._validate(kind, item_id, amount)
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            if await tx.fetchone(
                "SELECT 1 FROM bet_duels WHERE challenger_id = ? AND status IN ('open', 'active')", (player.id,)
            ):
                raise GameError("شما همین حالا یک شرط باز دارید؛ اول آن تمام شود یا لغوش کنید.")
            await _take(tx, player.id, kind, item_id, amount, 0, now)
            bet_id = await tx.execute(
                "INSERT INTO bet_duels (chat_id, challenger_id, kind, item_id, amount, status, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
                (chat_id, player.id, kind, item_id if kind == "item" else "", amount, now, now + OPEN_SECONDS),
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
            await _give(tx, player.id, bet.kind, bet.item_id, bet.amount, "bet_refund", now)
        bet.status = "cancelled"
        return bet

    async def accept(self, bet_id: int, player: Player):  # noqa: ANN201 -> (Bet, Duel, DuelUpdate)
        """Match the stake and start the duel at once. Everything is undone if the duel cannot start."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM bet_duels WHERE id = ?", (bet_id,))
            if row is None or row["status"] != "open" or row["expires_at"] <= now:
                raise GameError("این شرط دیگر باز نیست؛ یا قبول شده یا مهلتش تمام شده است.")
            if row["challenger_id"] == player.id:
                raise GameError("شرطی را که خودتان بسته‌اید نمی‌توانید قبول کنید؛ منتظر یک حریف بمانید.")
            bet = Bet.from_row(row)
            await _take(tx, player.id, bet.kind, bet.item_id, bet.amount, bet.id, now)
            await tx.execute("UPDATE bet_duels SET status = 'active', accepter_id = ? WHERE id = ?", (player.id, bet.id))
            challenger = await player_repo.get(tx, bet.challenger_id)
        assert challenger is not None
        try:
            duel = await self.duels.challenge(bet.chat_id, challenger, player)
            update = await self.duels.accept(duel.id, player)
        except Exception:
            async with self.ctx.db.transaction() as tx:  # the duel could not start: give the stake back, reopen the bet
                await _give(tx, player.id, bet.kind, bet.item_id, bet.amount, "bet_refund", now)
                await tx.execute("UPDATE bet_duels SET status = 'open', accepter_id = NULL WHERE id = ?", (bet.id,))
            raise
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE bet_duels SET duel_id = ? WHERE id = ?", (duel.id, bet.id))
        bet.duel_id, bet.accepter_id, bet.status = duel.id, player.id, "active"
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
                await _give(tx, bet.challenger_id, bet.kind, bet.item_id, bet.amount, "bet_refund", now)
                bet.status = "expired"
                out.append(bet)
        return out
