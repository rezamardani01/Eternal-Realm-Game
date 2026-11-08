"""Group bosses: summon, sign up, then the bot plays the fight round by round.

Nothing runs per boss in memory. The whole fight lives in the database (a JSON snapshot plus the
time of the next round), and one central processor, :meth:`BossService.process_due`, advances every
fight that is due. A restart simply continues from the stored state.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import bosses as repo
from ...db.repos import clans as clan_repo
from ...db.repos import inventory as inv_repo
from ...db.repos import wallet
from ...shared.errors import GameError, NotRegistered
from ...shared.jalali import describe
from ...shared.text import duration, fa
from ..data.bosses import (
    BossType,
    behavior_of,
    boss_attack,
    boss_by_id,
    boss_defense,
    pick_boss,
    boss_max_hp,
)
from ..data.classes import CLASSES
from ..data.sets import BOSS_DROPS
from ..engine.boss_fight import Boss, Hero, is_over, run_round
from ..models import Player
from .characters import CharacterService
from .inventory import InventoryService
from .players import PlayerService

MAX_CATCH_UP_ROUNDS = 3
REPORT_LINES = 7
#: a group that lost to a boss may summon the same one again within a day: it is angrier, but pays more
REVENGE_WINDOW = 24 * 3600
REVENGE_POWER = 1.15
REVENGE_REWARD = 1.5


@dataclass
class Payout:
    name: str
    mention: str
    damage: int
    share: float
    gold: int
    xp: int
    chest: str | None = None
    level_up: int | None = None
    trophy: str | None = None
    card: str | None = None


@dataclass
class FighterView:
    name: str
    mention: str
    emoji: str
    hp: int
    max_hp: int
    alive: bool
    damage: int


@dataclass
class BossView:
    id: int
    chat_id: int
    message_id: int | None
    type: BossType
    level: int
    phase: str  # recruiting | fighting | ended
    status: str  # active | defeated | expired
    hp: int
    max_hp: int
    summoner: str
    summoner_mention: str
    recruit_until: int
    expires_at: int
    now: int
    round: int = 0
    fighters: list[FighterView] = field(default_factory=list)
    report: list[str] = field(default_factory=list)
    payouts: list[Payout] = field(default_factory=list)
    #: how a finished fight ended: won | lost | fled | cancelled
    outcome: str | None = None
    free: bool = False
    #: the boss came back angrier after a lost fight (stronger, pays more when beaten)
    revenge: bool = False

    @property
    def seconds_left(self) -> int:
        end = self.recruit_until if self.phase == "recruiting" else self.expires_at
        return max(0, end - self.now)

    @property
    def alive_count(self) -> int:
        return sum(f.alive for f in self.fighters)


@dataclass
class BossUpdate:
    view: BossView
    #: started | report | final | cancelled
    kind: str


class BossService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, inventory: InventoryService, characters: CharacterService,
        cards: object | None = None,
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory
        self.cards = cards
        self.characters = characters

    # --- views --------------------------------------------------------------------------------
    async def _view(
        self, tx: Tx, row: Row, payouts: list[Payout] | None = None, outcome: str | None = None
    ) -> BossView:
        roster = await repo.fighters(tx, row["id"])
        summoner = next((r for r in roster if r["player_id"] == row["summoner_id"]), None)
        state = json.loads(row["state"] or "{}")
        phase = "ended" if row["status"] != "active" else row["phase"]
        return BossView(
            id=row["id"], chat_id=row["chat_id"], message_id=row["message_id"], type=boss_by_id(row["boss_type"]),
            level=row["level"], phase=phase, status=row["status"], hp=row["hp"], max_hp=row["max_hp"],
            summoner=summoner["name"] if summoner else "؟",
            summoner_mention=f"[{summoner['name']}](uid:{summoner['platform_user_id']})" if summoner else "؟",
            recruit_until=row["recruit_until"], expires_at=row["expires_at"], now=self.ctx.now(),
            round=state.get("boss", {}).get("round", 0),
            fighters=[
                FighterView(
                    r["name"], f"[{r['name']}](uid:{r['platform_user_id']})", CLASSES[r["class_id"]].emoji,
                    r["hp"], r["max_hp"], bool(r["alive"]), r["damage"],
                )
                for r in roster
            ],
            report=state.get("recent", []), payouts=payouts or [], outcome=outcome, free=bool(state.get("free")),
            revenge=bool(state.get("revenge")),
        )

    async def active(self, chat_id: int) -> BossView | None:
        async with self.ctx.db.read() as tx:
            row = await repo.active_in_chat(tx, chat_id)
            return await self._view(tx, row) if row is not None else None

    async def revenge_boss(self, chat_id: int):  # noqa: ANN201 - BossType | None
        """The boss that beat this group within the last day and is still owed a rematch, if any."""
        async with self.ctx.db.read() as tx:
            return self._owed(await repo.last_ended(tx, chat_id), self.ctx.now())

    def _owed(self, prev: Row | None, now: int):  # noqa: ANN202
        if prev is None or prev["status"] != "expired" or not prev["ended_at"]:
            return None
        if json.loads(prev["state"] or "{}").get("revenge"):
            return None  # one rematch per defeat, not an endless chain
        if now - prev["ended_at"] > REVENGE_WINDOW:
            return None
        return boss_by_id(prev["boss_type"])

    async def attach_message(self, boss_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await repo.set_message(tx, boss_id, message_id)

    async def summon_event(self, chat_id: int) -> BossView:
        """A hidden boss that the bot itself brings into a group: free, and anyone may start it."""
        from ...db.repos import events as event_repo
        from ...db.repos import players as player_repo

        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            if await repo.active_in_chat(tx, chat_id) is not None or await event_repo.active_in_chat(tx, chat_id, now):
                raise GameError("busy")
            last = await repo.last_created(tx, chat_id)
            if last and last + b.boss_cooldown_seconds > now:
                raise GameError("cooldown")
            pid = await event_repo.most_recent_member(tx, chat_id)
            lead = await player_repo.get(tx, pid) if pid else None
            if lead is None or lead.level < b.boss_min_level:
                raise GameError("nobody strong enough")
            kind = pick_boss(lead.level, self.ctx.rng)
            boss_id = await repo.create(
                tx, chat_id, kind.id, lead.level, lead.id, now, now + b.boss_recruit_seconds, json.dumps({"free": True})
            )
            await self._enlist(tx, boss_id, lead)
            row = await repo.get(tx, boss_id)
            assert row is not None
            return await self._view(tx, row)

    # --- summon and sign-up ---------------------------------------------------------------------
    async def summon(self, player: Player, chat_id: int) -> BossView:
        b, now = self.ctx.balance, self.ctx.now()
        if player.level < b.boss_min_level:
            raise GameError(
                f"🐉 احضار باس از سطح {fa(b.boss_min_level)} ممکن است. شما سطح {fa(player.level)} هستید؛ "
                "کمی ماجراجویی کنید و برگردید!"
            )
        async with self.ctx.db.transaction() as tx:
            current = await repo.active_in_chat(tx, chat_id)
            if current is not None:
                raise GameError("🐉 در این گروه یک باس زنده است! پیامش را بالاتر ببینید یا «باس» را دوباره بنویسید.")
            last = await repo.last_created(tx, chat_id)
            wait = last + b.boss_cooldown_seconds - now if last else 0
            if wait > 0:
                raise GameError(f"⏳ باس بعدی این گروه تا {duration(wait)} دیگر آماده می‌شود. تا آن موقع قدرت جمع کنید!")
            await wallet.apply(tx, player.id, gold=-b.boss_summon_gold, reason="boss_summon", now=now)
            owed = self._owed(await repo.last_ended(tx, chat_id), now)
            kind = owed or pick_boss(player.level, self.ctx.rng)
            boss_id = await repo.create(
                tx, chat_id, kind.id, player.level, player.id, now, now + b.boss_recruit_seconds,
                json.dumps({"revenge": True}) if owed else "{}",
            )
            await self._enlist(tx, boss_id, player)
            row = await repo.get(tx, boss_id)
            assert row is not None
            return await self._view(tx, row)

    async def _enlist(self, tx: Tx, boss_id: int, player: Player) -> None:
        stats = await self.characters.stats_in(tx, player)
        if not await repo.add_fighter(tx, boss_id, player.id, stats.hp):
            raise GameError("شما همین الان در این نبرد هستید، فرمانده!")

    async def join(self, boss_id: int, player: Player) -> BossView:
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, boss_id)
            if row is None or row["status"] != "active":
                raise GameError("🐉 این نبرد تمام شده است.")
            if row["phase"] != "recruiting" or row["recruit_until"] <= now:
                raise GameError("⏳ ثبت‌نام این نبرد بسته شده؛ نبرد شروع شده یا در حال شروع است.")
            if len(await repo.fighters(tx, boss_id)) >= b.boss_max_players:
                raise GameError(f"👥 ظرفیت پر است! حداکثر {fa(b.boss_max_players)} جنگجو می‌توانند شرکت کنند.")
            await self._enlist(tx, boss_id, player)
            return await self._view(tx, row)

    async def start(self, boss_id: int, player: Player) -> BossView:
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, boss_id)
            if row is None or row["status"] != "active":
                raise GameError("🐉 این نبرد تمام شده است.")
            free = json.loads(row["state"] or "{}").get("free", False)
            if row["summoner_id"] != player.id and not (free and await self._is_fighter(tx, row["id"], player.id)):
                raise GameError("🚀 فقط احضارکننده‌ی باس می‌تواند نبرد را شروع کند.")
            if row["phase"] != "recruiting":
                raise GameError("⚔️ نبرد همین الان در جریان است!")
            return await self._begin(tx, row, self.ctx.now())

    async def _begin(self, tx: Tx, row: Row, now: int) -> BossView:
        b = self.ctx.balance
        roster = await repo.fighters(tx, row["id"])
        if len(roster) < b.boss_min_players:
            raise GameError(
                f"👥 برای شروع نبرد حداقل {fa(b.boss_min_players)} جنگجو لازم است؛ "
                f"الان {fa(len(roster))} نفر هستید. دوستانتان را صدا بزنید!"
            )
        heroes: list[Hero] = []
        for r in roster:
            player = await self.players_get(tx, r["player_id"])
            stats = await self.characters.stats_in(tx, player)
            heroes.append(
                Hero(player.id, player.mention, player.class_id, stats.hp, stats.hp, stats.atk, stats.defense,
                     stats.magic, stats.speed, stats.luck)
            )
        avg_level = max(1, round(sum(r["level"] for r in roster) / len(roster)))
        kind = boss_by_id(row["boss_type"])
        revenge = bool(json.loads(row["state"] or "{}").get("revenge"))
        hp = round(boss_max_hp(kind, len(roster), avg_level) * (REVENGE_POWER if revenge else 1))
        boss = Boss(
            kind.name, hp, hp, round(boss_attack(kind, avg_level) * (REVENGE_POWER if revenge else 1)), boss_defense(avg_level),
            special=kind.special, weak_class=kind.weak_class, behavior=behavior_of(kind)[0],
        )
        state = {"boss": asdict(boss), "heroes": [asdict(h) for h in heroes], "pending": [], "recent": [
            f"⚔️ نبرد با {kind.name} آغاز شد!"
        ], **({"revenge": True} if revenge else {})}
        begun = await repo.begin_fight(
            tx, row["id"], avg_level, hp, json.dumps(state, ensure_ascii=False), now,
            now + b.boss_round_seconds, now + b.boss_fight_seconds,
        )
        if not begun:
            raise GameError("⚔️ نبرد همین الان در جریان است!")
        fresh = await repo.get(tx, row["id"])
        assert fresh is not None
        return await self._view(tx, fresh)

    async def _is_fighter(self, tx: Tx, boss_id: int, player_id: int) -> bool:
        return any(r["player_id"] == player_id for r in await repo.fighters(tx, boss_id))

    async def players_get(self, tx: Tx, player_id: int) -> Player:
        from ...db.repos import players as player_repo

        player = await player_repo.get(tx, player_id)
        if player is None:
            raise NotRegistered
        return player

    # --- the central processor ------------------------------------------------------------------
    async def process_due(self) -> list[BossUpdate]:
        """Advance every boss that needs it. Call this every few seconds from one place."""
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            ids = [r["id"] for r in await repo.all_active(tx)]
        updates: list[BossUpdate] = []
        for boss_id in ids:
            async with self.ctx.db.transaction() as tx:
                row = await repo.get(tx, boss_id)
                if row is None or row["status"] != "active":
                    continue
                update = await self._process(tx, row, now)
                if update is not None:
                    updates.append(update)
        return updates

    async def _process(self, tx: Tx, row: Row, now: int) -> BossUpdate | None:
        if row["phase"] == "recruiting":
            if row["recruit_until"] > now:
                return None
            roster = await repo.fighters(tx, row["id"])
            if len(roster) >= self.ctx.balance.boss_min_players:
                return BossUpdate(await self._begin(tx, row, now), "started")
            await repo.close(tx, row["id"], "expired", now)
            if not json.loads(row["state"] or "{}").get("free"):  # event bosses cost nothing, so nothing to refund
                await wallet.apply(
                    tx, row["summoner_id"], gold=self.ctx.balance.boss_summon_gold, reason="boss_refund", now=now,
                    ref=f"boss:{row['id']}:refund",
                )
            fresh = await repo.get(tx, row["id"])
            assert fresh is not None
            return BossUpdate(await self._view(tx, fresh, outcome="cancelled"), "cancelled")
        return await self._advance(tx, row, now)

    async def _advance(self, tx: Tx, row: Row, now: int) -> BossUpdate | None:
        b, rng = self.ctx.balance, self.ctx.rng
        state = json.loads(row["state"])
        boss = Boss(**state["boss"])
        heroes = [Hero(**h) for h in state["heroes"]]
        pending: list[list] = state["pending"]
        next_at, rounds, outcome = row["next_round_at"], 0, None
        while next_at <= now and rounds < MAX_CATCH_UP_ROUNDS and outcome is None:
            pending += [[prio, text] for prio, text in run_round(boss, heroes, rng)]
            next_at += b.boss_round_seconds
            rounds += 1
            outcome = is_over(boss, heroes)
        if next_at < now - b.boss_round_seconds:
            next_at = now  # after a long outage do not hoard a backlog of rounds
        if outcome is None and now >= row["expires_at"]:
            outcome = "fled"
        if rounds == 0 and outcome is None:
            return None

        for hero in heroes:
            await repo.save_fighter(tx, row["id"], hero.pid, hero.hp, hero.alive, hero.damage, hero.absorbed)
        state["boss"], state["heroes"] = asdict(boss), [asdict(h) for h in heroes]

        report_due = now - row["last_report_at"] >= b.boss_report_seconds
        if outcome is not None or report_due:
            state["recent"] = _pick_report(pending)
            state["pending"], last_report = [], now
        else:
            state["pending"], last_report = pending[-60:], row["last_report_at"]
        await repo.save_fight(tx, row["id"], boss.hp, json.dumps(state, ensure_ascii=False), next_at, last_report)

        if outcome is None:
            if not report_due:
                return None
            fresh = await repo.get(tx, row["id"])
            assert fresh is not None
            return BossUpdate(await self._view(tx, fresh), "report")
        status = "defeated" if outcome == "won" else "expired"
        payouts = await self._settle(tx, row, status, now)
        fresh = await repo.get(tx, row["id"])
        assert fresh is not None
        return BossUpdate(await self._view(tx, fresh, payouts, outcome), "final")

    # --- rewards --------------------------------------------------------------------------------
    async def _settle(self, tx: Tx, row: Row, status: str, now: int) -> list[Payout]:
        """Close the boss (once) and pay every fighter by contribution. A lost fight pays a consolation."""
        if not await repo.close(tx, row["id"], status, now):
            return []
        revenge = bool(json.loads(row["state"] or "{}").get("revenge"))
        factor = (REVENGE_REWARD if revenge else 1.0) if status == "defeated" else 0.25
        roster = await repo.fighters(tx, row["id"])
        weights = {r["player_id"]: r["damage"] + r["absorbed"] for r in roster}
        total = sum(weights.values()) or 1
        ranked = sorted(roster, key=lambda r: -weights[r["player_id"]])
        pool = round((500 + 100 * row["level"]) * factor)
        payouts: list[Payout] = []
        for index, r in enumerate(ranked):
            pid, share = r["player_id"], weights[r["player_id"]] / total
            gold = max(round(40 * factor), round(pool * share))
            xp = round((60 + 10 * row["level"]) * (0.5 + share) * factor)
            await wallet.apply(tx, pid, gold=gold, reason="boss_reward", now=now, ref=f"boss:{row['id']}:{pid}")
            level_up = await self.players.grant_xp(tx, pid, xp)
            await clan_repo.add_war_points(tx, pid, round((10 + 60 * share) * factor), now)
            from ...db.repos import season as season_repo

            await season_repo.add_points(tx, pid, "boss", now)
            await inv_repo.add_bond(tx, pid, 3)
            if status == "defeated":
                await season_repo.add_points(tx, pid, "boss_win", now)
            chest = trophy = None
            if status == "defeated":
                chest = "magic_chest" if index == 0 else "wooden_chest" if share >= 0.10 else None
                if chest:
                    await self.inventory.grant(tx, pid, chest, 1)
                chance = 0.40 if index == 0 else 0.12
                if self.ctx.rng.random() < chance:
                    trophy = self.ctx.rng.choices(
                        [i for i, _ in BOSS_DROPS], weights=[w for _, w in BOSS_DROPS], k=1
                    )[0]
                    kind = boss_by_id(row["boss_type"])
                    date = describe(now)[0]
                    await self.inventory.grant(
                        tx, pid, trophy, 1, origin=f"غنیمت شکست {kind.name} · {date}\nنخستین صاحب: {r['name']}"
                    )
            card_name = None
            if status == "defeated" and self.cards is not None:
                dropped = await self.cards.drop_for_boss(
                    tx, pid, boss_by_id(row["boss_type"]).element.id, 0.35 if index == 0 else 0.15
                )
                card_name = f"{dropped.emoji} {dropped.name}" if dropped else None
            payouts.append(
                Payout(r["name"], f"[{r['name']}](uid:{r['platform_user_id']})", r["damage"], share, gold, xp, chest,
                       level_up.new_level if level_up else None, trophy, card_name)
            )
        return payouts


def _pick_report(pending: list[list]) -> list[str]:
    """The lines worth showing: the most important events, kept in the order they happened."""
    indexed = list(enumerate(pending))
    best = sorted(indexed, key=lambda item: (-item[1][0], -item[0]))[:REPORT_LINES]
    return [text for _, (_, text) in sorted(best)]
