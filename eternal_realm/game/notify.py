"""Messages the bot sends a hero on its own: queued inside the transaction that caused them, delivered later.

A queued message is keyed, so the same news is never sent twice (an achievement step, a finished boost...).
"""

from __future__ import annotations

from ..db.database import Tx
from ..shared.text import fa
from .data.achievements import FAMILIES, reward_text


async def queue(tx: Tx, player_id: int, key: str, text: str, now: int, screen: str = "", arg: str = "") -> None:
    await tx.execute(
        "INSERT OR IGNORE INTO player_alerts (player_id, key, text, screen, arg, created_at, sent) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (player_id, key, text, screen, arg, now),
    )


async def achievement_check(tx: Tx, player_id: int, metric: str, value: int, now: int) -> None:
    """Tell the hero when an achievement step has just come within reach (once per step)."""
    for family in FAMILIES:
        if family.metric != metric:
            continue
        claimed = {
            r["step"] for r in await tx.fetchall(
                "SELECT step FROM achievement_claims WHERE player_id = ? AND family = ?", (player_id, family.id)
            )
        }
        for number, step in enumerate(family.steps, 1):
            if value >= step.target and number not in claimed:
                text = (
                    f"🏅 *دستاورد باز شد!*\n\n"
                    f"{family.emoji} {family.name} — مرحله‌ی {fa(number)}\n"
                    f"{family.how.format(n=fa(step.target))}\n\n"
                    f"🎁 پاداش: {reward_text(step)}"
                )
                await queue(tx, player_id, f"ach:{family.id}:{number}", text, now, "achf", family.id)
