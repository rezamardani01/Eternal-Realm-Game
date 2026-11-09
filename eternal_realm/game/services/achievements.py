"""Achievements: progress is read from deed counters and live facts; every step is paid once."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.achievements import FAMILIES, Family, Step, get_family
from ..models import Player
from .inventory import InventoryService


@dataclass
class FamilyView:
    family: Family
    value: int
    #: how many steps are already paid
    paid: int

    @property
    def step(self) -> Step | None:
        """The step being worked on (the first unpaid one), or ``None`` when all three are paid."""
        return self.family.steps[self.paid] if self.paid < len(self.family.steps) else None

    @property
    def claimable(self) -> bool:
        step = self.step
        return step is not None and self.value >= step.target

    @property
    def finished(self) -> bool:
        return self.paid >= len(self.family.steps)


class AchievementService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def _values(self, tx: Tx, player: Player) -> dict[str, int]:
        pid = player.id
        fresh = await tx.fetchone("SELECT level, daily_streak FROM players WHERE id = ?", (pid,))
        deeds = {
            r["deed"]: r["n"] for r in await tx.fetchall("SELECT deed, n FROM deed_counts WHERE player_id = ?", (pid,))
        }
        values = {f"deed:{d}": n for d, n in deeds.items()}
        values["level"] = fresh["level"]
        values["streak"] = fresh["daily_streak"]
        values["pets"] = int(await tx.scalar("SELECT COUNT(*) FROM player_pets WHERE player_id = ?", (pid,), 0))
        values["cards"] = int(await tx.scalar("SELECT COUNT(*) FROM player_cards WHERE player_id = ?", (pid,), 0))
        values["invites"] = int(await tx.scalar("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (pid,), 0))
        return values

    async def _paid(self, tx: Tx, player_id: int) -> dict[str, int]:
        rows = await tx.fetchall(
            "SELECT family, COUNT(*) AS n FROM achievement_claims WHERE player_id = ? GROUP BY family", (player_id,)
        )
        return {r["family"]: r["n"] for r in rows}

    async def overview(self, player: Player) -> list[FamilyView]:
        async with self.ctx.db.read() as tx:
            values = await self._values(tx, player)
            paid = await self._paid(tx, player.id)
        return [FamilyView(f, values.get(f.metric, 0), paid.get(f.id, 0)) for f in FAMILIES]

    async def view(self, player: Player, family_id: str) -> FamilyView:
        family = get_family(family_id)
        return next(v for v in await self.overview(player) if v.family is family)

    async def claimable_count(self, player: Player) -> int:
        return sum(1 for v in await self.overview(player) if v.claimable)

    async def claim(self, player: Player, family_id: str) -> tuple[Family, int, Step]:
        """Pay the family's next step if it is reached. Returns the family, the step number (1-3) and the step."""
        try:
            family = get_family(family_id)
        except KeyError:
            raise GameError("این دستاورد پیدا نشد.") from None
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            values = await self._values(tx, player)
            paid = (await self._paid(tx, player.id)).get(family.id, 0)
            if paid >= len(family.steps):
                raise GameError("همه‌ی مرحله‌های این دستاورد را گرفته‌اید.")
            step = family.steps[paid]
            if values.get(family.metric, 0) < step.target:
                raise GameError("هنوز به این مرحله نرسیده‌اید؛ کارش را ادامه دهید.")
            await tx.execute(
                "INSERT INTO achievement_claims (player_id, family, step, claimed_at) VALUES (?, ?, ?, ?)",
                (player.id, family.id, paid + 1, now),
            )
            await wallet.apply(
                tx, player.id, gold=step.gold, crystal=step.crystal, reason="achievement", now=now,
                ref=f"ach:{player.id}:{family.id}:{paid + 1}",
            )
            for item_id, qty in step.items:
                await self.inventory.grant(tx, player.id, item_id, qty)
            if step.pet:
                from .pets import PetService

                if not await PetService(self.ctx).grant(tx, player.id, step.pet):  # already owned: crystals instead
                    await wallet.apply(
                        tx, player.id, crystal=20, reason="achievement_pet", now=now,
                        ref=f"ach:{player.id}:{family.id}:{paid + 1}:pet",
                    )
            if step.title:
                await tx.execute("UPDATE players SET title = ? WHERE id = ? AND title = ''", (step.title, player.id))
        return family, paid + 1, step
