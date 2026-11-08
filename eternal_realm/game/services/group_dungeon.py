"""The group dungeon: 3-5 heroes in one chat clear three waves of monsters and a final guardian.

The lobby is a message with join / start buttons; starting plays the whole run at once with the boss
fight engine and pays everyone by their share of the damage.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import players as player_repo
from ...db.repos import season as season_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import duration, fa
from ..engine.boss_fight import NOTABLE, Boss, Hero, run_round
from ..models import Player
from .characters import CharacterService
from .inventory import InventoryService
from .players import PlayerService

MIN_PLAYERS, MAX_PLAYERS = 3, 5
MIN_LEVEL = 5
LOBBY_SECONDS = 300
COOLDOWN = 3600
MAX_ROUNDS = 70
WAVES = (
    ("گله‌ی گابلین‌ها", "👺", 0.27, 0.78),
    ("اسکلت‌های نگهبان", "💀", 0.35, 0.86),
    ("اورک‌های خشمگین", "👹", 0.42, 0.94),
    ("نگهبان سیاه‌چال", "👑", 0.72, 1.04),
)


@dataclass
class Member:
    pid: int
    name: str
    mention: str
    level: int


@dataclass
class LobbyView:
    id: int
    chat_id: int
    message_id: int | None
    summoner_id: int
    status: str
    seconds_left: int
    members: list[Member] = field(default_factory=list)


@dataclass
class WaveReport:
    name: str
    emoji: str
    won: bool
    rounds: int
    highlights: list[str]


@dataclass
class RunPayout:
    mention: str
    name: str
    damage: int
    share: float
    gold: int
    xp: int
    chest: bool = False
    fell: bool = False
    level_up: int | None = None


@dataclass
class RunResult:
    lobby: LobbyView
    waves: list[WaveReport]
    cleared: bool
    payouts: list[RunPayout]


class GroupDungeonService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, characters: CharacterService, inventory: InventoryService
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.characters = characters
        self.inventory = inventory

    # --- the lobby ----------------------------------------------------------------------------------
    async def _members(self, tx: Tx, dungeon_id: int) -> list[Member]:
        rows = await tx.fetchall(
            "SELECT p.id, p.display_name AS name, p.platform_user_id AS uid, p.level FROM gdungeon_members m"
            " JOIN players p ON p.id = m.player_id WHERE m.dungeon_id = ? ORDER BY m.rowid",
            (dungeon_id,),
        )
        return [Member(r["id"], r["name"], f"[{r['name']}](uid:{r['uid']})", r["level"]) for r in rows]

    async def _view(self, tx: Tx, row: Row) -> LobbyView:
        left = max(0, row["expires_at"] - self.ctx.now())
        return LobbyView(
            row["id"], row["chat_id"], row["message_id"], row["summoner_id"], row["status"], left,
            await self._members(tx, row["id"]),
        )

    async def lobby(self, dungeon_id: int) -> LobbyView | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM gdungeons WHERE id = ?", (dungeon_id,))
            return await self._view(tx, row) if row else None

    async def attach_message(self, dungeon_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE gdungeons SET message_id = ? WHERE id = ?", (message_id, dungeon_id))

    async def open(self, chat_id: int, player: Player) -> LobbyView:
        now = self.ctx.now()
        if player.level < MIN_LEVEL:
            raise GameError(
                f"سیاه‌چال گروهی از سطح {fa(MIN_LEVEL)} باز است. شما سطح {fa(player.level)} هستید؛ "
                f"{fa(MIN_LEVEL - player.level)} سطح دیگر مانده."
            )
        async with self.ctx.db.transaction() as tx:
            live = await tx.fetchone(
                "SELECT id FROM gdungeons WHERE chat_id = ? AND status = 'recruiting' AND expires_at > ?", (chat_id, now)
            )
            if live is not None:
                raise GameError("در این گروه یک سیاه‌چال باز است! پیامش را بالاتر ببینید و بپیوندید.")
            last = int(await tx.scalar("SELECT MAX(created_at) FROM gdungeons WHERE chat_id = ?", (chat_id,), 0))
            if last and last + COOLDOWN > now:
                raise GameError(f"⏳ سیاه‌چال بعدی این گروه تا {duration(last + COOLDOWN - now)} دیگر آماده می‌شود.")
            dungeon_id = await tx.execute(
                "INSERT INTO gdungeons (chat_id, summoner_id, status, created_at, expires_at)"
                " VALUES (?, ?, 'recruiting', ?, ?)",
                (chat_id, player.id, now, now + LOBBY_SECONDS),
            )
            await tx.execute("INSERT INTO gdungeon_members (dungeon_id, player_id) VALUES (?, ?)", (dungeon_id, player.id))
            row = await tx.fetchone("SELECT * FROM gdungeons WHERE id = ?", (dungeon_id,))
            assert row is not None
            return await self._view(tx, row)

    async def join(self, dungeon_id: int, player: Player) -> LobbyView:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM gdungeons WHERE id = ?", (dungeon_id,))
            if row is None or row["status"] != "recruiting" or row["expires_at"] <= now:
                raise GameError("ثبت‌نام این سیاه‌چال بسته شده است.")
            if player.level < MIN_LEVEL:
                raise GameError(f"سیاه‌چال گروهی از سطح {fa(MIN_LEVEL)} باز است.")
            members = await self._members(tx, dungeon_id)
            if any(m.pid == player.id for m in members):
                raise GameError("شما همین الان در این سیاه‌چال هستید، فرمانده!")
            if len(members) >= MAX_PLAYERS:
                raise GameError(f"ظرفیت پر است! حداکثر {fa(MAX_PLAYERS)} جنگجو.")
            await tx.execute("INSERT INTO gdungeon_members (dungeon_id, player_id) VALUES (?, ?)", (dungeon_id, player.id))
            return await self._view(tx, row)

    # --- the run -------------------------------------------------------------------------------------
    async def start(self, dungeon_id: int, player: Player) -> RunResult:
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM gdungeons WHERE id = ?", (dungeon_id,))
            if row is None or row["status"] != "recruiting":
                raise GameError("این سیاه‌چال دیگر باز نیست.")
            if row["summoner_id"] != player.id:
                raise GameError("فقط گشاینده‌ی سیاه‌چال می‌تواند آن را شروع کند.")
            members = await self._members(tx, dungeon_id)
            if len(members) < MIN_PLAYERS:
                raise GameError(
                    f"برای شروع دست‌کم {fa(MIN_PLAYERS)} جنگجو لازم است؛ الان {fa(len(members))} نفر هستید."
                )
            # the status flip is the gate that makes the run (and its rewards) happen exactly once
            await tx.execute("UPDATE gdungeons SET status = 'done' WHERE id = ? AND status = 'recruiting'", (dungeon_id,))
            if tx.rowcount != 1:
                raise GameError("این سیاه‌چال همین الان شروع شد.")
            heroes: list[Hero] = []
            for m in members:
                pl = await player_repo.get(tx, m.pid)
                assert pl is not None
                st = await self.characters.stats_in(tx, pl)
                heroes.append(Hero(pl.id, m.mention, pl.class_id, st.hp, st.hp, st.atk, st.defense, st.magic, st.speed, st.luck))
            avg = max(1, round(sum(m.level for m in members) / len(members)))
            waves, cleared = self._fight(heroes, avg, rng)
            payouts = await self._pay(tx, row, members, heroes, cleared, avg, now)
            view = await self._view(tx, row)
        return RunResult(view, waves, cleared, payouts)

    @staticmethod
    def _fight(heroes: list[Hero], avg: int, rng: random.Random) -> tuple[list[WaveReport], bool]:
        reports: list[WaveReport] = []
        for name, emoji, hp_factor, atk_factor in WAVES:
            alive = [h for h in heroes if h.alive]
            if not alive:
                break
            hp = round(len(heroes) * (95 + 56 * avg) * hp_factor)
            boss = Boss(name, hp, hp, round((7.5 + 1.75 * avg) * atk_factor), round(4 + 0.8 * avg))
            notable: list[str] = []
            for _ in range(MAX_ROUNDS):
                for prio, text in run_round(boss, heroes, rng):
                    if prio >= NOTABLE:
                        notable.append(text)
                if boss.hp <= 0 or not any(h.alive for h in heroes):
                    break
            won = boss.hp <= 0
            reports.append(WaveReport(name, emoji, won, boss.round, notable[-3:]))
            if not won:
                return reports, False
            for h in heroes:  # a short rest between rooms
                if h.alive:
                    h.hp = min(h.max_hp, h.hp + round(h.max_hp * 0.25))
        return reports, True

    async def _pay(
        self, tx: Tx, row: Row, members: list[Member], heroes: list[Hero], cleared: bool, avg: int, now: int
    ) -> list[RunPayout]:
        factor = 1.0 if cleared else 0.3
        total = sum(h.damage + h.absorbed for h in heroes) or 1
        ranked = sorted(heroes, key=lambda h: -(h.damage + h.absorbed))
        pool = round((450 + 90 * avg) * factor)
        out: list[RunPayout] = []
        for index, h in enumerate(ranked):
            share = (h.damage + h.absorbed) / total
            gold = max(round(40 * factor), round(pool * share))
            xp = round((70 + 12 * avg) * (0.5 + share) * factor)
            boost = await self.players.boost_factor(tx, h.pid)
            gold, xp = gold * boost, xp * boost
            await wallet.apply(
                tx, h.pid, gold=gold, reason="gdungeon", now=now, ref=f"gdungeon:{row['id']}:{h.pid}"
            )
            up = await self.players.grant_xp(tx, h.pid, xp)
            chest = cleared and index == 0
            if chest:
                await self.inventory.grant(tx, h.pid, "magic_chest", 1)
            await season_repo.add_points(tx, h.pid, "dungeon_win" if cleared else "dungeon", now)
            name = next(m.name for m in members if m.pid == h.pid)
            out.append(RunPayout(h.name, name, h.damage, share, gold, xp, chest, not h.alive, up.new_level if up else None))
        return out
