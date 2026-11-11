"""Realm-wide events (see ``data/raids.py``): announce, collect the heroes who join, play it all out, pay everybody."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from .. import notify
from ..data import raids as data
from ..data import solo as foes
from ..engine import combat
from ..engine.combat import Battle
from ..models import Player
from .inventory import InventoryService
from .players import PlayerService
from .solo import SoloService

MAX_ROUNDS = 25


@dataclass
class RaidView:
    id: int
    kind: data.GlobalKind
    status: str
    starts_at: int
    now: int
    count: int
    #: names of the heroes who joined, first come first (at most ``names_limit``)
    names: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @property
    def seconds_left(self) -> int:
        return max(0, self.starts_at - self.now)


@dataclass
class RaidEvent:
    #: finished | cancelled
    what: str
    view: RaidView


@dataclass
class Outcome:
    player: Player
    #: share of the monster taken off (raid), points (cup)
    removed: float = 0.0
    won: bool = False
    score: int = 0
    gold: int = 0
    xp: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)
    rank: int = 0
    note: str = ""


class RaidService:
    def __init__(self, ctx: AppContext, players: PlayerService, solo: SoloService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.solo = solo
        self.inventory = inventory

    # --- reading --------------------------------------------------------------------------------
    async def _view(self, tx: Tx, row, names_limit: int = 30) -> RaidView:  # noqa: ANN001
        names = [
            r["name"] for r in await tx.fetchall(
                "SELECT p.display_name AS name FROM raid_players r JOIN players p ON p.id = r.player_id"
                " WHERE r.raid_id = ? ORDER BY r.joined_at, r.player_id LIMIT ?", (row["id"], names_limit),
            )
        ]
        count = int(await tx.scalar("SELECT COUNT(*) FROM raid_players WHERE raid_id = ?", (row["id"],), 0))
        return RaidView(
            row["id"], data.get_kind(row["kind"]), row["status"], row["starts_at"], self.ctx.now(), count, names,
            json.loads(row["summary"] or "{}"),
        )

    async def get(self, raid_id: int) -> RaidView | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM raids WHERE id = ?", (raid_id,))
            return await self._view(tx, row) if row else None

    async def current(self) -> RaidView | None:
        """The event that is still gathering heroes."""
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM raids WHERE status = 'lobby' ORDER BY id DESC LIMIT 1")
            return await self._view(tx, row) if row else None

    async def joined(self, raid_id: int, player_id: int) -> bool:
        async with self.ctx.db.read() as tx:
            return bool(await tx.scalar("SELECT 1 FROM raid_players WHERE raid_id = ? AND player_id = ?", (raid_id, player_id), 0))

    # --- the automatic mode (the owner switches it on) --------------------------------------------------------
    async def auto_enabled(self) -> bool:
        async with self.ctx.db.read() as tx:
            return (await tx.scalar("SELECT value FROM app_settings WHERE key = 'auto_raids'", (), "0")) == "1"

    async def set_auto(self, enabled: bool) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO app_settings (key, value) VALUES ('auto_raids', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                ("1" if enabled else "0",),
            )

    async def auto_due(self) -> str | None:
        """The kind to announce now when the automatic mode is on and the last event is long enough ago, else ``None``."""
        if not await self.auto_enabled():
            return None
        now = self.ctx.now()
        hour = ((now + 12600) % 86400) // 3600
        if not data.AUTO_HOURS[0] <= hour < data.AUTO_HOURS[1]:
            return None
        async with self.ctx.db.read() as tx:
            if await tx.scalar("SELECT 1 FROM raids WHERE status = 'lobby'", (), 0):
                return None
            last = int(await tx.scalar("SELECT COALESCE(MAX(created_at), 0) FROM raids", (), 0))
        if now - last < data.AUTO_GAP_HOURS * 3600:
            return None
        return self.ctx.rng.choice(data.KINDS).id

    # --- starting and joining -------------------------------------------------------------------
    async def create(self, kind_id: str, minutes: int = data.LOBBY_MINUTES) -> RaidView:
        try:
            kind = data.get_kind(kind_id)
        except KeyError:
            raise GameError("چنین رویداد سراسری‌ای نداریم.") from None
        if not 1 <= minutes <= data.MAX_LOBBY_MINUTES:
            raise GameError(f"زمان انتظار باید بین ۱ تا {fa(data.MAX_LOBBY_MINUTES)} دقیقه باشد.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            if await tx.scalar("SELECT 1 FROM raids WHERE status = 'lobby'", (), 0):
                raise GameError("یک رویداد سراسری در حال جمع‌کردن بازیکن است؛ صبر کنید تمام شود.")
            raid_id = await tx.execute(
                "INSERT INTO raids (kind, status, created_at, starts_at) VALUES (?, 'lobby', ?, ?)",
                (kind.id, now, now + minutes * 60),
            )
            row = await tx.fetchone("SELECT * FROM raids WHERE id = ?", (raid_id,))
            return await self._view(tx, row)

    async def join(self, player: Player, raid_id: int) -> tuple[RaidView, bool]:
        """Add a hero. Returns the event and whether the hero is new in it."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM raids WHERE id = ?", (raid_id,))
            if row is None:
                raise GameError("این رویداد پیدا نشد.")
            if row["status"] != "lobby" or row["starts_at"] <= now:
                raise GameError("ثبت‌نام این رویداد تمام شده است؛ منتظر رویداد بعدی باشید.")
            fresh = not await tx.scalar("SELECT 1 FROM raid_players WHERE raid_id = ? AND player_id = ?", (raid_id, player.id), 0)
            if fresh:
                await tx.execute("INSERT INTO raid_players (raid_id, player_id, joined_at) VALUES (?, ?, ?)", (raid_id, player.id, now))
            return await self._view(tx, row), fresh

    # --- the messages that follow the countdown ----------------------------------------------------
    async def add_post(self, raid_id: int, chat_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "INSERT OR REPLACE INTO raid_posts (raid_id, chat_id, message_id) VALUES (?, ?, ?)", (raid_id, chat_id, message_id)
            )

    async def posts(self, raid_id: int) -> list[tuple[int, int]]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT chat_id, message_id FROM raid_posts WHERE raid_id = ?", (raid_id,))
        return [(r["chat_id"], r["message_id"]) for r in rows]

    async def set_dm(self, raid_id: int, player_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE raid_players SET dm_message = ? WHERE raid_id = ? AND player_id = ?", (message_id, raid_id, player_id))

    async def dms(self, raid_id: int) -> list[tuple[int, int]]:
        """(the hero's private chat id, the message that shows the countdown) of everybody who has one."""
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.platform_user_id AS uid, r.dm_message AS msg FROM raid_players r JOIN players p ON p.id = r.player_id"
                " WHERE r.raid_id = ? AND r.dm_message > 0", (raid_id,),
            )
        return [(int(r["uid"]), int(r["msg"])) for r in rows]

    async def target_groups(self) -> list[int]:
        """Every group the bot is playing in."""
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT chat_id FROM groups WHERE enabled = 1 AND last_seen >= ?", (self.ctx.now() - 60 * 86400,))
        return [int(r["chat_id"]) for r in rows]

    # --- the countdown ends ---------------------------------------------------------------------------
    async def tick(self) -> list[RaidEvent]:
        now = self.ctx.now()
        events: list[RaidEvent] = []
        async with self.ctx.db.transaction() as tx:
            due = await tx.fetchall("SELECT * FROM raids WHERE status = 'lobby' AND starts_at <= ?", (now,))
            for row in due:
                count = int(await tx.scalar("SELECT COUNT(*) FROM raid_players WHERE raid_id = ?", (row["id"],), 0))
                if count < data.MIN_PLAYERS:
                    await tx.execute("UPDATE raids SET status = 'cancelled', ended_at = ? WHERE id = ?", (now, row["id"]))
                    for r in await tx.fetchall("SELECT player_id FROM raid_players WHERE raid_id = ?", (row["id"],)):
                        await notify.queue(
                            tx, r["player_id"], f"raid:{row['id']}",
                            "🌫️ *رویداد سراسری برگزار نشد*\n\nشرکت‌کننده‌ی کافی نبود. دفعه‌ی بعد دوستانتان را هم خبر کنید!", now,
                        )
                    fresh = await tx.fetchone("SELECT * FROM raids WHERE id = ?", (row["id"],))
                    events.append(RaidEvent("cancelled", await self._view(tx, fresh)))
                    continue
                summary = await self._play(tx, row, now)
                await tx.execute(
                    "UPDATE raids SET status = 'done', ended_at = ?, summary = ? WHERE id = ?",
                    (now, json.dumps(summary, ensure_ascii=False), row["id"]),
                )
                fresh = await tx.fetchone("SELECT * FROM raids WHERE id = ?", (row["id"],))
                events.append(RaidEvent("finished", await self._view(tx, fresh)))
        return events

    async def _fight(self, tx: Tx, player: Player, kind: data.GlobalKind) -> tuple[float, bool, float]:
        """One automatic fight of a hero against their own copy of the monster: (share taken off, won, health kept)."""
        hero = await self.solo._hero(tx, player)
        foe = foes.get_foe(kind.foe).fighter(max(1, player.level), kind.mult)
        battle = Battle.start(hero, foe, MAX_ROUNDS, self.ctx.rng)
        for _ in range(MAX_ROUNDS * 4):
            if battle.finished:
                break
            combat.act(battle, combat.auto_action(battle.current), self.ctx.rng)
        removed = 1 - max(0, foe.hp) / max(1, foe.max_hp)
        won = battle.winner == 0
        return removed, won, max(0, hero.hp) / max(1, hero.max_hp)

    async def _play(self, tx: Tx, row, now: int) -> dict:  # noqa: ANN001
        kind = data.get_kind(row["kind"])
        pids = [r["player_id"] for r in await tx.fetchall(
            "SELECT player_id FROM raid_players WHERE raid_id = ? ORDER BY joined_at, player_id", (row["id"],)
        )]
        outcomes: list[Outcome] = []
        for pid in pids:
            player = await player_repo.get(tx, pid)
            if player is not None and not player.banned:
                outcomes.append(Outcome(player))
        if kind.mode == "lottery":
            summary = self._draw(outcomes)
        else:
            for o in outcomes:
                removed, won, kept = await self._fight(tx, o.player, kind)
                o.removed, o.won = removed, won
                o.score = round(100 * removed + (60 if won else 0) + (40 * kept if won else 0))
            summary = self._raid(outcomes, kind) if kind.mode == "raid" else self._cup(outcomes)
        for o in outcomes:
            await self._pay(tx, row["id"], o, now)
        summary.update(
            kind=kind.id, count=len(outcomes),
            top=[{"name": o.player.name, "score": o.score, "rank": o.rank, "crystal": o.crystal, "gold": o.gold}
                 for o in sorted(outcomes, key=lambda o: o.rank or 10**9)[:5]],
        )
        for o in outcomes:
            await notify.queue(tx, o.player.id, f"raid:{row['id']}", self._text(kind, o, summary), now)
            await tx.execute(
                "UPDATE raid_players SET score = ?, gold = ?, xp = ?, crystal = ?, rank = ? WHERE raid_id = ? AND player_id = ?",
                (o.score, o.gold, o.xp, o.crystal, o.rank, row["id"], o.player.id),
            )
        return summary

    # --- how each kind of event is decided ------------------------------------------------------------
    def _raid(self, outcomes: list[Outcome], kind: data.GlobalKind) -> dict:
        total = sum(o.removed for o in outcomes)
        need = data.RAID_WIN_SHARE * len(outcomes)
        victory = total >= need
        ranked = sorted(outcomes, key=lambda o: (-o.score, o.player.id))
        for rank, o in enumerate(ranked, 1):
            o.rank = rank
        for o in outcomes:
            level = o.player.level
            share = 0.4 + o.removed
            o.gold = round(data.base_gold(level) * share * (2 if victory else 1))
            o.xp = round(data.base_xp(level) * share * (2 if victory else 1))
            if victory:
                o.crystal += data.WIN_CRYSTALS
                o.items[data.WIN_CHEST] = o.items.get(data.WIN_CHEST, 0) + 1
        for (crystal, chest), o in zip(data.PODIUM, ranked):
            o.crystal += crystal
            o.items[chest] = o.items.get(chest, 0) + 1
        return {"victory": victory, "removed": round(total, 2), "need": round(need, 2)}

    def _cup(self, outcomes: list[Outcome]) -> dict:
        ranked = sorted(outcomes, key=lambda o: (-o.score, o.player.id))
        for rank, o in enumerate(ranked, 1):
            o.rank = rank
            level = o.player.level
            o.gold = round(data.base_gold(level) * (0.5 + o.removed))
            o.xp = round(data.base_xp(level) * (0.5 + o.removed))
            if rank <= len(data.CUP_PRIZES):
                o.crystal += data.CUP_PRIZES[rank - 1]
            if rank <= len(data.PODIUM):
                o.items[data.PODIUM[rank - 1][1]] = 1
        return {"victory": True}

    def _draw(self, outcomes: list[Outcome]) -> dict:
        pool = list(outcomes)
        self.ctx.rng.shuffle(pool)
        jackpot_gold, jackpot_crystal, jackpot_chest = data.LOTTERY_JACKPOT
        medium_n, medium_gold, medium_crystal, medium_chest = data.LOTTERY_MEDIUM
        for index, o in enumerate(pool):
            if index == 0:
                o.rank, o.gold, o.crystal, o.items = 1, jackpot_gold + 400 * len(pool), jackpot_crystal, {jackpot_chest: 1}
            elif index <= medium_n:
                o.rank, o.gold, o.crystal, o.items = 2, medium_gold, medium_crystal, {medium_chest: 1}
            else:
                consolation_gold, consolation_crystal, consolation_chest = data.LOTTERY_CONSOLATION
                o.rank, o.gold, o.crystal, o.items = 3, consolation_gold, consolation_crystal, {consolation_chest: 1}
            o.xp = data.base_xp(o.player.level) // 2
        return {"victory": True, "jackpot": pool[0].player.name if pool else ""}

    async def _pay(self, tx: Tx, raid_id: int, o: Outcome, now: int) -> None:
        await wallet.apply(tx, o.player.id, gold=o.gold, crystal=o.crystal, reason="raid", now=now, ref=f"raid:{raid_id}:{o.player.id}")
        for item_id, qty in o.items.items():
            await self.inventory.grant(tx, o.player.id, item_id, qty, origin="raid")
        if o.xp:
            await self.players.grant_xp(tx, o.player.id, o.xp)

    # --- what a hero reads afterwards -----------------------------------------------------------------
    def _text(self, kind: data.GlobalKind, o: Outcome, summary: dict) -> str:
        from ..data.items import get_item

        lines = [f"{kind.emoji} *{kind.title}*"]
        if kind.mode == "raid":
            lines.append("🏆 قلمرو پیروز شد!" if summary["victory"] else "💔 این بار غول پیروز شد؛ اما شما خوب جنگیدید.")
            taken = f"{fa(round(o.removed * 100))}٪ از غول را پایین آوردید" + (" و او را شکست دادید" if o.won else "")
            lines += [f"⚔️ {taken}", f"🏅 رتبه‌ی شما: {fa(o.rank)} از {fa(summary['count'])}"]
        elif kind.mode == "cup":
            lines += [f"🏅 رتبه‌ی شما در جام: {fa(o.rank)} از {fa(summary['count'])}", f"⚔️ امتیاز شما: {fa(o.score)}"]
        else:
            where = {1: "🥇 جایزه‌ی بزرگ برنده‌ی شما بود!", 2: "🥈 از برنده‌های دسته‌ی دوم بودید!", 3: "🎟️ قرعه به نام شما نیفتاد، ولی هدیه‌ی دلگرمی دارید."}
            lines.append(where[o.rank])
        gains = [f"🪙 {fa(o.gold)} سکه", f"⭐ {fa(o.xp)} تجربه"] if o.xp else [f"🪙 {fa(o.gold)} سکه"]
        if o.crystal:
            gains.append(f"💎 {fa(o.crystal)} کریستال")
        gains += [f"🎁 {get_item(i).name}" + (f" ×{fa(q)}" if q > 1 else "") for i, q in o.items.items()]
        lines += ["", "جایزه‌های شما (همین حالا به کیفتان آمد):", *gains]
        return "\n".join(lines)
