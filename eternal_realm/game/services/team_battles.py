"""Team battles: a lobby with seats for two teams, then turn-by-turn play, one team after the other."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import inventory as inv_repo
from ...db.repos import open_requests
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..engine import combat, team_fight
from ..engine.combat import Action, Fighter
from ..engine.team_fight import TeamBattle
from ..models import Player
from .characters import CharacterService
from .duels import Payout
from .pets import PetService
from .players import PlayerService

SEATS = 10
LOBBY_SECONDS = 300
DAY = 24 * 3600


@dataclass
class Lobby:
    id: int
    chat_id: int
    message_id: int | None
    creator_id: int
    status: str
    expires_at: int
    #: (team, seat, player), ordered by team then seat
    members: list[tuple[int, int, Player]] = field(default_factory=list)
    battle: TeamBattle | None = None

    def seat_of(self, player_id: int) -> tuple[int, int] | None:
        return next(((t, s) for t, s, p in self.members if p.id == player_id), None)

    def at(self, team: int, seat: int) -> Player | None:
        return next((p for t, s, p in self.members if (t, s) == (team, seat)), None)


@dataclass
class TeamUpdate:
    lobby: Lobby
    battle: TeamBattle
    lines: list[str]
    finished: bool = False
    #: player id -> payout, only when finished
    payouts: dict[int, Payout] = field(default_factory=dict)


class TeamBattleService:
    def __init__(self, ctx: AppContext, players: PlayerService, characters: CharacterService) -> None:
        self.ctx = ctx
        self.players = players
        self.characters = characters

    # --- loading ------------------------------------------------------------------------------
    async def _load(self, tx: Tx, battle_id: int) -> Lobby:
        row = await tx.fetchone("SELECT * FROM team_battles WHERE id = ?", (battle_id,))
        if row is None:
            raise GameError("این مبارزه‌ی تیمی دیگر وجود ندارد.")
        members = []
        for m in await tx.fetchall(
            "SELECT player_id, team, seat FROM team_battle_members WHERE battle_id = ? ORDER BY team, seat", (battle_id,)
        ):
            player = await player_repo.get(tx, m["player_id"])
            if player is not None:
                members.append((m["team"], m["seat"], player))
        battle = TeamBattle.from_dict(json.loads(row["state"])) if row["state"] else None
        return Lobby(
            row["id"], row["chat_id"], row["message_id"], row["creator_id"], row["status"], row["expires_at"],
            members, battle,
        )

    async def get(self, battle_id: int) -> Lobby | None:
        try:
            async with self.ctx.db.read() as tx:
                return await self._load(tx, battle_id)
        except GameError:
            return None

    async def attach_message(self, battle_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE team_battles SET message_id = ? WHERE id = ?", (message_id, battle_id))

    async def _ensure_free(self, tx: Tx, player_id: int, now: int) -> None:
        left = await player_repo.is_away(tx, player_id, now)
        if left is not None:
            raise player_repo.away_error(left)
        busy = await tx.fetchone(
            "SELECT b.id FROM team_battles b JOIN team_battle_members m ON m.battle_id = b.id"
            " WHERE m.player_id = ? AND b.status = 'active' LIMIT 1",
            (player_id,),
        )
        if busy is not None:
            raise GameError("شما هم‌اکنون در یک مبارزه‌ی تیمی هستید؛ اول آن را تمام کنید یا از جایگاهتان برخیزید.")

    # --- lobby --------------------------------------------------------------------------------
    async def create(self, chat_id: int, creator: Player) -> Lobby:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await open_requests.close_all(tx, creator.id, now)
            await self._ensure_free(tx, creator.id, now)
            battle_id = await tx.execute(
                "INSERT INTO team_battles (chat_id, creator_id, status, created_at, updated_at, expires_at)"
                " VALUES (?, ?, 'lobby', ?, ?, ?)",
                (chat_id, creator.id, now, now, now + LOBBY_SECONDS),
            )
            await tx.execute(
                "INSERT INTO team_battle_members (battle_id, player_id, team, seat) VALUES (?, ?, 0, 0)",
                (battle_id, creator.id),
            )
            return await self._load(tx, battle_id)

    async def sit(self, battle_id: int, player: Player, team: int, seat: int) -> tuple[Lobby, str]:
        """Take a seat (moving there if already seated elsewhere); a tap on your own seat stands you up."""
        now = self.ctx.now()
        if team not in (0, 1) or not 0 <= seat < SEATS:
            raise GameError("این جایگاه وجود ندارد.")
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT status, expires_at, creator_id FROM team_battles WHERE id = ?", (battle_id,))
            if row is None or row["status"] != "lobby" or row["expires_at"] <= now:
                raise GameError("ثبت‌نام این مبارزه بسته شده است.")
            creator_id = row["creator_id"]
            if await tx.scalar(
                "SELECT 1 FROM team_battle_bans WHERE battle_id = ? AND player_id = ?", (battle_id, player.id), 0
            ):
                raise GameError("سازنده‌ی مبارزه شما را از این مبارزه بیرون کرده است؛ نمی‌توانید جایگاهی بگیرید.")
            holder = await tx.scalar(
                "SELECT player_id FROM team_battle_members WHERE battle_id = ? AND team = ? AND seat = ?",
                (battle_id, team, seat), None,
            )
            if holder is not None and holder != player.id and player.id == creator_id:
                await tx.execute(
                    "DELETE FROM team_battle_members WHERE battle_id = ? AND player_id = ?", (battle_id, holder)
                )
                await tx.execute(
                    "INSERT OR IGNORE INTO team_battle_bans (battle_id, player_id) VALUES (?, ?)", (battle_id, holder)
                )
                gone = await player_repo.get(tx, holder)
                return await self._load(tx, battle_id), f"{gone.name if gone else 'او'} از مبارزه بیرون انداخته شد."
            if holder == player.id:
                await tx.execute(
                    "DELETE FROM team_battle_members WHERE battle_id = ? AND player_id = ?", (battle_id, player.id)
                )
                note = "از جایگاهتان برخاستید."
            elif holder is not None:
                raise GameError("این جایگاه را فرمانده‌ی دیگری گرفته است؛ جایگاه خالی را انتخاب کنید.")
            else:
                seated = await tx.scalar(
                    "SELECT 1 FROM team_battle_members WHERE battle_id = ? AND player_id = ?", (battle_id, player.id), 0
                )
                if seated:
                    await tx.execute(
                        "UPDATE team_battle_members SET team = ?, seat = ? WHERE battle_id = ? AND player_id = ?",
                        (team, seat, battle_id, player.id),
                    )
                else:
                    await open_requests.close_all(tx, player.id, now, keep_lobby=battle_id)
                    await self._ensure_free(tx, player.id, now)
                    await tx.execute(
                        "INSERT INTO team_battle_members (battle_id, player_id, team, seat) VALUES (?, ?, ?, ?)",
                        (battle_id, player.id, team, seat),
                    )
                note = "جایگاهتان را گرفتید."
            return await self._load(tx, battle_id), note

    async def cancel(self, battle_id: int, by: Player) -> Lobby:
        """The creator may call the whole thing off, in the lobby or in the middle of the fight (nothing is paid)."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            lobby = await self._load(tx, battle_id)
            if by.id != lobby.creator_id:
                raise GameError("فقط سازنده‌ی همین مبارزه می‌تواند آن را لغو کند.")
            await tx.execute(
                "UPDATE team_battles SET status = 'cancelled', updated_at = ? WHERE id = ? AND status IN ('lobby', 'active')",
                (now, battle_id),
            )
            if tx.rowcount == 0:
                raise GameError("این مبارزه پیش‌تر تمام شده است.")
            lobby.status = "cancelled"
            return lobby

    async def start(self, battle_id: int, by: Player) -> TeamUpdate:
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            lobby = await self._load(tx, battle_id)
            if by.id != lobby.creator_id:
                raise GameError("فقط سازنده‌ی همین مبارزه می‌تواند آن را شروع کند.")
            if lobby.status != "lobby" or lobby.expires_at <= now:
                raise GameError("ثبت‌نام این مبارزه بسته شده است.")
            for _, _, member in lobby.members:
                left = await player_repo.is_away(tx, member.id, now)
                if left is not None:
                    raise player_repo.away_error(left, member.name, "\nجایگاهش را خالی کنید.")
            if not any(t == 0 for t, _, _ in lobby.members) or not any(t == 1 for t, _, _ in lobby.members):
                raise GameError("هر دو تیم دست‌کم یک جنگجو لازم دارند؛ منتظر بمانید تا جایگاه‌ها پر شوند.")
            fighters, teams = [], []
            for team, _seat, p in lobby.members:
                stats = await self.characters.stats_in(tx, p)
                fighter = await self.characters.fighter_from(tx, p, stats, p.mention)
                striker = await PetService(self.ctx).striker_in(tx, p.id, stats.atk)
                if striker:
                    fighter.pet_emoji, fighter.pet_name, fighter.pet_power = striker
                fighters.append(fighter)
                teams.append(team)
            sides = [[f for f, t in zip(fighters, teams, strict=True) if t == side] for side in (0, 1)]
            ratio, strong = combat.level_field(sides)
            battle = TeamBattle.start(fighters, teams, self.ctx.rng)
            battle.power_ratio, battle.strong_team = ratio, strong
            await tx.execute(
                "UPDATE team_battles SET status = 'active', state = ?, updated_at = ?, expires_at = ?"
                " WHERE id = ? AND status = 'lobby'",
                (json.dumps(battle.to_dict()), now, now + b.duel_turn_seconds, battle_id),
            )
            if tx.rowcount == 0:
                raise GameError("این مبارزه دیگر در حال ثبت‌نام نیست.")
            lobby.status, lobby.battle = "active", battle
        first = "اول" if battle.first_team == 0 else "دوم"
        return TeamUpdate(lobby, battle, [f"⚔️ شیپور نبرد نواخته شد! قرعه به نام تیم {first} افتاد و او آغاز می‌کند."])

    # --- play ---------------------------------------------------------------------------------
    async def act(self, battle_id: int, by: Player, action: Action) -> TeamUpdate:
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            lobby = await self._load(tx, battle_id)
            battle = lobby.battle
            if lobby.status != "active" or battle is None:
                raise GameError("این نبرد پایان یافته است.")
            if lobby.seat_of(by.id) is None:
                raise GameError("شما در این نبرد حضور ندارید، فرمانده!")
            if battle.current.player_id != by.id:
                raise GameError(f"✋ صبر کنید فرمانده، نوبت {battle.current.name} است!")
            if lobby.expires_at <= now:
                raise GameError("زمان شما تمام شد و ریگ‌های ساعت ریختند! نبرد به‌زودی ادامه پیدا می‌کند.")
            if action is not Action.SURRENDER and (problem := combat.readiness_error(battle.current, action)):
                raise GameError(problem)
            if battle.actor in battle.auto:
                battle.auto.remove(battle.actor)  # back in the fight
            lines = team_fight.act(battle, action, self.ctx.rng)
            return await self._after_turn(tx, lobby, battle, lines, now, b.duel_turn_seconds)

    async def _after_turn(
        self, tx: Tx, lobby: Lobby, battle: TeamBattle, lines: list[str], now: int, turn_seconds: int
    ) -> TeamUpdate:
        while not battle.finished and battle.actor in battle.auto:  # idle heroes fight on their own
            lines += [f"⌛ {battle.current.name} در زمان مقرر حرکتی نکرد؛ سرباز او خودکار می‌جنگد."]
            lines += team_fight.act(battle, team_fight.auto_action(battle.current), self.ctx.rng)
        state = json.dumps(battle.to_dict())
        if not battle.finished:
            await tx.execute(
                "UPDATE team_battles SET state = ?, updated_at = ?, expires_at = ? WHERE id = ?",
                (state, now, now + turn_seconds, lobby.id),
            )
            return TeamUpdate(lobby, battle, lines)
        await tx.execute(
            "UPDATE team_battles SET state = ?, status = 'finished', updated_at = ? WHERE id = ? AND status = 'active'",
            (state, now, lobby.id),
        )
        if tx.rowcount == 0:
            raise GameError("این نبرد پیش‌تر پایان یافته است.")
        lobby.status = "finished"
        payouts = await self._pay(tx, lobby, battle, now)
        return TeamUpdate(lobby, battle, lines, finished=True, payouts=payouts)

    async def _pay(self, tx: Tx, lobby: Lobby, battle: TeamBattle, now: int) -> dict[int, Payout]:
        """Pay each hero once (the status flip above guarantees a single caller)."""
        from ...db.repos import season as season_repo

        b = self.ctx.balance
        levels: dict[int, list[int]] = {0: [], 1: []}
        for team, _seat, p in lobby.members:
            levels[team].append(p.level)
        payouts: dict[int, Payout] = {}
        for index, fighter in enumerate(battle.fighters):
            pid = fighter.player_id
            assert pid is not None
            team = battle.teams[index]
            won = battle.winner == team
            if battle.winner is not None:
                await player_repo.record_result(tx, pid, won=won)
            payout = Payout()
            earlier = int(await tx.scalar(
                "SELECT COUNT(*) FROM team_battle_members WHERE player_id = ? AND paid_at > ?", (pid, now - DAY), 0
            ))
            owner = int(await tx.scalar("SELECT platform_user_id FROM players WHERE id = ?", (pid,), 0)) == self.ctx.settings.owner_id
            if index not in battle.auto and (owner or earlier < b.duel_daily_reward_cap):
                foes = levels[1 - team]
                if won:
                    worth = combat.reward_factor(battle.power_ratio, battle.strong_team == team) if battle.strong_team >= 0 else 1.0
                    payout.gold = round((b.duel_win_gold + 2 * (sum(foes) // max(1, len(foes)))) * worth)
                    payout.xp = round(b.duel_win_xp * worth)
                else:
                    payout.xp = b.duel_lose_xp
            boost = await self.players.boost_factor(tx, pid)
            payout.gold, payout.xp = payout.gold * boost, payout.xp * boost
            if payout.gold:
                await wallet.apply(
                    tx, pid, gold=payout.gold, reason="duel_win", now=now, ref=f"teambattle:{lobby.id}:{pid}"
                )
            if payout.xp:
                payout.level_up = await self.players.grant_xp(tx, pid, payout.xp)
            await tx.execute(
                "UPDATE team_battle_members SET paid_at = ? WHERE battle_id = ? AND player_id = ?", (now, lobby.id, pid)
            )
            await season_repo.add_points(tx, pid, "duel_win" if won else "duel", now)
            await inv_repo.add_bond(tx, pid, 2)
            payouts[pid] = payout
        return payouts

    # --- housekeeping -------------------------------------------------------------------------
    async def expire_stale(self) -> list[TeamUpdate | Lobby]:
        """Close lobbies nobody started, and play on for a hero whose turn timer ran out."""
        b, now = self.ctx.balance, self.ctx.now()
        results: list[TeamUpdate | Lobby] = []
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT id FROM team_battles WHERE status IN ('lobby', 'active') AND expires_at <= ?", (now,)
            )
            for row in rows:
                lobby = await self._load(tx, row["id"])
                if lobby.status == "lobby":
                    await tx.execute("UPDATE team_battles SET status = 'expired', updated_at = ? WHERE id = ?", (now, lobby.id))
                    lobby.status = "expired"
                    results.append(lobby)
                    continue
                battle = lobby.battle
                assert battle is not None
                if battle.actor not in battle.auto:
                    battle.auto.append(battle.actor)
                results.append(await self._after_turn(tx, lobby, battle, [], now, b.duel_turn_seconds))
        return results
