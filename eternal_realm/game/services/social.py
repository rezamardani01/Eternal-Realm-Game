"""Friends (a list, a daily gift of energy, a look at each other's road) and the weekly goal of a group."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from .. import notify
from ..data import maze as maze_data
from ..engine import progression
from ..models import Player
from .inventory import InventoryService
from .players import PlayerService

MAX_FRIENDS = 30
GIFT_ENERGY = 20
#: the sender gets a little experience for being kind (so gifting is never a loss)
GIFT_XP = 15
GOAL_MIN, GOAL_MAX, GOAL_PER_HERO = 50, 500, 10
#: a hero must have struck this many times to share the group's prize
GOAL_MIN_HITS = 3


def day_of(now: int) -> int:
    return (now + 12600) // 86400


def week_of(now: int) -> int:
    """Weeks start on Saturday (Tehran)."""
    return (day_of(now) + 5) // 7


@dataclass
class FriendView:
    player_id: int
    name: str
    level: int
    class_label: str
    chapters: int
    best_floor: int
    gifted_today: bool


@dataclass
class Goal:
    target: int
    done: int
    mine: int
    week: int
    completed_now: bool = False
    rewarded: list[int] | None = None


class SocialService:
    def __init__(self, ctx: AppContext, players: PlayerService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory

    # --- friends ----------------------------------------------------------------------------------
    async def _count(self, tx: Tx, player_id: int) -> int:
        return int(await tx.scalar("SELECT COUNT(*) FROM friends WHERE player_id = ? AND status = 'accepted'", (player_id,), 0))

    async def request(self, sender: Player, target_id: int) -> Player:
        """Ask somebody to be a friend. Returns the person asked."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            target = await player_repo.get(tx, target_id)
            if target is None or target.banned:
                raise GameError("این قهرمان پیدا نشد.")
            if target.id == sender.id:
                raise GameError("با خودتان که نمی‌شود دوست شد! 😄")
            have = await tx.fetchone("SELECT status FROM friends WHERE player_id = ? AND friend_id = ?", (sender.id, target.id))
            if have is not None and have["status"] == "accepted":
                raise GameError(f"{target.name} همین حالا هم دوست شماست.")
            back = await tx.fetchone("SELECT status FROM friends WHERE player_id = ? AND friend_id = ?", (target.id, sender.id))
            if back is not None and back["status"] == "pending":  # they had asked first: accept at once
                await self._link(tx, sender.id, target.id, now)
                return target
            if have is not None:
                raise GameError("درخواست دوستی شما از قبل فرستاده شده؛ منتظر پاسخ بمانید.")
            if await self._count(tx, sender.id) >= MAX_FRIENDS:
                raise GameError(f"فهرست دوستان شما پر است ({fa(MAX_FRIENDS)} نفر).")
            await tx.execute("INSERT INTO friends (player_id, friend_id, status, at) VALUES (?, ?, 'pending', ?)", (sender.id, target.id, now))
            await notify.queue(
                tx, target.id, f"friendreq:{sender.id}:{now // 3600}",
                f"👥 *درخواست دوستی*\n\n{sender.name} (سطح {fa(sender.level)}) می‌خواهد دوست شما شود.", now, "friends",
            )
            return target

    async def _link(self, tx: Tx, a: int, b: int, now: int) -> None:
        for x, y in ((a, b), (b, a)):
            await tx.execute(
                "INSERT INTO friends (player_id, friend_id, status, at) VALUES (?, ?, 'accepted', ?)"
                " ON CONFLICT (player_id, friend_id) DO UPDATE SET status = 'accepted', at = excluded.at", (x, y, now),
            )

    async def respond(self, player: Player, requester_id: int, accept: bool) -> None:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT 1 FROM friends WHERE player_id = ? AND friend_id = ? AND status = 'pending'", (requester_id, player.id)
            )
            if row is None:
                raise GameError("این درخواست دیگر نیست.")
            if not accept:
                await tx.execute("DELETE FROM friends WHERE player_id = ? AND friend_id = ?", (requester_id, player.id))
                return
            if await self._count(tx, player.id) >= MAX_FRIENDS:
                raise GameError(f"فهرست دوستان شما پر است ({fa(MAX_FRIENDS)} نفر).")
            await self._link(tx, requester_id, player.id, now)
            await notify.queue(
                tx, requester_id, f"friendyes:{player.id}:{now // 3600}",
                f"🤝 *{player.name}* درخواست دوستی شما را پذیرفت!", now, "friends",
            )

    async def remove(self, player: Player, friend_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "DELETE FROM friends WHERE (player_id = ? AND friend_id = ?) OR (player_id = ? AND friend_id = ?)",
                (player.id, friend_id, friend_id, player.id),
            )

    async def pending(self, player: Player) -> list[tuple[int, str, int]]:
        """Who asked this hero for friendship: (id, name, level)."""
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.id, p.display_name AS name, p.level FROM friends f JOIN players p ON p.id = f.player_id"
                " WHERE f.friend_id = ? AND f.status = 'pending' ORDER BY f.at", (player.id,),
            )
        return [(r["id"], r["name"], r["level"]) for r in rows]

    async def friends(self, player: Player) -> list[FriendView]:
        day = day_of(self.ctx.now())
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.id, p.display_name AS name, p.level, p.class AS cls FROM friends f JOIN players p ON p.id = f.friend_id"
                " WHERE f.player_id = ? AND f.status = 'accepted' ORDER BY p.level DESC, p.id", (player.id,),
            )
            out = []
            for r in rows:
                prog = {
                    x["key"]: x["n"] for x in await tx.fetchall(
                        "SELECT key, n FROM solo_progress WHERE player_id = ? AND key IN ('maze:best', 'maze:chapters')", (r["id"],)
                    )
                }
                gifted = bool(await tx.scalar(
                    "SELECT 1 FROM friend_gifts WHERE sender_id = ? AND friend_id = ? AND day = ?", (player.id, r["id"], day), 0
                ))
                from ..data.classes import CLASSES

                out.append(FriendView(
                    r["id"], r["name"], r["level"], CLASSES[r["cls"]].name, prog.get("maze:chapters", 0), prog.get("maze:best", 0), gifted
                ))
        return out

    async def gift_energy(self, sender: Player, friend_id: int) -> int:
        """Send a friend some energy, once a day each. Returns how much the friend received."""
        now = self.ctx.now()
        day = day_of(now)
        async with self.ctx.db.transaction() as tx:
            if not await tx.scalar(
                "SELECT 1 FROM friends WHERE player_id = ? AND friend_id = ? AND status = 'accepted'", (sender.id, friend_id), 0
            ):
                raise GameError("او در فهرست دوستان شما نیست.")
            if await tx.scalar("SELECT 1 FROM friend_gifts WHERE sender_id = ? AND friend_id = ? AND day = ?", (sender.id, friend_id, day), 0):
                raise GameError("امروز برای این دوست هدیه فرستاده‌اید؛ فردا دوباره.")
            friend = await player_repo.get(tx, friend_id)
            if friend is None:
                raise GameError("این قهرمان پیدا نشد.")
            balance = self.ctx.balance
            energy, _ = progression.regen_energy(friend.energy, friend.energy_at, now, friend.level, balance)
            cap = progression.max_energy(friend.level, balance)
            gained = max(0, min(GIFT_ENERGY, cap - energy))
            await player_repo.set_energy(tx, friend_id, energy + gained, now)
            await tx.execute("INSERT INTO friend_gifts (sender_id, friend_id, day) VALUES (?, ?, ?)", (sender.id, friend_id, day))
            await self.players.grant_xp(tx, sender.id, GIFT_XP)
            await notify.queue(
                tx, friend_id, f"friendgift:{sender.id}:{day}",
                f"🎁 *{sender.name}* برایتان {fa(gained)} انرژی فرستاد! ⚡" if gained else f"🎁 *{sender.name}* برایتان انرژی فرستاد، اما نوارتان پر بود.", now, "friends",
            )
            return gained

    async def titles(self, player_id: int, limit: int = 4) -> list[str]:
        """The newest lasting badges of a hero (for the profile)."""
        from ...db.repos import titles

        async with self.ctx.db.read() as tx:
            return [r["text"] for r in await titles.of_player(tx, player_id, limit)]

    # --- the weekly goal of a group ------------------------------------------------------------------
    async def goal(self, chat_id: int, player_id: int | None = None) -> Goal | None:
        now = self.ctx.now()
        week = week_of(now)
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM group_goals WHERE chat_id = ? AND week = ?", (chat_id, week))
            if row is None:
                return None
            mine = 0
            if player_id is not None:
                mine = int(await tx.scalar(
                    "SELECT n FROM group_goal_hits WHERE chat_id = ? AND week = ? AND player_id = ?", (chat_id, week, player_id), 0
                ))
        return Goal(row["target"], row["done"], mine, week)

    async def hit(self, chat_id: int, player: Player) -> Goal:
        """One hunt in this group. When the group's weekly target is reached everybody who helped is paid."""
        now = self.ctx.now()
        week = week_of(now)
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM group_goals WHERE chat_id = ? AND week = ?", (chat_id, week))
            if row is None:
                active = int(await tx.scalar(
                    "SELECT COUNT(*) FROM group_members WHERE chat_id = ? AND last_active >= ?", (chat_id, now - 7 * 86400), 0
                ))
                target = max(GOAL_MIN, min(GOAL_MAX, GOAL_PER_HERO * active))
                await tx.execute("INSERT INTO group_goals (chat_id, week, target, done) VALUES (?, ?, ?, 0)", (chat_id, week, target))
                row = await tx.fetchone("SELECT * FROM group_goals WHERE chat_id = ? AND week = ?", (chat_id, week))
            await tx.execute(
                "INSERT INTO group_goal_hits (chat_id, week, player_id, n) VALUES (?, ?, ?, 1)"
                " ON CONFLICT (chat_id, week, player_id) DO UPDATE SET n = n + 1", (chat_id, week, player.id),
            )
            done = row["done"] + 1
            await tx.execute("UPDATE group_goals SET done = ? WHERE chat_id = ? AND week = ?", (done, chat_id, week))
            mine = int(await tx.scalar(
                "SELECT n FROM group_goal_hits WHERE chat_id = ? AND week = ? AND player_id = ?", (chat_id, week, player.id), 0
            ))
            goal = Goal(row["target"], done, mine, week)
            if done == row["target"]:  # exactly once: the hit that fills the bar
                goal.completed_now = True
                goal.rewarded = await self._pay_goal(tx, chat_id, week, now)
            return goal

    async def _pay_goal(self, tx: Tx, chat_id: int, week: int, now: int) -> list[int]:
        paid = []
        rows = await tx.fetchall(
            "SELECT player_id, n FROM group_goal_hits WHERE chat_id = ? AND week = ? AND n >= ?", (chat_id, week, GOAL_MIN_HITS)
        )
        for r in rows:
            player = await player_repo.get(tx, r["player_id"])
            if player is None:
                continue
            gold = 400 + 30 * player.level
            chest = "magic_chest" if r["n"] >= 15 else "wooden_chest"
            await wallet.apply(
                tx, player.id, gold=gold, crystal=2, reason="group_goal", now=now, ref=f"goal:{chat_id}:{week}:{player.id}"
            )
            await self.inventory.grant(tx, player.id, chest, 1, origin="group_goal")
            await notify.queue(
                tx, player.id, f"goal:{chat_id}:{week}",
                f"🎯 *هدف هفتگی گروه کامل شد!*\n\nشما {fa(r['n'])} شکار انجام دادید.\n🎁 جایزه: 🪙 {fa(gold)} سکه · 💎 ۲ کریستال · یک صندوقچه", now,
            )
            paid.append(player.id)
        return paid

    @staticmethod
    def maze_line(view: FriendView) -> str:
        if view.chapters >= len(maze_data.CHAPTERS):
            return "فاتح هزارتو 🏆"
        return f"هزارتو: طبقه‌ی {fa(view.best_floor)}" if view.best_floor else "هنوز وارد هزارتو نشده"
