"""Hero growth: attribute points the player spends, and the class talents he chooses."""

from __future__ import annotations

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.arms import Trait
from ..data.growth import (
    ATTR_CAP, ATTRS, RESET_GOLD_PER_LEVEL, TALENT_BY_ID, TALENT_LEVELS, attr_resist, attr_stats, points_earned,
    talent_places, talents_of,
)
from ..data.stats import Stats
from ..models import Player


class GrowthService:
    def __init__(self, ctx: AppContext, arms) -> None:  # noqa: ANN001 - ArmsService
        self.ctx = ctx
        self.arms = arms

    # --- reading ----------------------------------------------------------------------------------------------------------
    async def attrs_in(self, tx: Tx, player_id: int) -> dict[str, int]:
        rows = await tx.fetchall("SELECT attr, pts FROM hero_attrs WHERE player_id = ?", (player_id,))
        return {r["attr"]: r["pts"] for r in rows if r["attr"] in ATTRS}

    async def talents_in(self, tx: Tx, player: Player) -> list[str]:
        rows = await tx.fetchall("SELECT talent_id FROM hero_talents WHERE player_id = ?", (player.id,))
        mine = [r["talent_id"] for r in rows if r["talent_id"] in TALENT_BY_ID and TALENT_BY_ID[r["talent_id"]].class_id == player.class_id]
        return mine[: talent_places(player.level)]  # a hero who lost a level (or changed class) keeps only what fits

    async def attrs(self, player_id: int) -> dict[str, int]:
        async with self.ctx.db.read() as tx:
            return await self.attrs_in(tx, player_id)

    async def talents(self, player: Player) -> list[str]:
        async with self.ctx.db.read() as tx:
            return await self.talents_in(tx, player)

    async def free_points(self, player: Player) -> int:
        spent = sum((await self.attrs(player.id)).values())
        return max(0, points_earned(player.level) - spent)

    async def bonus_in(self, tx: Tx, player: Player) -> Stats:
        """Stat bonus of the spent attribute points and of the chosen talents."""
        total = attr_stats(await self.attrs_in(tx, player.id))
        for talent_id in await self.talents_in(tx, player):
            total = total + TALENT_BY_ID[talent_id].stats
        return total

    async def traits_in(self, tx: Tx, player: Player) -> list[Trait]:
        """Special abilities that do not come from gear: the chosen talents and the resistance of vitality."""
        traits: list[Trait] = []
        for talent_id in await self.talents_in(tx, player):
            traits += TALENT_BY_ID[talent_id].traits
        resist = attr_resist(await self.attrs_in(tx, player.id))
        if resist:
            traits.append(Trait("resist_all", resist))
        return traits

    # --- attribute points -------------------------------------------------------------------------------------------------
    async def spend(self, player: Player, attr_id: str, count: int = 1) -> dict[str, int]:
        if attr_id not in ATTRS or count < 1:
            raise GameError("این ویژگی وجود ندارد.")
        async with self.ctx.db.transaction() as tx:
            current = await self.attrs_in(tx, player.id)
            free = points_earned(player.level) - sum(current.values())
            if free <= 0:
                raise GameError("امتیاز ویژگی ندارید؛ با بالا رفتن سطح، امتیاز تازه می‌گیرید.")
            count = min(count, free, ATTR_CAP - current.get(attr_id, 0))
            if count <= 0:
                raise GameError(f"هر ویژگی بیشتر از {fa(ATTR_CAP)} امتیاز نمی‌گیرد؛ بقیه را جای دیگر بگذارید.")
            await tx.execute(
                "INSERT INTO hero_attrs (player_id, attr, pts) VALUES (?, ?, ?)"
                " ON CONFLICT (player_id, attr) DO UPDATE SET pts = pts + excluded.pts", (player.id, attr_id, count),
            )
            current[attr_id] = current.get(attr_id, 0) + count
            return current

    def reset_price(self, player: Player) -> int:
        return RESET_GOLD_PER_LEVEL * player.level

    async def reset(self, player: Player) -> int:
        """Take every point back (for coins) so the hero can be built again; returns the points given back."""
        await self.arms.ensure_out_of_fight(player.id)
        async with self.ctx.db.transaction() as tx:
            spent = sum((await self.attrs_in(tx, player.id)).values())
            if not spent:
                raise GameError("هنوز امتیازی خرج نکرده‌اید.")
            await wallet.apply(tx, player.id, gold=-self.reset_price(player), reason="attr_reset", now=self.ctx.now())
            await tx.execute("DELETE FROM hero_attrs WHERE player_id = ?", (player.id,))
            return spent

    # --- talents ----------------------------------------------------------------------------------------------------------
    async def choose(self, player: Player, talent_id: str) -> list[str]:
        talent = TALENT_BY_ID.get(talent_id)
        if talent is None or talent.class_id != player.class_id:
            raise GameError("این استعداد برای کلاس شما نیست.")
        await self.arms.ensure_out_of_fight(player.id)
        async with self.ctx.db.transaction() as tx:
            mine = await self.talents_in(tx, player)
            if talent_id in mine:
                raise GameError("این استعداد را همین حالا دارید.")
            places = talent_places(player.level)
            if len(mine) >= places:
                if places == 0:
                    raise GameError(f"استعدادها از سطح {fa(TALENT_LEVELS[0])} باز می‌شوند.")
                nxt = next((n for n in TALENT_LEVELS if n > player.level), None)
                more = f" جای تازه از سطح {fa(nxt)} باز می‌شود." if nxt else ""
                raise GameError(f"همه‌ی جای استعدادها پر است؛ اول یکی را بردارید.{more}")
            await tx.execute("INSERT INTO hero_talents (player_id, talent_id) VALUES (?, ?)", (player.id, talent_id))
            return [*mine, talent_id]

    async def drop(self, player: Player, talent_id: str) -> list[str]:
        await self.arms.ensure_out_of_fight(player.id)
        async with self.ctx.db.transaction() as tx:
            await tx.execute("DELETE FROM hero_talents WHERE player_id = ? AND talent_id = ?", (player.id, talent_id))
            return await self.talents_in(tx, player)

    def available(self, player: Player) -> list:
        return talents_of(player.class_id)
