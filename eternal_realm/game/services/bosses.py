"""Group bosses: summon, hit together, share the rewards by damage."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import bosses as repo
from ...db.repos import inventory as inv_repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError, NotRegistered
from ...shared.text import duration, fa
from ..data.bosses import BOSSES, BossType, boss_for_level
from ..models import Player
from .characters import CharacterService
from .inventory import InventoryService
from .players import PlayerService


@dataclass
class Payout:
    name: str
    damage: int
    share: float
    gold: int
    xp: int
    chest: str | None = None
    level_up: int | None = None


@dataclass
class BossView:
    id: int
    chat_id: int
    message_id: int | None
    type: BossType
    level: int
    hp: int
    max_hp: int
    status: str
    expires_at: int
    now: int
    top: list[tuple[str, int, int]] = field(default_factory=list)
    participants: int = 0
    payouts: list[Payout] = field(default_factory=list)

    @property
    def seconds_left(self) -> int:
        return max(0, self.expires_at - self.now)


@dataclass
class HitResult:
    view: BossView
    damage: int
    crit: bool
    heavy: bool
    finished: bool


class BossService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, inventory: InventoryService, characters: CharacterService
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory
        self.characters = characters

    # --- reading ------------------------------------------------------------------------------
    async def _view(self, tx: Tx, row: Row, payouts: list[Payout] | None = None) -> BossView:
        hitters = await repo.hitters(tx, row["id"])
        boss_type = next(b for b in BOSSES if b.id == row["boss_type"])
        return BossView(
            row["id"], row["chat_id"], row["message_id"], boss_type, row["level"], row["hp"], row["max_hp"],
            row["status"], row["expires_at"], self.ctx.now(),
            top=[(h["name"], h["damage"], h["hits"]) for h in hitters[:5]],
            participants=len(hitters), payouts=payouts or [],
        )

    async def active(self, chat_id: int) -> BossView | None:
        async with self.ctx.db.read() as tx:
            row = await repo.active_in_chat(tx, chat_id)
            if row is None or row["expires_at"] <= self.ctx.now():
                return None
            return await self._view(tx, row)

    async def attach_message(self, boss_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await repo.set_message(tx, boss_id, message_id)

    # --- summoning ----------------------------------------------------------------------------
    async def summon(self, player: Player, chat_id: int) -> BossView:
        b, now = self.ctx.balance, self.ctx.now()
        if player.level < b.boss_min_level:
            raise GameError(
                f"🐉 احضار باس از سطح {fa(b.boss_min_level)} ممکن است. شما سطح {fa(player.level)} هستید؛ "
                "کمی ماجراجویی کنید و برگردید!"
            )
        async with self.ctx.db.transaction() as tx:
            current = await repo.active_in_chat(tx, chat_id)
            if current is not None and current["expires_at"] > now:
                raise GameError("🐉 در این گروه یک باس زنده است! پیامش را بالاتر ببینید یا «باس» را دوباره بنویسید.")
            if current is not None:
                await self._settle(tx, current, "expired", now)
            last = await repo.last_created(tx, chat_id)
            wait = last + b.boss_cooldown_seconds - now if last else 0
            if wait > 0:
                raise GameError(f"⏳ باس بعدی این گروه تا {duration(wait)} دیگر آماده می‌شود. تا آن موقع قدرت جمع کنید!")
            await wallet.apply(tx, player.id, gold=-b.boss_summon_gold, reason="boss_summon", now=now)
            kind = boss_for_level(player.level)
            boss_id = await repo.create(
                tx, chat_id, kind.id, player.level, kind.max_hp(player.level), player.id, now,
                now + b.boss_duration_seconds,
            )
            row = await repo.get(tx, boss_id)
            assert row is not None
            return await self._view(tx, row)

    # --- hitting ------------------------------------------------------------------------------
    async def hit(self, boss_id: int, player: Player, heavy: bool = False) -> HitResult:
        b, now, rng = self.ctx.balance, self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, boss_id)
            if row is None or row["status"] != "active":
                raise GameError("🐉 این باس دیگر در میدان نیست.")
            if row["expires_at"] <= now:
                raise GameError("⌛ زمان نبرد با این باس تمام شد.")
            key = f"boss:{boss_id}:{'h' if heavy else 'n'}"
            until = await inv_repo.cooldown_until(tx, player.id, key)
            if until > now:
                raise GameError(f"⏳ دست‌هایتان خسته است! {duration(until - now)} دیگر دوباره ضربه بزنید.")
            await self.players.spend_energy(tx, player.id, b.boss_heavy_energy if heavy else b.boss_hit_energy)

            fresh = await player_repo.get(tx, player.id)
            if fresh is None:
                raise NotRegistered
            stats = await self.characters.stats_in(tx, fresh)
            offense = max(stats.atk, stats.magic * 0.8) * rng.uniform(0.9, 1.1)
            crit = rng.random() < min(0.5, 0.05 + stats.luck * 0.003 + fresh.char_class.crit_bonus)
            raw = offense * (1.5 if crit else 1.0) * (2.2 if heavy else 1.0) - BossType.defense(row["level"]) * 0.5
            amount = min(max(1, round(raw)), row["hp"])
            if not await repo.damage(tx, boss_id, amount):
                raise GameError("🐉 این باس همین الان افتاد!")
            await repo.add_hit(tx, boss_id, player.id, amount)
            await inv_repo.set_cooldown(
                tx, player.id, key, now + (b.boss_heavy_cooldown if heavy else b.boss_hit_cooldown)
            )
            fresh_row = await repo.get(tx, boss_id)
            assert fresh_row is not None
            finished = fresh_row["hp"] <= 0
            payouts = await self._settle(tx, fresh_row, "defeated", now) if finished else None
            if finished:
                fresh_row = await repo.get(tx, boss_id)
                assert fresh_row is not None
            view = await self._view(tx, fresh_row, payouts)
            return HitResult(view, amount, crit, heavy, finished)

    # --- ending -------------------------------------------------------------------------------
    async def _settle(self, tx: Tx, row: Row, status: str, now: int) -> list[Payout]:
        """Close the boss (once) and pay everyone who hit it. ``expired`` pays a small consolation."""
        if not await repo.close(tx, row["id"], status, now):
            return []
        factor = 1.0 if status == "defeated" else 0.25
        hitters = await repo.hitters(tx, row["id"])
        total = sum(h["damage"] for h in hitters) or 1
        pool = round((500 + 100 * row["level"]) * factor)
        payouts: list[Payout] = []
        for index, hitter in enumerate(hitters):
            pid, share = hitter["player_id"], hitter["damage"] / total
            gold = max(round(40 * factor), round(pool * share))
            xp = round((60 + 10 * row["level"]) * (0.5 + share) * factor)
            await wallet.apply(
                tx, pid, gold=gold, reason="boss_reward", now=now, ref=f"boss:{row['id']}:{pid}"
            )
            level_up = await self.players.grant_xp(tx, pid, xp)
            chest = None
            if status == "defeated":
                chest = "magic_chest" if index == 0 else "wooden_chest" if share >= 0.10 else None
                if chest:
                    await self.inventory.grant(tx, pid, chest, 1)
            payouts.append(
                Payout(hitter["name"], hitter["damage"], share, gold, xp, chest, level_up.new_level if level_up else None)
            )
        return payouts

    async def expire_stale(self) -> list[BossView]:
        """Bosses nobody finished in time flee; their fighters get a small consolation."""
        now, results = self.ctx.now(), []
        async with self.ctx.db.transaction() as tx:
            for row in await repo.stale(tx, now):
                payouts = await self._settle(tx, row, "expired", now)
                fresh = await repo.get(tx, row["id"])
                assert fresh is not None
                results.append(await self._view(tx, fresh, payouts))
        return results
