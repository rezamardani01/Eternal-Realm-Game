"""Daily missions: made on first look each day, advanced by deeds, paid once."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import players as player_repo
from ...db.repos import season as season_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.missions import PER_DAY, get_kind, pick, reward_for
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
    #: crystals paid because this was the day's last mission
    bonus_crystal: int = 0

    @property
    def done(self) -> bool:
        return self.progress >= self.target


ALL_DONE_CRYSTALS = 2
#: days of a week with every mission done -> the week's prize: (crystals, chest); the best one reached is paid
WEEK_PRIZES: tuple[tuple[int, int, str], ...] = ((7, 6, "royal_chest"), (5, 3, "magic_chest"), (3, 1, "wooden_chest"))


def week_of(now: int) -> int:
    """Weeks start on Saturday (Tehran)."""
    return (today(now) + 5) // 7


@dataclass
class WeekView:
    days: int
    week: int
    claimed: bool
    #: (days needed, crystals, chest id) of the prize the hero has earned so far, if any
    earned: tuple[int, int, str] | None
    #: the next prize still to win
    next_prize: tuple[int, int, str] | None
    seconds_left: int


def today(now: int) -> int:
    return (now + 12600) // 86400


class MissionService:
    def __init__(self, ctx: AppContext, offers: OfferService, inventory=None) -> None:  # noqa: ANN001 - InventoryService
        self.ctx = ctx
        self.offers = offers
        self.inventory = inventory

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
                count = PER_DAY + (1 if fresh.vip_until > now else 0)
                for slot, kind in enumerate(pick(facts, player.id, day, count)):
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

    async def grant_welcome(self, player: Player) -> bool:
        """Today's «welcome back» mission, once a day. False when it was already handed out."""
        from ..data.missions import WELCOME, WELCOME_SLOT

        await self.today(player)  # the day's ordinary missions exist first
        day = today(self.ctx.now())
        async with self.ctx.db.transaction() as tx:
            have = await tx.fetchone(
                "SELECT 1 FROM daily_missions WHERE player_id = ? AND day = ? AND slot = ?", (player.id, day, WELCOME_SLOT)
            )
            if have:
                return False
            await tx.execute(
                "INSERT INTO daily_missions (player_id, day, slot, kind_id, deed, target, progress, claimed)"
                " VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
                (player.id, day, WELCOME_SLOT, WELCOME.id, WELCOME.deed, WELCOME.target),
            )
        return True

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
            if fresh.boost_until > now:  # the bought 2x boost is running
                from ..data.packs import BOOST_FACTOR

                gold *= BOOST_FACTOR
            await tx.execute(
                "UPDATE daily_missions SET claimed = 1 WHERE player_id = ? AND day = ? AND slot = ?",
                (player.id, day, slot),
            )
            await wallet.apply(
                tx, player.id, gold=gold, reason="mission", now=now, ref=f"mission:{player.id}:{day}:{slot}"
            )
            await season_repo.add_points(tx, player.id, "mission", now)
            bonus = 0
            open_left = int(await tx.scalar(
                "SELECT COUNT(*) FROM daily_missions WHERE player_id = ? AND day = ? AND claimed = 0", (player.id, day), 0
            ))
            if open_left == 0:  # every mission of the day is done: a few free crystals
                bonus = ALL_DONE_CRYSTALS
                await wallet.apply(
                    tx, player.id, crystal=bonus, reason="missions_all", now=now, ref=f"missall:{player.id}:{day}"
                )
                await tx.execute("INSERT OR IGNORE INTO mission_days (player_id, day) VALUES (?, ?)", (player.id, day))
        return MissionView(slot, kind.id, kind.emoji, kind.title, row["progress"], row["target"], gold, True, bonus)

    # --- the week ---------------------------------------------------------------------------------
    async def week(self, player: Player) -> WeekView:
        now = self.ctx.now()
        week = week_of(now)
        first = week * 7 - 5  # the Saturday this week began on
        async with self.ctx.db.read() as tx:
            days = int(await tx.scalar(
                "SELECT COUNT(*) FROM mission_days WHERE player_id = ? AND day >= ? AND day < ?", (player.id, first, first + 7), 0
            ))
            claimed = bool(await tx.scalar("SELECT 1 FROM mission_week_claims WHERE player_id = ? AND week = ?", (player.id, week), 0))
        earned = next((p for p in WEEK_PRIZES if days >= p[0]), None)
        higher = [p for p in WEEK_PRIZES if p[0] > days]
        next_prize = min(higher, key=lambda p: p[0]) if higher else None
        return WeekView(days, week, claimed, earned, next_prize, (first + 7) * 86400 - 12600 - now)

    async def claim_week(self, player: Player) -> tuple[int, int, str]:
        """Collect the prize of the week so far (once a week). Returns (days, crystals, chest id)."""
        now = self.ctx.now()
        view = await self.week(player)
        if view.claimed:
            raise GameError("جایزه‌ی این هفته را قبلاً گرفته‌اید.")
        if view.earned is None:
            raise GameError("برای جایزه‌ی هفته دست‌کم در ۳ روز باید همه‌ی مأموریت‌های روز را تمام کنید.")
        _, crystal, chest = view.earned
        async with self.ctx.db.transaction() as tx:
            await tx.execute("INSERT INTO mission_week_claims (player_id, week) VALUES (?, ?)", (player.id, view.week))
            await wallet.apply(tx, player.id, crystal=crystal, reason="mission_week", now=now, ref=f"missweek:{player.id}:{view.week}")
            await self.inventory.grant(tx, player.id, chest, 1, origin="mission_week")
        return view.days, crystal, chest
