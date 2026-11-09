"""Solo play: one interactive fight at a time against the game's own enemies, rewards paid once when it ends.

The fight is the shared combat engine (the hero acts, then the enemy answers by itself), so gear, skills, pets and
shields all count. What differs between the arena, the story, a dungeon floor and a boss is only who the enemy is, what
the fight costs and what it pays.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data import solo as data
from ..engine import combat, loot
from ..engine.combat import Action, Battle, Fighter
from ..models import Player
from .characters import CharacterService
from .inventory import InventoryService
from .pets import PetService
from .players import LevelUp, PlayerService

MAX_ROUNDS = 25
LOSS_SHARE = 0.25


def _day(now: int) -> int:
    return (now + 12600) // 86400


@dataclass
class SoloFight:
    id: int
    player_id: int
    kind: str
    status: str
    battle: Battle
    info: dict


@dataclass
class Payout:
    gold: int = 0
    xp: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)
    level_up: LevelUp | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class SoloUpdate:
    fight: SoloFight
    lines: list[str]
    finished: bool = False
    won: bool = False
    fled: bool = False
    payout: Payout = field(default_factory=Payout)


@dataclass
class EventResult:
    lines: list[str]
    payout: Payout = field(default_factory=Payout)
    fight: SoloFight | None = None


class SoloService:
    def __init__(self, ctx: AppContext, players: PlayerService, characters: CharacterService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.characters = characters
        self.inventory = inventory

    # --- progress -------------------------------------------------------------------------------------------------
    async def _progress(self, tx: Tx, pid: int, key: str) -> int:
        return int(await tx.scalar("SELECT n FROM solo_progress WHERE player_id = ? AND key = ?", (pid, key), 0))

    async def _set_progress(self, tx: Tx, pid: int, key: str, n: int) -> None:
        await tx.execute(
            "INSERT INTO solo_progress (player_id, key, n) VALUES (?, ?, ?)"
            " ON CONFLICT (player_id, key) DO UPDATE SET n = excluded.n", (pid, key, n),
        )

    async def _daily(self, tx: Tx, pid: int, key: str) -> int:
        return int(await tx.scalar(
            "SELECT n FROM solo_daily WHERE player_id = ? AND day = ? AND key = ?", (pid, _day(self.ctx.now()), key), 0
        ))

    async def _bump_daily(self, tx: Tx, pid: int, key: str) -> int:
        day = _day(self.ctx.now())
        await tx.execute(
            "INSERT INTO solo_daily (player_id, day, key, n) VALUES (?, ?, ?, 1)"
            " ON CONFLICT (player_id, day, key) DO UPDATE SET n = n + 1", (pid, day, key),
        )
        return await self._daily(tx, pid, key)

    async def overview(self, player_id: int) -> dict[str, int]:
        """Everything the hub shows: story progress, dungeon records, today's boss and arena counts."""
        day = _day(self.ctx.now())
        async with self.ctx.db.read() as tx:
            out = {r["key"]: r["n"] for r in await tx.fetchall("SELECT key, n FROM solo_progress WHERE player_id = ?", (player_id,))}
            for r in await tx.fetchall("SELECT key, n FROM solo_daily WHERE player_id = ? AND day = ?", (player_id, day)):
                out[f"today:{r['key']}"] = r["n"]
        return out

    # --- reading a fight ------------------------------------------------------------------------------------------
    @staticmethod
    def _load(row) -> SoloFight:  # noqa: ANN001
        return SoloFight(row["id"], row["player_id"], row["kind"], row["status"], Battle.from_dict(json.loads(row["state"])), json.loads(row["info"]))

    async def active(self, player_id: int) -> SoloFight | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM solo_fights WHERE player_id = ? AND status = 'active' LIMIT 1", (player_id,))
        return self._load(row) if row else None

    async def _hero(self, tx: Tx, player: Player) -> Fighter:
        stats = await self.characters.stats_in(tx, player)
        hero = Fighter.for_player(player.id, player.name, player.char_class, stats, player.mention)
        striker = await PetService(self.ctx).striker_in(tx, player.id, stats.atk)
        if striker:
            hero.pet_emoji, hero.pet_name, hero.pet_power = striker
        return hero

    # --- starting ---------------------------------------------------------------------------------------------------
    async def _begin(
        self, tx: Tx, player: Player, kind: str, foe: Fighter, info: dict, energy: int, *, shield: bool = False
    ) -> SoloFight:
        if await tx.scalar("SELECT 1 FROM solo_fights WHERE player_id = ? AND status = 'active'", (player.id,), 0):
            raise GameError("یک نبرد نیمه‌کاره دارید! اول آن را تمام کنید (از «سفر قهرمان» ادامه بدهید).")
        if energy:
            await self.players.spend_energy(tx, player.id, energy)
        hero = await self._hero(tx, player)
        hero.shield = shield
        battle = Battle.start(hero, foe, MAX_ROUNDS, self.ctx.rng)
        info = {**info, "kind": kind}
        now = self.ctx.now()
        fight_id = await tx.execute(
            "INSERT INTO solo_fights (player_id, kind, status, state, info, created_at, updated_at)"
            " VALUES (?, ?, 'active', ?, ?, ?, ?)",
            (player.id, kind, json.dumps(battle.to_dict()), json.dumps(info, ensure_ascii=False), now, now),
        )
        fight = SoloFight(fight_id, player.id, kind, "active", battle, info)
        self._foe_turns(fight, [])  # a quicker enemy opens
        await self._save(tx, fight)
        return fight

    async def _save(self, tx: Tx, fight: SoloFight) -> None:
        await tx.execute(
            "UPDATE solo_fights SET state = ?, status = ?, updated_at = ? WHERE id = ?",
            (json.dumps(fight.battle.to_dict()), fight.status, self.ctx.now(), fight.id),
        )

    def _scale(self, level: int, gold: float, xp: float) -> tuple[int, int]:
        return round(gold * loot.level_scale(level)), round(xp * loot.xp_scale(level))

    async def start_arena(self, player: Player, tier_id: str, bot_id: str | None = None) -> SoloFight:
        try:
            _, name, mult, reward, need = data.get_tier(tier_id)
        except StopIteration:
            raise GameError("این سطح در میدان نیست.") from None
        if player.level < need:
            raise GameError(f"این سطح از میدان از سطح {fa(need)} باز می‌شود.")
        bot_id = bot_id if bot_id in data.ARENA_BOTS else self.ctx.rng.choice(data.ARENA_BOTS)
        foe = data.get_foe(bot_id).fighter(player.level, mult)
        gold, xp = self._scale(player.level, 60 * reward, 55 * reward)
        info = {"title": f"میدان بات‌ها · {name}", "tier": tier_id, "gold": gold, "xp": xp, "foe": bot_id}
        async with self.ctx.db.transaction() as tx:
            return await self._begin(tx, player, "arena", foe, info, data.ENERGY["arena"])

    async def start_stage(self, player: Player, number: int, style: str) -> SoloFight:
        try:
            stage = data.get_stage(number)
        except KeyError:
            raise GameError("این مرحله وجود ندارد.") from None
        if style not in stage.labels or style not in data.STYLES:
            raise GameError("این راه در این مرحله نیست.")
        title, _, need, chapter_mult = data.CHAPTERS[stage.chapter]
        if player.level < need:
            raise GameError(f"فصل «{title}» از سطح {fa(need)} باز می‌شود.")
        async with self.ctx.db.transaction() as tx:
            cleared = await self._progress(tx, player.id, "story")
            if number > cleared + 1:
                raise GameError("اول مرحله‌های پیشین را به پایان برسانید.")
            effect = data.STYLES[style]
            foe = data.get_foe(stage.foe).fighter(player.level, chapter_mult * (1.05 if stage.boss else 1.0))
            foe.max_hp = foe.hp = round(foe.max_hp * effect["foe_hp"])
            foe.atk = round(foe.atk * effect["foe_atk"])
            base_gold, base_xp = data.stage_reward(stage)
            gold, xp = self._scale(player.level, base_gold * effect["gold"], base_xp * effect["xp"])
            replay = number <= cleared
            if replay:  # a stage already told pays a third
                gold, xp = round(gold / 3), round(xp / 3)
            info = {
                "title": f"داستان · {stage.title}", "stage": number, "gold": gold, "xp": xp, "replay": replay, "foe": stage.foe,
                "chest": ("magic_chest" if stage.boss and not replay else ""),
            }
            return await self._begin(tx, player, "story", foe, info, data.ENERGY["story"], shield=bool(effect["shield"]))

    async def start_dungeon(self, player: Player, dungeon_id: str) -> SoloFight:
        try:
            dungeon = data.get_dungeon(dungeon_id)
        except KeyError:
            raise GameError("این دخمه وجود ندارد.") from None
        if dungeon not in data.todays_dungeons(_day(self.ctx.now())):
            raise GameError("این دخمه امروز بسته است؛ دخمه‌های امروز را ببینید.")
        async with self.ctx.db.transaction() as tx:
            fight = await self._floor(tx, player, dungeon, 1, data.ENERGY["dungeon"])
            await self._set_progress(tx, player.id, "run", self._run_code(dungeon, 1))
            return fight

    @staticmethod
    def _run_code(dungeon: data.Dungeon, floor: int) -> int:
        return (data.DUNGEONS.index(dungeon) + 1) * 100 + floor

    async def _floor(self, tx: Tx, player: Player, dungeon: data.Dungeon, floor: int, energy: int) -> SoloFight:
        foe_id = data.floor_foe(dungeon, floor)
        foe = data.get_foe(foe_id).fighter(player.level, data.floor_mult(floor))
        gold, xp = self._scale(player.level, *data.floor_reward(floor))
        info = {
            "title": f"{dungeon.name} · طبقه‌ی {fa(floor)}", "dungeon": dungeon.id, "floor": floor, "gold": gold, "xp": xp,
            "foe": foe_id, "chest": ("wooden_chest" if floor == data.FLOORS else ""),
        }
        return await self._begin(tx, player, "dungeon", foe, info, energy)

    async def next_floor(self, player: Player) -> SoloFight:
        """Go on to the next floor of the dungeon run in progress (no new energy is spent)."""
        async with self.ctx.db.transaction() as tx:
            code = await self._progress(tx, player.id, "run")
            if not code:
                raise GameError("دخمه‌ای در جریان ندارید.")
            index, floor = divmod(code, 100)
            dungeon = data.DUNGEONS[index - 1]
            if dungeon not in data.todays_dungeons(_day(self.ctx.now())):
                await self._set_progress(tx, player.id, "run", 0)
                raise GameError("این دخمه برای امروز بسته شد؛ از اول وارد شوید.")
            if floor > data.FLOORS:
                await self._set_progress(tx, player.id, "run", 0)
                raise GameError("این دخمه تمام شد.")
            return await self._floor(tx, player, dungeon, floor, 0)

    async def start_boss(self, player: Player, foe_id: str) -> SoloFight:
        try:
            boss = data.get_solo_boss(foe_id)
        except StopIteration:
            raise GameError("این باس وجود ندارد.") from None
        if player.level < boss.min_level:
            raise GameError(f"این باس از سطح {fa(boss.min_level)} باز می‌شود.")
        foe = data.get_foe(foe_id).fighter(player.level, boss.mult)
        gold, xp = self._scale(player.level, boss.gold / 10, boss.xp / 10)
        info = {
            "title": f"باس تک‌نفره · {foe.name}", "boss": foe_id, "gold": gold, "xp": xp, "crystal": boss.crystal,
            "item": list(boss.item), "foe": foe_id,
        }
        async with self.ctx.db.transaction() as tx:
            return await self._begin(tx, player, "boss", foe, info, data.ENERGY["boss"])

    # --- playing -------------------------------------------------------------------------------------------------
    def _foe_turns(self, fight: SoloFight, lines: list[str]) -> None:
        battle = fight.battle
        while not battle.finished and battle.actor == 1:
            lines += combat.act(battle, combat.auto_action(battle.current), self.ctx.rng)

    async def act(self, player: Player, action: Action) -> SoloUpdate:
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM solo_fights WHERE player_id = ? AND status = 'active' LIMIT 1", (player.id,))
            if row is None:
                raise GameError("نبرد فعالی ندارید.")
            fight = self._load(row)
            battle = fight.battle
            if battle.actor != 0:
                self._foe_turns(fight, [])
            if action is Action.SKILL and battle.current.skill_ready_in > 1:
                raise GameError(f"مهارت ویژه هنوز آماده نیست؛ {fa(battle.current.skill_ready_in - 1)} نوبت دیگر صبر کنید یا حمله‌ی معمولی بزنید.")
            lines = combat.act(battle, action, self.ctx.rng)
            if not battle.finished:
                self._foe_turns(fight, lines)
            if not battle.finished:
                await self._save(tx, fight)
                return SoloUpdate(fight, lines)
            fled = battle.surrendered
            won = battle.winner == 0 and not fled
            fight.status = "won" if won else "fled" if fled else "lost"
            await self._save(tx, fight)
            payout = await self._settle(tx, player, fight, won)
            return SoloUpdate(fight, lines, finished=True, won=won, fled=fled, payout=payout)

    # --- paying out -----------------------------------------------------------------------------------------------
    async def _pay(self, tx: Tx, pid: int, gold: int, xp: int, crystal: int = 0, items: dict[str, int] | None = None) -> Payout:
        boost = await self.players.boost_factor(tx, pid)
        pay = Payout(gold=gold * boost, xp=xp * boost, crystal=crystal, items=dict(items or {}))
        now = self.ctx.now()
        await wallet.apply(tx, pid, gold=pay.gold, crystal=pay.crystal, reason="solo", now=now)
        for item_id, qty in pay.items.items():
            await self.inventory.grant(tx, pid, item_id, qty, origin="solo")
        if pay.xp:
            pay.level_up = await self.players.grant_xp(tx, pid, pay.xp)
        return pay

    async def _settle(self, tx: Tx, player: Player, fight: SoloFight, won: bool) -> Payout:
        info, pid, kind = fight.info, player.id, fight.kind
        if not won:
            if kind == "dungeon":
                await self._set_progress(tx, pid, "run", 0)
            xp = round(info.get("xp", 0) * LOSS_SHARE) if fight.status == "lost" else 0
            return await self._pay(tx, pid, 0, xp)
        gold, xp, crystal, items = info.get("gold", 0), info.get("xp", 0), 0, {}
        notes: list[str] = []
        if kind == "arena":
            wins = await self._bump_daily(tx, pid, "arena")
            if wins > data.ARENA_FULL_WINS:
                gold, xp = round(gold / 3), round(xp / 3)
                notes.append(f"پاداش میدان امروز بعد از {fa(data.ARENA_FULL_WINS)} برد یک‌سوم است.")
        elif kind == "story":
            stage = data.get_stage(info["stage"])
            if info["stage"] > await self._progress(tx, pid, "story"):
                await self._set_progress(tx, pid, "story", info["stage"])
            if info.get("chest"):
                items[info["chest"]] = 1
            last = max(s.number for s in data.STAGES if s.chapter == stage.chapter)
            if info["stage"] == last and not await self._progress(tx, pid, f"chapter:{stage.chapter}"):
                await self._set_progress(tx, pid, f"chapter:{stage.chapter}", 1)
                crystal += data.CHAPTER_DONE_CRYSTALS
                notes.append(f"فصل «{data.CHAPTERS[stage.chapter][0]}» به پایان رسید! {fa(data.CHAPTER_DONE_CRYSTALS)} کریستال هدیه.")
        elif kind == "dungeon":
            floor, dungeon = info["floor"], data.get_dungeon(info["dungeon"])
            if floor > await self._progress(tx, pid, f"dng:{dungeon.id}"):
                await self._set_progress(tx, pid, f"dng:{dungeon.id}", floor)
                notes.append(f"رکورد تازه در «{dungeon.name}»: طبقه‌ی {fa(floor)}!")
            if info.get("chest"):
                items[info["chest"]] = 1
            await self._set_progress(tx, pid, "run", 0 if floor >= data.FLOORS else self._run_code(dungeon, floor + 1))
        elif kind == "boss":
            first = await self._bump_daily(tx, pid, f"boss:{info['boss']}") == 1
            if first:
                crystal, items[info["item"][0]] = info["crystal"], info["item"][1]
            else:
                gold, xp = round(gold / 3), round(xp / 3)
                notes.append("این باس را امروز زده‌اید؛ پاداش ویژه فقط روزی یک بار است.")
            kills = await self._progress(tx, pid, f"boss:{info['boss']}")
            await self._set_progress(tx, pid, f"boss:{info['boss']}", kills + 1)
        pay = await self._pay(tx, pid, gold, xp, crystal, items)
        pay.notes = notes
        return pay

    async def abandon(self, player: Player) -> None:
        """Walk away from a fight in progress (no reward; energy is not returned)."""
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "UPDATE solo_fights SET status = 'fled', updated_at = ? WHERE player_id = ? AND status = 'active'",
                (self.ctx.now(), player.id),
            )
            if tx.rowcount == 0:
                raise GameError("نبرد فعالی ندارید.")
            await self._set_progress(tx, player.id, "run", 0)

    # --- events on the road ---------------------------------------------------------------------------------------
    async def wander(self, player: Player) -> data.RoadEvent:
        async with self.ctx.db.transaction() as tx:
            if await self._progress(tx, player.id, "event"):
                raise GameError("یک اتفاق در راه منتظر تصمیم شماست.")
            await self.players.spend_energy(tx, player.id, data.ENERGY["wander"])
            index = self.ctx.rng.randrange(len(data.EVENTS))
            await self._set_progress(tx, player.id, "event", index + 1)
            return data.EVENTS[index]

    async def pending_event(self, player_id: int) -> data.RoadEvent | None:
        async with self.ctx.db.read() as tx:
            n = await self._progress(tx, player_id, "event")
        return data.EVENTS[n - 1] if n else None

    async def decide(self, player: Player, choice_index: int) -> EventResult:
        rng: random.Random = self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            n = await self._progress(tx, player.id, "event")
            if not n:
                raise GameError("اتفاقی در راه نیست.")
            event = data.EVENTS[n - 1]
            if not 0 <= choice_index < len(event.choices):
                raise GameError("این گزینه وجود ندارد.")
            result = dict(event.choices[choice_index].result)
            lines: list[str] = []
            pay = Payout()
            if "pay" in result:
                await wallet.apply(tx, player.id, gold=-result["pay"], reason="road_event", now=self.ctx.now())
                lines.append(f"🪙 {fa(result['pay'])} سکه پرداختید.")
            if "chance" in result:
                result = result["win"] if rng.random() < result["chance"] else result["lose"]
            if "fight" in result:
                gold, xp = self._scale(player.level, 70, 60)
                foe = data.get_foe(result["fight"]).fighter(player.level, 0.9)
                await self._set_progress(tx, player.id, "event", 0)
                fight = await self._begin(tx, player, "event", foe, {"title": "راهزن جاده", "gold": gold, "xp": xp, "foe": result["fight"]}, 0)
                return EventResult(["راهزن شمشیر کشید!"], fight=fight)
            gold = rng.randint(*result["gold"]) if "gold" in result else 0
            xp = rng.randint(*result["xp"]) if "xp" in result else 0
            items = {result["item"][0]: result["item"][1]} if "item" in result else {}
            pay = await self._pay(tx, player.id, round(gold * loot.level_scale(player.level)), round(xp * loot.xp_scale(player.level)), result.get("crystal", 0), items)
            lines.insert(0, result.get("text", "ماجرا گذشت."))
            await self._set_progress(tx, player.id, "event", 0)
            return EventResult(lines, pay)
