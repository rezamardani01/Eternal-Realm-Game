"""Daily missions: made on first look each day, advanced by deeds, paid once."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import players as player_repo
from ...db.repos import season as season_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.missions import get_kind, pick, reward_for
from ..models import Player
from .offers import OfferService


@dataclass
class MissionView:
    slot: int
    kind_id: str
    emoji: str
    title: str
    progress: int
    target: int
    gold: int
    claimed: bool

    @property
    def done(self) -> bool:
        return self.progress >= self.target


def today(now: int) -> int:
    return (now + 12600) // 86400


class MissionService:
    def __init__(self, ctx: AppContext, offers: OfferService) -> None:
        self.ctx = ctx
        self.offers = offers

    async def today(self, player: Player) -> list[MissionView]:
        now = self.ctx.now()
        day = today(now)
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT * FROM daily_missions WHERE player_id = ? AND day = ? ORDER BY slot", (player.id, day)
            )
            if not rows:
                fresh = await player_repo.get(tx, player.id)
                assert fresh is not None
                facts = await self.offers.facts(tx, fresh)
                for slot, kind in enumerate(pick(facts, player.id, day)):
                    await tx.execute(
                        "INSERT INTO daily_missions (player_id, day, slot, kind_id, deed, target, progress, claimed)"
                        " VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
                        (player.id, day, slot, kind.id, kind.deed, kind.target),
                    )
                rows = await tx.fetchall(
                    "SELECT * FROM daily_missions WHERE player_id = ? AND day = ? ORDER BY slot", (player.id, day)
                )
            level = (await player_repo.get(tx, player.id)).level  # type: ignore[union-attr]
        out = []
        for r in rows:
            kind = get_kind(r["kind_id"])
            out.append(MissionView(r["slot"], kind.id, kind.emoji, kind.title, r["progress"], r["target"],
                                   reward_for(kind, level), bool(r["claimed"])))
        return out

    async def claim(self, player: Player, slot: int) -> MissionView:
        now = self.ctx.now()
        day = today(now)
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT * FROM daily_missions WHERE player_id = ? AND day = ? AND slot = ?", (player.id, day, slot)
            )
            if row is None:
                raise GameError("این مأموریت برای امروز نیست.")
            if row["claimed"]:
                raise GameError("پاداش این مأموریت را قبلاً گرفته‌اید.")
            if row["progress"] < row["target"]:
                raise GameError("هنوز این مأموریت تمام نشده؛ کارش را به پایان برسانید.")
            kind = get_kind(row["kind_id"])
            fresh = await player_repo.get(tx, player.id)
            assert fresh is not None
            gold = reward_for(kind, fresh.level)
            await tx.execute(
                "UPDATE daily_missions SET claimed = 1 WHERE player_id = ? AND day = ? AND slot = ?",
                (player.id, day, slot),
            )
            await wallet.apply(
                tx, player.id, gold=gold, reason="mission", now=now, ref=f"mission:{player.id}:{day}:{slot}"
            )
            await season_repo.add_points(tx, player.id, "mission", now)
        return MissionView(slot, kind.id, kind.emoji, kind.title, row["progress"], row["target"], gold, True)
