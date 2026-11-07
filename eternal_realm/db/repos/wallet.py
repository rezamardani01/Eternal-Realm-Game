"""The only place that changes gold or crystals. Every change leaves a ledger entry."""

from __future__ import annotations

import sqlite3

from ...shared.errors import GameError
from ..database import Tx


class InsufficientFunds(GameError):
    def __init__(self, gold: bool = False, crystal: bool = False) -> None:
        what = "سکه" if gold and not crystal else "کریستال" if crystal and not gold else "موجودی"
        super().__init__(f"{what} کافی نداری.")


class DuplicateOperation(GameError):
    def __init__(self) -> None:
        super().__init__("این عملیات قبلاً انجام شده است.")


async def apply(
    tx: Tx,
    player_id: int,
    *,
    gold: int = 0,
    crystal: int = 0,
    reason: str,
    now: int,
    ref: str | None = None,
) -> None:
    """Atomically add (or subtract) currency.

    ``ref`` makes the operation idempotent: a second call with the same ref raises
    :class:`DuplicateOperation` and, because it runs in the caller's transaction, changes nothing.
    """
    if gold == 0 and crystal == 0:
        return
    await tx.execute(
        "UPDATE players SET gold = gold + ?, crystal = crystal + ?"
        " WHERE id = ? AND gold + ? >= 0 AND crystal + ? >= 0",
        (gold, crystal, player_id, gold, crystal),
    )
    if tx.rowcount == 0:
        raise InsufficientFunds(gold=gold < 0, crystal=crystal < 0)
    try:
        await tx.execute(
            "INSERT INTO transactions (player_id, gold_delta, crystal_delta, reason, ref, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (player_id, gold, crystal, reason, ref, now),
        )
    except sqlite3.IntegrityError as exc:
        if ref is not None:
            raise DuplicateOperation from exc
        raise


async def spent_since(tx: Tx, player_id: int, reason: str, since: int) -> int:
    """Total gold moved out for ``reason`` since a timestamp (positive number)."""
    total = await tx.scalar(
        "SELECT SUM(-gold_delta) FROM transactions"
        " WHERE player_id = ? AND reason = ? AND created_at >= ?",
        (player_id, reason, since),
        default=0,
    )
    return int(total)
