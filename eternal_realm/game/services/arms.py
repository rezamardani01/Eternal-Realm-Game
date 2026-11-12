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
from ..data.arms import (
    ARMS, CATEGORIES, MAX_EQUIPPED, MAX_UPGRADE, UPGRADE_CHANCE, Arm, Trait, get_arm, upgrade_gold, upgrade_materials,
    upgraded_stats,
)
from ..data.growth import slots_open
from ..data.stats import Stats
from ..models import Player


#: the pieces free players can find, and how likely each rarity is among them
FREE_MAX_RARITY = 2
FREE_WEIGHT = {1: 70, 2: 30}
#: chance of a find: a won hunt, a won fight of the trip, a chest, a fighter of a boss
FREE_CHANCE = {"hunt": 0.06, "trip": 0.08, "chest": 0.15, "boss": 0.25}


@dataclass
class Loadout:
    """What the equipped pieces give: stat bonuses and special traits."""

    slots: list[Arm | None]
    stats: Stats
    traits: list[Trait]
    #: upgrade level (+0 to +10) of every piece the hero owns
    plus: dict[str, int] | None = None

    @property
    def worn(self) -> list[Arm]:
        return [a for a in self.slots if a is not None]


def _loadout(slots: list[Arm | None], plus: dict[str, int]) -> Loadout:
    stats = Stats()
    traits: list[Trait] = []
    for arm in slots:
        if arm is not None:
            stats = stats + upgraded_stats(arm, plus.get(arm.id, 0))
            traits += arm.traits
    return Loadout(slots, stats, traits, plus)


@dataclass
class UpgradeResult:
    arm: Arm
    success: bool
    level: int
    chance: float
    gold: int
    materials: dict[str, int]


class ArmsService:
    def __init__(self, ctx: AppContext, inventory=None) -> None:  # noqa: ANN001 - InventoryService (not needed to grant)
        self.ctx = ctx
        self.inventory = inventory

    # --- reading --------------------------------------------------------------------------------------------------
    async def loadout_in(self, tx: Tx, player_id: int) -> Loadout:
        rows = await tx.fetchall("SELECT slot, arm_id FROM arms_equipped WHERE player_id = ?", (player_id,))
        slots: list[Arm | None] = [None] * MAX_EQUIPPED
        for row in rows:
            if 1 <= row["slot"] <= MAX_EQUIPPED and row["arm_id"] in ARMS:
                slots[row["slot"] - 1] = ARMS[row["arm_id"]]
        rows = await tx.fetchall("SELECT arm_id, lvl FROM arms_upgrades WHERE player_id = ?", (player_id,))
        return _loadout(slots, {r["arm_id"]: r["lvl"] for r in rows})

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
        """War gear cannot be bought with coins: the treasury sells it for real money, and it drops in the game."""
        if arm_id not in ARMS or qty < 1:
            raise GameError("این تجهیزات در قلمرو شناخته نمی‌شود.")
        if get_arm(arm_id).boss:
            raise GameError("این تجهیزات فقط از شکست دادن باس‌ها به دست می‌آید.")
        raise GameError("تجهیزات جنگی را فقط با پول واقعی از «خزانه قلمرو» می‌توان خرید؛ با سکه نمی‌شود. تجهیزات کم‌ارزش‌تر را گاهی از شکار، سفر، صندوقچه و باس‌ها پیدا می‌کنید.")

    async def free_drop(self, tx: Tx, player_id: int, chance: float) -> Arm | None:
        """A lucky find for everybody: a common or uncommon piece (never a boss spoil)."""
        if self.ctx.rng.random() >= chance:
            return None
        pool = [a for a in ARMS.values() if not a.boss and a.rarity <= FREE_MAX_RARITY]
        size = {r: sum(1 for a in pool if a.rarity == r) for r in FREE_WEIGHT}  # each rarity gets its share, split by its pieces
        arm = self.ctx.rng.choices(pool, weights=[FREE_WEIGHT[a.rarity] / size[a.rarity] for a in pool], k=1)[0]
        await self.grant(tx, player_id, arm.id, 1)
        return arm

    # --- equipping ------------------------------------------------------------------------------------------------
    async def plus_of(self, player_id: int) -> dict[str, int]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT arm_id, lvl FROM arms_upgrades WHERE player_id = ?", (player_id,))
        return {r["arm_id"]: r["lvl"] for r in rows}

    async def upgrade(self, player: Player, arm_id: str) -> UpgradeResult:
        """Try to raise a piece by one level. The coins and materials are spent whether it works or not."""
        if arm_id not in ARMS:
            raise GameError("این تجهیزات در قلمرو شناخته نمی‌شود.")
        arm = get_arm(arm_id)
        async with self.ctx.db.transaction() as tx:
            if not await tx.scalar("SELECT qty FROM arms_owned WHERE player_id = ? AND arm_id = ?", (player.id, arm_id), 0):
                raise GameError("این تجهیزات را ندارید؛ اول از خزانه قلمرو بخرید.")
            level = int(await tx.scalar("SELECT lvl FROM arms_upgrades WHERE player_id = ? AND arm_id = ?", (player.id, arm_id), 0))
            if level >= MAX_UPGRADE:
                raise GameError(f"«{arm.name}» به بیشترین ارتقا (+{fa(MAX_UPGRADE)}) رسیده است.")
            target = level + 1
            gold, mats, chance = upgrade_gold(arm, target), upgrade_materials(target), UPGRADE_CHANCE[target - 1]
            assert self.inventory is not None
            await wallet.apply(tx, player.id, gold=-gold, reason="arm_upgrade", now=self.ctx.now())
            for item_id, qty in mats.items():
                await self.inventory.take(tx, player.id, item_id, qty)
            won = self.ctx.rng.random() < chance
            if won:
                await tx.execute(
                    "INSERT INTO arms_upgrades (player_id, arm_id, lvl) VALUES (?, ?, ?)"
                    " ON CONFLICT (player_id, arm_id) DO UPDATE SET lvl = excluded.lvl", (player.id, arm_id, target),
                )
        return UpgradeResult(arm, won, target if won else level, chance, gold, mats)

    async def ensure_out_of_fight(self, player_id: int) -> None:
        async with self.ctx.db.read() as tx:
            await self._ensure_out_of_fight(tx, player_id)

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
        if slot > slots_open(player.level):
            from ..data.growth import SLOT_LEVELS

            raise GameError(f"جایگاه {fa(slot)} از سطح {fa(SLOT_LEVELS[slot - 1])} باز می‌شود؛ شما سطح {fa(player.level)} هستید.")
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
