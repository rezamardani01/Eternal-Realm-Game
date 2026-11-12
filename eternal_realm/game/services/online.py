"""Online duels (مبارزه آنلاین): players search from the bot's private chat and are matched with each other.

Nothing here fights by itself: a match is an ordinary duel (:mod:`duels`) between the two heroes, so turns, skills, gear,
timers, the power cap, rewards, ratings and leagues work exactly as in a group. What this module adds is the part that
groups do not have: a waiting queue, a matchmaker that widens its search while somebody waits, and the bookkeeping of the
two private messages (one per player) that show the same fight.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.repos import duels as duel_repo
from ...db.repos import players as player_repo
from ...shared.errors import GameError
from ..engine import combat
from ..engine.combat import Battle
from ..models import Player
from .duels import Duel, DuelService, DuelUpdate

#: a search ends without an opponent after this many seconds (five minutes)
QUEUE_TIMEOUT = 300
#: the player whose turn it is gets a warning when this many seconds are left
WARN_SECONDS = 30
#: after this long anybody is a fair opponent (a quiet hour must not leave two players waiting for ever)
ANYONE_AFTER = 150
#: the power ranges players are sorted into (a hero's power is the number the duel engine uses to compare fighters)
POWER_EDGES = (0, 200, 400, 700, 1100, 1700, 2600, 4000, 6000, 9000, 14000)
#: how long the longest waiter has waited -> how many neighbouring ranges are acceptable (0 = the same range only)
REACH = ((15, 0), (45, 1), (90, 2))


def bracket_of(power: int) -> int:
    """The index of the power range a hero belongs to."""
    index = 0
    for i, edge in enumerate(POWER_EDGES):
        if power >= edge:
            index = i
    return index


def bracket_label(index: int) -> str:
    """The range as text, e.g. ``۴۰۰ تا ۷۰۰`` (the last one is open-ended)."""
    from ...shared.text import fa

    low = POWER_EDGES[index]
    if index + 1 >= len(POWER_EDGES):
        return f"{fa(low)} به بالا"
    return f"{fa(low)} تا {fa(POWER_EDGES[index + 1])}"


def reach(waited: int) -> int | None:
    """How many ranges apart two players may be, given how long the one who waited longest has waited (``None`` = anyone)."""
    if waited >= ANYONE_AFTER:
        return None
    for limit, ranges in REACH:
        if waited < limit:
            return ranges
    return REACH[-1][1] + 1


@dataclass
class Waiting:
    player_id: int
    platform_user_id: int
    level: int
    rating: int
    chat_id: int
    message_id: int
    joined_at: int
    power: int = 0

    @property
    def bracket(self) -> int:
        return bracket_of(self.power)


@dataclass
class Seat:
    """One player of an online match and the private message that shows the fight to them."""

    player_id: int
    platform_user_id: int
    chat_id: int
    message_id: int | None


@dataclass
class OnlineMatch:
    duel_id: int
    seats: list[Seat]
    #: the freshly started fight (only when the match was just made)
    update: DuelUpdate | None = None

    def seat_of(self, player_id: int) -> Seat:
        return next(s for s in self.seats if s.player_id == player_id)


@dataclass
class Sweep:
    matches: list[OnlineMatch] = field(default_factory=list)
    #: searches that ended without an opponent
    expired: list[Waiting] = field(default_factory=list)


@dataclass
class JoinResult:
    #: ``None`` while the player waits
    match: OnlineMatch | None
    waiting: int
    #: the player was already searching (the search message was only refreshed)
    already: bool = False
    #: the hero's power, which decides the range he is matched in
    power: int = 0


class OnlineService:
    def __init__(self, ctx: AppContext, players, duels: DuelService) -> None:  # noqa: ANN001 - PlayerService
        self.ctx = ctx
        self.players = players
        self.duels = duels
        #: one matchmaker at a time: the queue is tiny, a lock is the simplest way to rule out double matches
        self._lock = asyncio.Lock()

    # --- the queue ------------------------------------------------------------------------------------------------
    async def _rows(self, tx) -> list[Waiting]:  # noqa: ANN001 - Tx
        rows = await tx.fetchall(
            "SELECT q.player_id, p.platform_user_id, q.level, q.rating, q.chat_id, q.message_id, q.joined_at, q.power"
            " FROM online_queue q JOIN players p ON p.id = q.player_id ORDER BY q.joined_at, q.player_id"
        )
        return [Waiting(r["player_id"], r["platform_user_id"], r["level"], r["rating"], r["chat_id"], r["message_id"], r["joined_at"], r["power"]) for r in rows]

    async def waiting(self) -> int:
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT COUNT(*) FROM online_queue", (), 0))

    async def searching(self, player_id: int) -> Waiting | None:
        async with self.ctx.db.read() as tx:
            return next((w for w in await self._rows(tx) if w.player_id == player_id), None)

    async def match_of_player(self, player_id: int) -> OnlineMatch | None:
        """The online fight the player is in right now, if any."""
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone(
                "SELECT m.duel_id FROM online_matches m JOIN duels d ON d.id = m.duel_id"
                " WHERE d.status = 'active' AND (m.a_player = ? OR m.b_player = ?) LIMIT 1", (player_id, player_id),
            )
        return await self.match_of(int(row["duel_id"])) if row else None

    async def match_of(self, duel_id: int) -> OnlineMatch | None:
        """The two seats of an online duel; ``None`` for a duel that was not made here (a group duel)."""
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM online_matches WHERE duel_id = ?", (duel_id,))
            if row is None:
                return None
            ids = (row["a_player"], row["b_player"])
            uids = {r["id"]: r["platform_user_id"] for r in await tx.fetchall(
                "SELECT id, platform_user_id FROM players WHERE id IN (?, ?)", ids)}
        return OnlineMatch(duel_id, [
            Seat(row["a_player"], uids[row["a_player"]], row["a_chat"], row["a_msg"]),
            Seat(row["b_player"], uids[row["b_player"]], row["b_chat"], row["b_msg"]),
        ])

    async def set_messages(self, duel_id: int, messages: dict[int, int | None]) -> None:
        """Remember the message that shows the fight to each player (by player id)."""
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT a_player, b_player FROM online_matches WHERE duel_id = ?", (duel_id,))
            if row is None:
                return
            if row["a_player"] in messages:
                await tx.execute("UPDATE online_matches SET a_msg = ? WHERE duel_id = ?", (messages[row["a_player"]], duel_id))
            if row["b_player"] in messages:
                await tx.execute("UPDATE online_matches SET b_msg = ? WHERE duel_id = ?", (messages[row["b_player"]], duel_id))

    async def record(self, player_id: int) -> tuple[int, int]:
        """``(online fights, online wins)`` of a player, counting only finished online duels."""
        async with self.ctx.db.read() as tx:
            played = await tx.scalar(
                "SELECT COUNT(*) FROM online_matches m JOIN duels d ON d.id = m.duel_id"
                " WHERE d.status = 'finished' AND (m.a_player = ? OR m.b_player = ?)", (player_id, player_id), 0,
            )
            won = await tx.scalar(
                "SELECT COUNT(*) FROM online_matches m JOIN duels d ON d.id = m.duel_id"
                " WHERE d.status = 'finished' AND d.winner_id = ?", (player_id,), 0,
            )
        return int(played), int(won)

    # --- joining and leaving --------------------------------------------------------------------------------------
    async def join(self, player: Player, chat_id: int, message_id: int) -> JoinResult:
        """Start (or refresh) a search. When a fitting opponent already waits the match is made at once."""
        now = self.ctx.now()
        async with self._lock:
            async with self.ctx.db.transaction() as tx:
                fresh = await player_repo.get(tx, player.id)
                if fresh is None or fresh.banned:
                    raise GameError("این قهرمان نمی‌تواند در مبارزه‌ی آنلاین شرکت کند.")
                left = await player_repo.is_away(tx, player.id, now)
                if left is not None:
                    raise player_repo.away_error(left)
                if await duel_repo.open_for(tx, (player.id, player.id)) is not None:
                    raise GameError("هم‌اکنون در یک نبرد هستید؛ اول آن را تمام کنید.")
                rating = int(await tx.scalar("SELECT rating FROM players WHERE id = ?", (player.id,), 1000))
                power = round(combat.power_of(await self.duels._fighter(tx, fresh)))
                already = await tx.scalar("SELECT 1 FROM online_queue WHERE player_id = ?", (player.id,), 0)
                if already:
                    await tx.execute(
                        "UPDATE online_queue SET chat_id = ?, message_id = ?, level = ?, rating = ?, power = ? WHERE player_id = ?",
                        (chat_id, message_id, fresh.level, rating, power, player.id),
                    )
                else:
                    await tx.execute(
                        "INSERT INTO online_queue (player_id, level, rating, chat_id, message_id, joined_at, power)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)", (player.id, fresh.level, rating, chat_id, message_id, now, power),
                    )
            if not already:
                try:
                    made = await self._match_for(player.id, now)
                except _Race:
                    made = None
                if made is not None:
                    return JoinResult(made, 0)
        return JoinResult(None, await self.waiting(), already=bool(already), power=power)

    async def leave(self, player_id: int) -> bool:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("DELETE FROM online_queue WHERE player_id = ?", (player_id,))
            return tx.rowcount == 1

    # --- the matchmaker -------------------------------------------------------------------------------------------
    async def _match_for(self, player_id: int, now: int) -> OnlineMatch | None:
        """Try to pair one waiting player with the best partner (the closest in power, then in rating)."""
        async with self.ctx.db.read() as tx:
            rows = await self._rows(tx)
        mine = next((w for w in rows if w.player_id == player_id), None)
        if mine is None:
            return None
        candidates = []
        for other in rows:
            if other.player_id == player_id:
                continue
            gap = reach(now - min(mine.joined_at, other.joined_at))
            if gap is not None and abs(other.bracket - mine.bracket) > gap:
                continue
            candidates.append((abs(other.bracket - mine.bracket), abs(other.power - mine.power), other.joined_at, other))
        for *_, other in sorted(candidates, key=lambda c: c[:3]):
            first, second = (mine, other) if mine.joined_at <= other.joined_at else (other, mine)
            made = await self._make_match(first, second)
            if made is not None:
                return made
        return None

    async def _make_match(self, first: Waiting, second: Waiting) -> OnlineMatch | None:
        """Take both players out of the queue (one winner of the race only) and start their duel."""
        async with self.ctx.db.transaction() as tx:
            gone = 0
            for w in (first, second):
                await tx.execute("DELETE FROM online_queue WHERE player_id = ?", (w.player_id,))
                gone += tx.rowcount
            if gone != 2:
                raise _Race  # somebody left or was matched meanwhile: the transaction is undone, nothing changed
        a = await self.players.get(first.player_id)
        b = await self.players.get(second.player_id)
        if a is None or b is None:
            return None
        try:
            duel: Duel = await self.duels.challenge(first.chat_id, a, b)
            update = await self.duels.accept(duel.id, b)
        except GameError:
            await self._requeue((first, second))  # they cannot fight each other now (a daily limit, a busy hero): keep searching
            return None
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO online_matches (duel_id, a_player, a_chat, a_msg, b_player, b_chat, b_msg, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (duel.id, first.player_id, first.chat_id, first.message_id, second.player_id, second.chat_id, second.message_id, self.ctx.now()),
            )
        return OnlineMatch(
            duel.id,
            [Seat(first.player_id, first.platform_user_id, first.chat_id, first.message_id),
             Seat(second.player_id, second.platform_user_id, second.chat_id, second.message_id)],
            update,
        )

    async def _requeue(self, waiters: tuple[Waiting, ...]) -> None:
        async with self.ctx.db.transaction() as tx:
            for w in waiters:
                await tx.execute(
                    "INSERT OR IGNORE INTO online_queue (player_id, level, rating, chat_id, message_id, joined_at, power)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)", (w.player_id, w.level, w.rating, w.chat_id, w.message_id, w.joined_at, w.power),
                )

    async def sweep(self) -> Sweep:
        """The matchmaker's heartbeat: pair everybody who fits now (the band widens with the wait) and drop old searches."""
        now = self.ctx.now()
        out = Sweep()
        async with self._lock:
            async with self.ctx.db.read() as tx:
                rows = await self._rows(tx)
            for w in rows:
                if now - w.joined_at >= QUEUE_TIMEOUT:
                    if await self.leave(w.player_id):
                        out.expired.append(w)
                    continue
                try:
                    made = await self._match_for(w.player_id, now)
                except _Race:
                    continue
                if made is not None:
                    out.matches.append(made)
        return out


    async def due_warnings(self) -> list[tuple[OnlineMatch, int, int]]:
        """Turns that are about to run out and have not been warned yet: ``(match, player who must move, seconds left)``."""
        now = self.ctx.now()
        found: list[tuple[int, int, int]] = []
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT m.duel_id, m.warned_for, d.expires_at, d.state FROM online_matches m JOIN duels d ON d.id = m.duel_id"
                " WHERE d.status = 'active' AND d.expires_at - ? <= ? AND d.expires_at > ?", (now, WARN_SECONDS, now),
            )
            for row in rows:
                if row["warned_for"] == row["expires_at"] or not row["state"]:
                    continue
                await tx.execute("UPDATE online_matches SET warned_for = ? WHERE duel_id = ?", (row["expires_at"], row["duel_id"]))
                battle = Battle.from_dict(json.loads(row["state"]))
                found.append((row["duel_id"], int(battle.current.player_id or 0), row["expires_at"] - now))
        out = []
        for duel_id, actor, left in found:
            match = await self.match_of(duel_id)
            if match is not None:
                out.append((match, actor, left))
        return out


class _Race(Exception):
    """Two matchmaking steps wanted the same player; the loser simply tries again at the next heartbeat."""
