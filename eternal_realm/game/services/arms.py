"""Hero war gear: buying, owning, equipping four pieces, and what the pieces add to a fighter.

Pieces live in two small tables (``arms_owned`` and ``arms_equipped``), apart from the older ``gear`` and the economy
items, so nothing there is touched. All checks (level, class, the four places, "not in a fight") happen here, on the
server; the fight engine reads the saved loadout, never anything a player sends.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.arms import ARMS, CATEGORIES, MAX_EQUIPPED, Arm, Trait, get_arm
from ..data.stats import Stats
from ..models import Player


@dataclass
class Loadout:
    """What the equipped pieces give: stat bonuses and special traits."""

    slots: list[Arm | None]
    stats: Stats
    traits: list[Trait]

    @property
    def worn(self) -> list[Arm]:
        return [a for a in self.slots if a is not None]


def _loadout(slots: list[Arm | None]) -> Loadout:
    stats = Stats()
    traits: list[Trait] = []
    for arm in slots:
        if arm is not None:
            stats = stats + arm.stats
            traits += arm.traits
    return Loadout(slots, stats, traits)


class ArmsService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # --- reading --------------------------------------------------------------------------------------------------
    async def loadout_in(self, tx: Tx, player_id: int) -> Loadout:
        rows = await tx.fetchall("SELECT slot, arm_id FROM arms_equipped WHERE player_id = ?", (player_id,))
        slots: list[Arm | None] = [None] * MAX_EQUIPPED
        for row in rows:
            if 1 <= row["slot"] <= MAX_EQUIPPED and row["arm_id"] in ARMS:
                slots[row["slot"] - 1] = ARMS[row["arm_id"]]
        return _loadout(slots)

    async def loadout(self, player_id: int) -> Loadout:
        async with self.ctx.db.read() as tx:
            return await self.loadout_in(tx, player_id)

    async def owned(self, player_id: int) -> dict[str, int]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT arm_id, qty FROM arms_owned WHERE player_id = ? AND qty > 0", (player_id,))
        return {r["arm_id"]: r["qty"] for r in rows if r["arm_id"] in ARMS}

    # --- buying ---------------------------------------------------------------------------------------------------
    async def grant(self, tx: Tx, player_id: int, arm_id: str, qty: int = 1) -> None:
        """Put pieces in a hero's chest (used by the coin shop and by delivery of a paid order)."""
        if arm_id not in ARMS:
            raise GameError("این تجهیزات در قلمرو شناخته نمی‌شود.")
        await tx.execute(
            "INSERT INTO arms_owned (player_id, arm_id, qty) VALUES (?, ?, ?)"
            " ON CONFLICT (player_id, arm_id) DO UPDATE SET qty = qty + excluded.qty",
            (player_id, arm_id, qty),
        )

    async def buy(self, player: Player, arm_id: str, qty: int = 1) -> Arm:
        """Buy pieces with coins from the realm treasury. There is no limit on how many a hero may own."""
        if arm_id not in ARMS or qty < 1:
            raise GameError("این تجهیزات در قلمرو شناخته نمی‌شود.")
        arm = get_arm(arm_id)
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(tx, player.id, gold=-arm.price * qty, reason="arm_buy", now=self.ctx.now())
            await self.grant(tx, player.id, arm_id, qty)
        return arm

    # --- equipping ------------------------------------------------------------------------------------------------
    async def _ensure_out_of_fight(self, tx: Tx, player_id: int) -> None:
        busy = (
            await tx.scalar("SELECT 1 FROM solo_fights WHERE player_id = ? AND status = 'active'", (player_id,), 0)
            or await tx.scalar(
                "SELECT 1 FROM duels WHERE status = 'active' AND (challenger_id = ? OR target_id = ?)", (player_id, player_id), 0
            )
            or await tx.scalar(
                "SELECT 1 FROM team_battles b JOIN team_battle_members m ON m.battle_id = b.id"
                " WHERE m.player_id = ? AND b.status = 'active'", (player_id,), 0,
            )
        )
        if busy:
            raise GameError("وسط نبرد نمی‌توانید تجهیزات را عوض کنید؛ اول نبرد را تمام کنید.")

    async def equip(self, player: Player, slot: int, arm_id: str) -> Loadout:
        if not 1 <= slot <= MAX_EQUIPPED or arm_id not in ARMS:
            raise GameError("این جایگاه یا تجهیزات وجود ندارد.")
        arm = get_arm(arm_id)
        async with self.ctx.db.transaction() as tx:
            await self._ensure_out_of_fight(tx, player.id)
            if not await tx.scalar("SELECT qty FROM arms_owned WHERE player_id = ? AND arm_id = ?", (player.id, arm_id), 0):
                raise GameError("این تجهیزات را ندارید؛ اول از خزانه قلمرو بخرید.")
            if player.level < arm.level_req:
                raise GameError(f"«{arm.name}» از سطح {fa(arm.level_req)} قابل استفاده است؛ شما سطح {fa(player.level)} هستید.")
            if arm.classes and player.class_id not in arm.classes:
                from ..data.classes import CLASSES

                raise GameError("«" + arm.name + "» فقط برای " + "، ".join(CLASSES[c].name for c in arm.classes) + " است.")
            await tx.execute("DELETE FROM arms_equipped WHERE player_id = ? AND (slot = ? OR arm_id = ?)", (player.id, slot, arm_id))
            await tx.execute("INSERT INTO arms_equipped (player_id, slot, arm_id) VALUES (?, ?, ?)", (player.id, slot, arm_id))
            return await self.loadout_in(tx, player.id)

    async def unequip(self, player: Player, slot: int) -> Loadout:
        async with self.ctx.db.transaction() as tx:
            await self._ensure_out_of_fight(tx, player.id)
            await tx.execute("DELETE FROM arms_equipped WHERE player_id = ? AND slot = ?", (player.id, slot))
            return await self.loadout_in(tx, player.id)

    def categories(self) -> dict[str, tuple[str, str]]:
        return CATEGORIES
