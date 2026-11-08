"""Active blessings and curses, and the altar where a hero may gamble on one."""

from __future__ import annotations

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.effects import EFFECTS, Effect, get_effect
from ..data.stats import Stats
from ..models import Player

ALTAR_PRICE = 400
BLESSING_CHANCE = 0.70


class EffectService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def active_in(self, tx: Tx, player_id: int) -> list[tuple[Effect, int]]:
        """``(effect, seconds left)`` for every effect still running."""
        now = self.ctx.now()
        rows = await tx.fetchall(
            "SELECT effect_id, until FROM player_effects WHERE player_id = ? AND until > ? ORDER BY until",
            (player_id, now),
        )
        return [(get_effect(r["effect_id"]), r["until"] - now) for r in rows]

    async def active(self, player_id: int) -> list[tuple[Effect, int]]:
        async with self.ctx.db.read() as tx:
            return await self.active_in(tx, player_id)

    async def apply_to(self, tx: Tx, player_id: int, stats: Stats) -> Stats:
        for effect, _ in await self.active_in(tx, player_id):
            stats = effect.apply(stats)
        return stats

    async def give(self, tx: Tx, player_id: int, effect: Effect) -> None:
        until = self.ctx.now() + effect.minutes * 60
        await tx.execute(
            "INSERT INTO player_effects (player_id, effect_id, until) VALUES (?, ?, ?)"
            " ON CONFLICT (player_id, effect_id) DO UPDATE SET until = excluded.until",
            (player_id, effect.id, until),
        )

    def roll(self, blessing_chance: float = BLESSING_CHANCE) -> Effect:
        rng = self.ctx.rng
        good = rng.random() < blessing_chance
        return rng.choice([e for e in EFFECTS if e.blessing == good])

    async def pray(self, player: Player) -> Effect:
        """Pay at the altar and receive a random blessing (mostly) or curse."""
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(tx, player.id, gold=-ALTAR_PRICE, reason="altar", now=self.ctx.now())
            effect = self.roll()
            await self.give(tx, player.id, effect)
        return effect

    async def cleanse(self, player: Player) -> int:
        """Remove every curse (free once the altar is visited at all; paid with a small offering)."""
        async with self.ctx.db.transaction() as tx:
            curses = [e for e, _ in await self.active_in(tx, player.id) if not e.blessing]
            if not curses:
                raise GameError("نفرینی بر شما نیست؛ چیزی برای پاک کردن نیست.")
            await wallet.apply(tx, player.id, gold=-ALTAR_PRICE // 2, reason="altar_cleanse", now=self.ctx.now())
            for e in curses:
                await tx.execute("DELETE FROM player_effects WHERE player_id = ? AND effect_id = ?", (player.id, e.id))
        return len(curses)
