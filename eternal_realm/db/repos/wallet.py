"""The only place that changes gold or crystals. Every change leaves a ledger entry."""

from __future__ import annotations

import sqlite3

from ...shared.errors import GameError
from ..database import Tx


_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _num(value: int) -> str:
    return f"{value:,}".replace(",", "٬").translate(_FA)


class InsufficientFunds(GameError):
    """Not enough gold/crystal. The message states what the player has and what is needed."""

    def __init__(self, shortages: list[tuple[str, str, int, int]]) -> None:
        # each shortage: (icon, name, have, need)
        lines = ["💸 کیسه‌ی شما برای این کار کافی نیست.", ""]
        for icon, name, have, need in shortages:
            lines.append(f"{icon} {name}: دارید {_num(have)} · نیاز دارید {_num(need)} · کمبود {_num(need - have)}")
        lines.append("")
        if any(name == "کریستال" for _, name, _, _ in shortages):
            lines.append("💡 کریستال از «خزانه‌ی ویژه» یا گنج‌های کمیاب ماجراجویی به دست می‌آید.")
        else:
            lines.append("💡 با ماهیگیری، معدن، شکار و جایزه‌ی روزانه سکه جمع کنید.")
        super().__init__("\n".join(lines))


class DuplicateOperation(GameError):
    def __init__(self) -> None:
        super().__init__("این کار پیش‌تر انجام شده است و نیازی به تکرار نیست.")


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
        row = await tx.fetchone("SELECT gold, crystal FROM players WHERE id = ?", (player_id,))
        have_gold, have_crystal = (row["gold"], row["crystal"]) if row else (0, 0)
        shortages = []
        if gold < 0 and have_gold + gold < 0:
            shortages.append(("🪙", "سکه", have_gold, -gold))
        if crystal < 0 and have_crystal + crystal < 0:
            shortages.append(("💎", "کریستال", have_crystal, -crystal))
        raise InsufficientFunds(shortages)
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


async def spent_since(tx: Tx, player_id: int, reason: str, since: int, currency: str = "gold") -> int:
    """Total gold (or crystal) moved out for ``reason`` since a timestamp (positive number)."""
    column = "crystal_delta" if currency == "crystal" else "gold_delta"
    total = await tx.scalar(
        f"SELECT SUM(-{column}) FROM transactions"  # noqa: S608
        " WHERE player_id = ? AND reason = ? AND created_at >= ?",
        (player_id, reason, since),
        default=0,
    )
    return int(total)
