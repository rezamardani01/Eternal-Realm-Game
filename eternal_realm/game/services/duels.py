"""Player-versus-player duels: invitation, turn-by-turn play and a once-only payout."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import duels as repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..engine import combat
from ..engine.combat import Action, Battle, Fighter
from ..models import Player
from .characters import CharacterService
from .players import LevelUp, PlayerService

DAY = 24 * 3600


@dataclass
class Duel:
    id: int
    chat_id: int
    message_id: int | None
    challenger_id: int
    target_id: int
    status: str
    winner_id: int | None
    expires_at: int
    battle: Battle | None = None

    @classmethod
    def from_row(cls, row: Row) -> Duel:
        battle = Battle.from_dict(json.loads(row["state"])) if row["state"] else None
        return cls(
            row["id"], row["chat_id"], row["message_id"], row["challenger_id"], row["target_id"],
            row["status"], row["winner_id"], row["expires_at"], battle,
        )


@dataclass
class Payout:
    gold: int = 0
    xp: int = 0
    level_up: LevelUp | None = None


@dataclass
class DuelUpdate:
    duel: Duel
    battle: Battle
    lines: list[str]
    finished: bool = False
    #: player id -> payout, only when finished
    payouts: dict[int, Payout] = field(default_factory=dict)
    #: the duel was closed because somebody ran out of time
    timed_out: bool = False


class DuelService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, characters: CharacterService
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.characters = characters

    # --- invitation ---------------------------------------------------------------------------
    async def challenge(self, chat_id: int, challenger: Player, target: Player) -> Duel:
        b, now = self.ctx.balance, self.ctx.now()
        if challenger.id == target.id:
            raise GameError("فرمانده، با سایه‌ی خودتان که نمی‌شود دوئل کرد! 😅 روی پیام یک حریف ریپلای کنید.")
        if target.banned:
            raise GameError("این بازیکن از قلمرو تبعید شده و نمی‌شود با او کاری داشت.")
        async with self.ctx.db.transaction() as tx:
            pair = (challenger.id, target.id)
            await repo.expire_pending_for(tx, pair, now)
            if await repo.open_for(tx, pair) is not None:
                raise GameError("یکی از شما هم‌اکنون در میدان نبرد است. بگذارید آن نبرد تمام شود، بعد دوباره دعوت کنید.")
            if await repo.pair_count_since(tx, challenger.id, target.id, now - DAY) >= b.duel_pair_daily_limit:
                raise GameError("شما دو نفر امروز آن‌قدر با هم جنگیده‌اید که شمشیرها خسته شده‌اند! فردا دوباره بجنگید.")
            duel_id = await repo.create(tx, chat_id, challenger.id, target.id, now, now + b.duel_invite_seconds)
            row = await repo.get(tx, duel_id)
        assert row is not None
        return Duel.from_row(row)

    async def attach_message(self, duel_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await repo.set_message(tx, duel_id, message_id)

    async def get(self, duel_id: int) -> Duel | None:
        async with self.ctx.db.read() as tx:
            row = await repo.get(tx, duel_id)
        return Duel.from_row(row) if row else None

    async def decline(self, duel_id: int, by: Player) -> Duel:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, duel_id)
            if row is None:
                raise GameError("این دعوت‌نامه دیگر وجود ندارد.")
            if by.id not in (row["target_id"], row["challenger_id"]):
                raise GameError("این دعوت‌نامه مال شما نیست.")
            if not await repo.close_pending(tx, duel_id, "declined", now):
                raise GameError("این دعوت‌نامه دیگر معتبر نیست؛ پذیرفته، رد یا منقضی شده است.")
            row = await repo.get(tx, duel_id)
        assert row is not None
        return Duel.from_row(row)

    async def accept(self, duel_id: int, by: Player) -> DuelUpdate:
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, duel_id)
            if row is None or row["status"] != "pending":
                raise GameError("این دعوت‌نامه دیگر معتبر نیست؛ پذیرفته، رد یا منقضی شده است.")
            if by.id != row["target_id"]:
                raise GameError("فقط کسی که به دوئل فراخوانده شده می‌تواند دعوت را بپذیرد.")
            if row["expires_at"] <= now:
                raise GameError("مهلت این دعوت‌نامه تمام شده است. دوباره دعوت کنید.")
            challenger = await player_repo.get(tx, row["challenger_id"])
            target = await player_repo.get(tx, row["target_id"])
            assert challenger is not None and target is not None
            fighters = []
            for p in (challenger, target):
                stats = await self.characters.stats_in(tx, p)
                fighters.append(Fighter.for_player(p.id, p.name, p.char_class, stats))
            battle = Battle.start(fighters[0], fighters[1], b.duel_max_rounds, self.ctx.rng)
            if not await repo.start(tx, duel_id, json.dumps(battle.to_dict()), now, now + b.duel_turn_seconds):
                raise GameError("این دعوت‌نامه دیگر معتبر نیست؛ پذیرفته، رد یا منقضی شده است.")
            fresh = await repo.get(tx, duel_id)
        assert fresh is not None
        return DuelUpdate(Duel.from_row(fresh), battle, [f"⚔️ شیپور نبرد نواخته شد! چون {battle.current.name} چابک‌تر است، اول او حمله می‌کند."])

    # --- play ---------------------------------------------------------------------------------
    async def act(self, duel_id: int, by: Player, action: Action) -> DuelUpdate:
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, duel_id)
            if row is None or row["status"] != "active":
                raise GameError("این نبرد پایان یافته است.")
            duel = Duel.from_row(row)
            assert duel.battle is not None
            battle = duel.battle
            if by.id not in (duel.challenger_id, duel.target_id):
                raise GameError("شما در این نبرد حضور ندارید، فرمانده!")
            if battle.current.player_id != by.id:
                raise GameError("✋ صبر کنید فرمانده، نوبت حریف شماست!")
            if row["expires_at"] <= now:
                raise GameError("زمان شما تمام شد و ریگ‌های ساعت ریختند! نبرد به‌زودی بسته می‌شود.")
            if action is Action.SKILL and battle.current.skill_ready_in > 1:
                raise GameError(f"مهارت ویژه‌ی شما هنوز آماده نیست؛ {battle.current.skill_ready_in - 1} نوبت دیگر صبر کنید یا حمله‌ی معمولی بزنید.")
            lines = combat.act(battle, action, self.ctx.rng)
            return await self._after_turn(tx, duel, battle, lines, now, b.duel_turn_seconds)

    async def _after_turn(
        self, tx: Tx, duel: Duel, battle: Battle, lines: list[str], now: int, turn_seconds: int,
        *, timed_out: bool = False,
    ) -> DuelUpdate:
        state = json.dumps(battle.to_dict())
        if not battle.finished:
            await repo.save_state(tx, duel.id, state, now, now + turn_seconds)
            return DuelUpdate(duel, battle, lines)
        winner_pid = battle.fighters[battle.winner].player_id if battle.winner is not None else None
        if not await repo.finish(tx, duel.id, state, winner_pid, now):
            raise GameError("این نبرد پیش‌تر پایان یافته است.")
        duel.status, duel.winner_id = "finished", winner_pid
        payouts = await self._pay(tx, duel, battle, now)
        return DuelUpdate(duel, battle, lines, finished=True, payouts=payouts, timed_out=timed_out)

    async def _pay(self, tx: Tx, duel: Duel, battle: Battle, now: int) -> dict[int, Payout]:
        """Record results and pay once. ``repo.finish`` already guarantees a single caller."""
        b = self.ctx.balance
        payouts: dict[int, Payout] = {}
        day_start = now - DAY
        for index, fighter in enumerate(battle.fighters):
            pid = fighter.player_id
            assert pid is not None
            won = battle.winner == index
            lost = battle.winner is not None and not won
            if battle.winner is not None:
                await player_repo.record_result(tx, pid, won=won)
            payout = Payout()
            # the finished duel itself is already counted, hence the strict limit
            if await repo.finished_count_since(tx, pid, day_start) <= b.duel_daily_reward_cap:
                opponent = battle.fighters[1 - index].player_id
                other = await player_repo.get(tx, opponent) if opponent else None
                if won:
                    payout.gold = b.duel_win_gold + 2 * (other.level if other else 1)
                    payout.xp = b.duel_win_xp
                elif lost or battle.winner is None:
                    payout.xp = b.duel_lose_xp
            if payout.gold:
                await wallet.apply(
                    tx, pid, gold=payout.gold, reason="duel_win", now=now, ref=f"duel:{duel.id}:{pid}"
                )
            if payout.xp:
                payout.level_up = await self.players.grant_xp(tx, pid, payout.xp)
            payouts[pid] = payout
        return payouts

    # --- housekeeping -------------------------------------------------------------------------
    async def expire_stale(self) -> list[DuelUpdate | Duel]:
        """Close invitations nobody answered and duels where someone ran out of time."""
        now = self.ctx.now()
        results: list[DuelUpdate | Duel] = []
        async with self.ctx.db.transaction() as tx:
            for row in await repo.stale(tx, now):
                duel = Duel.from_row(row)
                if duel.status == "pending":
                    if await repo.close_pending(tx, duel.id, "expired", now):
                        duel.status = "expired"
                        results.append(duel)
                    continue
                assert duel.battle is not None
                battle = duel.battle
                idler = battle.current
                battle.finished, battle.winner = True, 1 - battle.actor
                lines = [f"⌛ فرمانده {idler.name} در زمان مقرر حرکتی نکرد و نبرد را واگذار کرد."]
                results.append(
                    await self._after_turn(tx, duel, battle, lines, now, 0, timed_out=True)
                )
        return results
