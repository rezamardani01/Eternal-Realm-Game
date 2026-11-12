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
from ..data import maze as maze_data
from ..data import solo as data
from ..data import world as world_data
from ..engine import combat, loot
from ..engine.combat import Action, Battle, Fighter
from ..models import Player
from .characters import CharacterService
from .inventory import InventoryService
from .pets import PetService
from .players import LevelUp, PlayerService
from .world import WorldService

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
    #: for a story stage: 1 bronze, 2 silver, 3 gold (0 = not a stage)
    grade: int = 0


@dataclass
class SoloUpdate:
    fight: SoloFight
    lines: list[str]
    finished: bool = False
    won: bool = False
    fled: bool = False
    payout: Payout = field(default_factory=Payout)


@dataclass
class MazeRun:
    floor: int
    hp: float
    buffs: dict[str, float]
    gold: int
    xp: int
    #: what stands on this floor: "scene" (a story with choices) or "giant" (a fight), and which one
    kind: str
    ref: str
    #: the scenes this run has already told, so none comes twice
    seen: list[str] = field(default_factory=list)

    @property
    def tier(self) -> str | None:
        return maze_data.giant_tier(self.floor) if self.kind == "giant" else None


@dataclass
class MazeStep:
    lines: list[str]
    run: MazeRun | None
    fight: SoloFight | None = None
    payout: Payout = field(default_factory=Payout)
    ended: bool = False


@dataclass
class EventResult:
    lines: list[str]
    payout: Payout = field(default_factory=Payout)
    fight: SoloFight | None = None


class SoloService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, characters: CharacterService, inventory: InventoryService,
        world: WorldService,
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.characters = characters
        self.inventory = inventory
        self.world = world

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

    async def recent_results(self, player_id: int, count: int = 3) -> list[str]:
        """The verdicts of the last few finished fights (newest first): won, lost or fled."""
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT status FROM solo_fights WHERE player_id = ? AND status != 'active' ORDER BY id DESC LIMIT ?",
                (player_id, count),
            )
        return [r["status"] for r in rows]

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

    async def last_finished(self, player_id: int) -> SoloFight | None:
        """The fight that ended most recently (to rescue a tap on a button of a fight that is already over)."""
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM solo_fights WHERE player_id = ? AND status != 'active' ORDER BY id DESC LIMIT 1", (player_id,))
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
        self, tx: Tx, player: Player, kind: str, foe: Fighter, info: dict, energy: int, *, shield: bool = False,
        hp_frac: float = 1.0, buffs: dict[str, float] | None = None,
    ) -> SoloFight:
        if await tx.scalar("SELECT 1 FROM solo_fights WHERE player_id = ? AND status = 'active'", (player.id,), 0):
            raise GameError("یک نبرد نیمه‌کاره دارید! اول آن را تمام کنید (از «سفر قهرمان» ادامه بدهید).")
        if energy:
            await self.players.spend_energy(tx, player.id, energy)
        hero = await self._hero(tx, player)
        hero.shield = shield
        for stat, amount in (buffs or {}).items():  # temporary powers (and curses) of a maze run
            if stat == "atk":
                hero.atk, hero.magic = max(1, round(hero.atk * (1 + amount))), max(1, round(hero.magic * (1 + amount)))
            elif stat == "def":
                hero.defense = round(hero.defense * (1 + amount))
            elif stat == "hp":
                hero.max_hp = round(hero.max_hp * (1 + amount))
        hero.hp = max(1, round(hero.max_hp * hp_frac)) if hp_frac < 1.0 else hero.max_hp
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
        return round(gold * data.REWARD_SHARE * loot.level_scale(level)), round(xp * data.REWARD_SHARE * loot.xp_scale(level))

    async def _use_today(self, tx: Tx, player: Player, section: str) -> None:
        """One use of a section of the trip; a hero gets ``DAILY_USES`` of each a day (the owner is exempt)."""
        if self.players.is_owner(player):
            return
        used = await self._daily(tx, player.id, f"use:{section}")
        if used >= data.DAILY_USES:
            raise GameError(f"امروز از «{data.SECTION_NAMES[section]}» استفاده کرده‌اید؛ هر بخش سفر قهرمان روزی {fa(data.DAILY_USES)} بار باز است. فردا برگردید!")
        await self._bump_daily(tx, player.id, f"use:{section}")

    async def start_arena(self, player: Player, tier_id: str, bot_id: str | None = None) -> SoloFight:
        try:
            _, name, mult, reward, need = data.get_tier(tier_id)
        except StopIteration:
            raise GameError("این سطح در میدان نیست.") from None
        if player.level < need:
            raise GameError(f"این سطح از میدان از سطح {fa(need)} باز می‌شود.")
        bot_id = bot_id if bot_id in data.ARENA_BOTS else self.ctx.rng.choice(data.ARENA_BOTS)
        async with self.ctx.db.transaction() as tx:
            await self._use_today(tx, player, "arena")
            fm, rm = await self.world.effect(tx, world_data.ARENA_REGION)  # a darker region fights harder and pays more
            foe = data.get_foe(bot_id).fighter(player.level, mult * fm)
            gold, xp = self._scale(player.level, 60 * reward * rm, 55 * reward * rm)
            info = {"title": f"میدان بات‌ها · {name}", "tier": tier_id, "gold": gold, "xp": xp, "foe": bot_id, "region": world_data.ARENA_REGION}
            return await self._begin(tx, player, "arena", foe, info, data.ENERGY["arena"])

    async def start_academy(self, player: Player) -> SoloFight:
        """The academy's practice fight: a weak training goblin, no energy and no daily limit (a lost one is just tried again)."""
        async with self.ctx.db.transaction() as tx:
            foe = data.get_foe("dark_goblin").fighter(player.level, 0.45)
            foe.name = "گابلین تمرینی"
            gold, xp = self._scale(player.level, 20, 30)
            info = {"title": "آکادمی · نبرد تمرینی", "gold": gold, "xp": xp, "foe": "dark_goblin"}
            return await self._begin(tx, player, "academy", foe, info, 0)

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
            region = world_data.STORY_REGION[stage.chapter]
            fm, rm = await self.world.effect(tx, region)
            foe = data.get_foe(stage.foe).fighter(player.level, chapter_mult * (1.05 if stage.boss else 1.0) * fm)
            foe.max_hp = foe.hp = round(foe.max_hp * effect["foe_hp"])
            foe.atk = round(foe.atk * effect["foe_atk"])
            base_gold, base_xp = data.stage_reward(stage)
            gold, xp = self._scale(player.level, base_gold * effect["gold"] * rm, base_xp * effect["xp"] * rm)
            replay = number <= cleared
            if not replay:
                await self._use_today(tx, player, "story")
            if replay:  # a stage already told pays a third
                gold, xp = round(gold / 3), round(xp / 3)
            info = {
                "title": f"داستان · {stage.title}", "stage": number, "gold": gold, "xp": xp, "replay": replay, "foe": stage.foe,
                "region": region,
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
            await self._use_today(tx, player, "dungeon")
            fight = await self._floor(tx, player, dungeon, 1, data.ENERGY["dungeon"])
            await self._set_progress(tx, player.id, "run", self._run_code(dungeon, 1))
            return fight

    @staticmethod
    def _run_code(dungeon: data.Dungeon, floor: int) -> int:
        return (data.DUNGEONS.index(dungeon) + 1) * 100 + floor

    async def _floor(self, tx: Tx, player: Player, dungeon: data.Dungeon, floor: int, energy: int) -> SoloFight:
        foe_id = data.floor_foe(dungeon, floor)
        region = world_data.DUNGEON_REGION[dungeon.id]
        fm, rm = await self.world.effect(tx, region)
        foe = data.get_foe(foe_id).fighter(player.level, data.floor_mult(floor) * fm)
        base_gold, base_xp = data.floor_reward(floor)
        gold, xp = self._scale(player.level, base_gold * rm, base_xp * rm)
        info = {
            "title": f"{dungeon.name} · طبقه‌ی {fa(floor)}", "dungeon": dungeon.id, "floor": floor, "gold": gold, "xp": xp,
            "foe": foe_id, "chest": ("wooden_chest" if floor == data.FLOORS else ""), "region": region,
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
            await self._use_today(tx, player, "boss")
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
            lines: list[str] = []
            if not battle.finished:  # a far stronger foe that opened the fight may already have ended it
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
        if kind == "maze":
            return await self._maze_fought(tx, player, fight, won)
        if kind == "world":
            return await self._world_fought(tx, player, fight, won)
        if not won:
            if kind == "dungeon":
                await self._set_progress(tx, pid, "run", 0)
            xp = round(info.get("xp", 0) * LOSS_SHARE) if fight.status == "lost" else 0
            return await self._pay(tx, pid, 0, xp)
        gold, xp, crystal, items = info.get("gold", 0), info.get("xp", 0), 0, {}
        notes: list[str] = []
        grade = 0
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
            hero_hp = fight.battle.fighters[0].hp / max(1, fight.battle.fighters[0].max_hp)
            grade = 3 if hero_hp >= 0.75 else 2 if hero_hp >= 0.4 else 1  # bronze: won; silver/gold: won with health to spare
            best = await self._progress(tx, pid, f"grade:{info['stage']}")
            if grade > best:
                await self._set_progress(tx, pid, f"grade:{info['stage']}", grade)
                crystal += grade - best  # a better grade pays the difference in crystals
                if grade > 1:
                    notes.append(f"درجه‌ی {data.GRADES[grade]} برای این مرحله: {fa(grade - best)} کریستال هدیه.")
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
        elif kind == "tower":
            gold, xp, crystal, items, notes = await self._tower_won(tx, pid, info)
        elif kind == "boss":
            first = await self._bump_daily(tx, pid, f"boss:{info['boss']}") == 1
            if first:
                crystal, items[info["item"][0]] = info["crystal"], info["item"][1]
            else:
                gold, xp = round(gold / 3), round(xp / 3)
                notes.append("این باس را امروز زده‌اید؛ پاداش ویژه فقط روزی یک بار است.")
            kills = await self._progress(tx, pid, f"boss:{info['boss']}")
            await self._set_progress(tx, pid, f"boss:{info['boss']}", kills + 1)
        if info.get("region"):  # a win pushes the region's darkness back a little
            await self.world.relieve(tx, info["region"], 1 if kind == "arena" else 2)
        pay = await self._pay(tx, pid, gold, xp, crystal, items)
        pay.notes = notes
        if kind == "story":
            pay.grade = grade
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
            await tx.execute("DELETE FROM maze_runs WHERE player_id = ?", (player.id,))

    # --- world events ----------------------------------------------------------------------------------------------
    async def start_world_fight(self, player: Player) -> SoloFight:
        """Fight the guardian of the world event in progress; whatever damage is done counts for everybody."""
        event = await self.world.active(player.id)
        if event is None:
            raise GameError("الان رویداد جهانی فعالی نیست؛ کمی بعد دوباره سر بزنید.")
        foe = data.get_foe(event.kind.foe).fighter(player.level, 0.95)
        gold, xp = self._scale(player.level, 80, 90)
        info = {"title": f"رویداد جهانی · {event.kind.title}", "event": event.id, "gold": gold, "xp": xp, "foe": event.kind.foe}
        async with self.ctx.db.transaction() as tx:
            await self._use_today(tx, player, "world")
            return await self._begin(tx, player, "world", foe, info, world_data.ENERGY)

    async def _world_fought(self, tx: Tx, player: Player, fight: SoloFight, won: bool) -> Payout:
        info, foe = fight.info, fight.battle.fighters[1]
        removed = 0.0 if fight.status == "fled" else 1 - max(0, foe.hp) / max(1, foe.max_hp)
        points = round(100 * removed * (1 + player.level / 50) * (1.2 if won else 1.0))
        points = max(5, points) if fight.status != "fled" else 0
        notes = await self.world.contribute(tx, info["event"], player.id, points) if points else ["فرار کردید و سهمی ثبت نشد."]
        pay = await self._pay(tx, player.id, info["gold"] if won else 0, info["xp"] if won else round(info["xp"] * LOSS_SHARE))
        pay.notes = notes
        return pay

    # --- the eternal maze ----------------------------------------------------------------------------------------
    async def maze_run(self, player_id: int) -> MazeRun | None:
        async with self.ctx.db.read() as tx:
            return await self._run(tx, player_id)

    async def _run(self, tx: Tx, player_id: int) -> MazeRun | None:
        row = await tx.fetchone("SELECT * FROM maze_runs WHERE player_id = ?", (player_id,))
        if row is None:
            return None
        floor, stage = row["floor"], json.loads(row["options"])
        if not isinstance(stage, dict):  # a run saved before floors had scenes: give its floor a fixed one
            if maze_data.giant_tier(floor):
                pool = maze_data.pool_for(floor)
                stage = {"kind": "giant", "ref": maze_data.BOSS_FLOORS.get(floor) or pool[(player_id + floor) % len(pool)]}
            else:
                stage = {"kind": "scene", "ref": maze_data.SCENE_IDS[(player_id + floor) % len(maze_data.SCENE_IDS)]}
        return MazeRun(
            floor, row["hp"], json.loads(row["buffs"]), row["gold"], row["xp"], stage["kind"], stage["ref"],
            list(stage.get("seen", [])),
        )

    @staticmethod
    def _stage_json(run: MazeRun) -> str:
        return json.dumps({"kind": run.kind, "ref": run.ref, "seen": run.seen})

    async def _save_run(self, tx: Tx, player_id: int, run: MazeRun) -> None:
        await tx.execute(
            "UPDATE maze_runs SET floor = ?, hp = ?, buffs = ?, gold = ?, xp = ?, options = ? WHERE player_id = ?",
            (run.floor, run.hp, json.dumps(run.buffs), run.gold, run.xp, self._stage_json(run), player_id),
        )

    def _enter(self, run: MazeRun, floor: int) -> None:
        """Step onto a floor and decide what waits there: a giant, the campfire before a guardian, or a new scene."""
        rng = self.ctx.rng
        run.floor = floor
        if maze_data.giant_tier(floor):
            run.kind, run.ref = "giant", maze_data.BOSS_FLOORS.get(floor) or rng.choice(maze_data.pool_for(floor))
        elif floor + 1 in maze_data.BOSS_FLOORS:
            run.kind, run.ref = "scene", maze_data.CAMPFIRE.id
        else:
            fresh = [s for s in maze_data.SCENE_IDS if s not in run.seen]
            if not fresh:
                run.seen, fresh = [], list(maze_data.SCENE_IDS)
            run.kind, run.ref = "scene", rng.choice(fresh)
            run.seen.append(run.ref)

    async def maze_start(self, player: Player) -> MazeRun:
        async with self.ctx.db.transaction() as tx:
            if await self._run(tx, player.id) is not None:
                raise GameError("یک هزارتوی نیمه‌کاره دارید؛ ادامه‌اش بدهید یا با غنیمت بیرون بیایید.")
            done = await self._progress(tx, player.id, "maze:chapters")
            if done >= len(maze_data.CHAPTERS):
                raise GameError("هر چهار فصل هزارتو را فتح کرده‌اید؛ هزارتو برای هر قهرمان فقط یک بار باز است و دیگر درهایش بسته شد. 🏆")
            await self._use_today(tx, player, "maze")
            await self.players.spend_energy(tx, player.id, maze_data.ENERGY)
            first = done * maze_data.CHAPTER_FLOORS + 1
            run = MazeRun(first, 1.0, {}, 0, 0, "scene", "")
            self._enter(run, first)
            await tx.execute(
                "INSERT INTO maze_runs (player_id, floor, hp, buffs, gold, xp, options, started) VALUES (?, ?, 1.0, '{}', 0, 0, ?, ?)",
                (player.id, first, self._stage_json(run), self.ctx.now()),
            )
            return run

    async def maze_chapters_done(self, player_id: int) -> int:
        async with self.ctx.db.read() as tx:
            return await self._progress(tx, player_id, "maze:chapters")

    async def _maze_fight(self, tx: Tx, player: Player, run: MazeRun, foe_id: str, path: str, bonus: float = 0.0) -> SoloFight:
        """A fight on the run's floor. ``path``: a giant's tier, or "ambush" for a foe met by accident."""
        floor = run.floor
        if path == "ambush":
            mult, share = maze_data.AMBUSH_MULT, 1.0 + bonus
        else:
            _, mult, share, _ = maze_data.TIERS[path]
        level = maze_data.foe_level(floor, player.level)
        foe = data.get_foe(foe_id).fighter(level, mult)
        gold, xp = self._scale(player.level, *(v * share for v in maze_data.floor_reward(floor)))
        info = {
            "title": f"هزارتوی ابدی · طبقه‌ی {fa(floor)}", "floor": floor, "path": path, "gold": gold, "xp": xp,
            "foe": foe_id, "level": level,
        }
        return await self._begin(tx, player, "maze", foe, info, 0, hp_frac=run.hp, buffs=run.buffs)

    async def maze_pick(self, player: Player, index: int) -> MazeStep:
        rng = self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            run = await self._run(tx, player.id)
            if run is None:
                raise GameError("هزارتویی در جریان ندارید.")
            if await tx.scalar("SELECT 1 FROM solo_fights WHERE player_id = ? AND status = 'active'", (player.id,), 0):
                raise GameError("اول نبرد نیمه‌کاره را تمام کنید.")
            if run.kind == "giant":
                return await self._face_giant(tx, player, run, index)
            scene = maze_data.SCENES[run.ref]
            if not 0 <= index < len(scene.choices):
                raise GameError("این راه در این طبقه نیست.")
            outcomes = scene.choices[index].outcomes
            outcome = rng.choices(outcomes, weights=[o.weight for o in outcomes])[0]
            fx, lines, items = outcome.fx, [outcome.text], {}
            base_gold, base_xp = self._scale(player.level, *maze_data.floor_reward(run.floor))
            if "hurt" in fx:
                run.hp = max(0.05, run.hp - fx["hurt"])
                lines.append(f"💔 {fa(round(fx['hurt'] * 100))}٪ از جانتان رفت")
            if "bless" in fx:
                stat = rng.choice(list(maze_data.BLESSINGS)) if fx["bless"] == "any" else fx["bless"]
                label, amount = maze_data.BLESSINGS[stat]
                run.buffs[stat] = round(run.buffs.get(stat, 0.0) + amount, 3)
                lines.append(f"✨ {label} (تا پایان این هزارتو)")
            if fx.get("curse"):
                label, stat, amount = maze_data.CURSE
                run.buffs[stat] = round(run.buffs.get(stat, 0.0) + amount, 3)
                lines.append(f"🕸️ {label}")
            if "heal" in fx:
                run.hp = min(1.0, run.hp + fx["heal"])
                lines.append(f"💚 {fa(round(fx['heal'] * 100))}٪ از جانتان برگشت")
            if "lose" in fx:
                lost = round(run.gold * fx["lose"])
                run.gold -= lost
                lines.append(f"💸 {fa(lost)} سکه از غنیمت‌تان رفت" if lost else "💸 غنیمتی نداشتید که ببازید")
            if fx.get("fight"):
                await self._save_run(tx, player.id, run)
                foe_id = rng.choice(maze_data.pool_for(run.floor))
                fight = await self._maze_fight(tx, player, run, foe_id, "ambush", fx.get("gold", 0.0))
                return MazeStep(lines, run, fight=fight)
            if "gold" in fx:
                gold = round(base_gold * fx["gold"])
                run.gold += gold
                lines.append(f"🪙 {fa(gold)} سکه به غنیمت‌تان اضافه شد")
            if "xp" in fx:
                xp = round(base_xp * fx["xp"])
                run.xp += xp
                lines.append(f"⭐ {fa(xp)} تجربه اندوختید")
            if "item" in fx:
                items[fx["item"][0]] = fx["item"][1]
                lines.append("🎁 چیزی هم به کوله‌تان رفت")
            payout = await self._pay(tx, player.id, 0, 0, 0, items) if items else Payout()
            self._enter(run, run.floor + 1)
            await self._save_run(tx, player.id, run)
            return MazeStep(lines, run, payout=payout)

    async def _face_giant(self, tx: Tx, player: Player, run: MazeRun, index: int) -> MazeStep:
        """A giant's floor: 0 fights it; 1 tries to slip past (ordinary giants only)."""
        tier, foe = run.tier or "giant", data.get_foe(run.ref)
        if index == 1 and tier == "giant":
            if self.ctx.rng.random() < maze_data.SNEAK_CHANCE:
                self._enter(run, run.floor + 1)
                await self._save_run(tx, player.id, run)
                return MazeStep([f"🌫️ نفس در سینه حبس کردید و از پشت سر {foe.name} گذشتید؛ بی‌غنیمت، اما سالم."], run)
            run.hp = max(0.05, run.hp - maze_data.SNEAK_HURT)
            await self._save_run(tx, player.id, run)
            fight = await self._maze_fight(tx, player, run, run.ref, tier)
            return MazeStep([f"{foe.name} بوی شما را شنید و پیش از آنکه بجنبید ضربه‌ای زد!"], run, fight=fight)
        if index != 0:
            raise GameError("این راه در این طبقه نیست.")
        fight = await self._maze_fight(tx, player, run, run.ref, tier)
        return MazeStep([f"{foe.name} راهتان را بسته است!"], run, fight=fight)

    async def _maze_fought(self, tx: Tx, player: Player, fight: SoloFight, won: bool) -> Payout:
        pid, info = player.id, fight.info
        run = await self._run(tx, pid)
        if run is None:
            return Payout()
        floor = info["floor"]
        hero = fight.battle.fighters[0]
        if not won:
            pay = await self._finish_run(tx, pid, run, maze_data.DEFEAT_SHARE)
            pay.notes.insert(0, f"هزارتو شما را در طبقه‌ی {fa(floor)} بلعید؛ نیمی از غنیمت‌تان ماند.")
            if fight.status == "lost":
                level = info.get("level", 0)
                pay.notes.append(
                    f"این دشمن هم‌تراز سطح {fa(level)} بود؛ سطح و تجهیزاتتان را بالا ببرید و برگردید."
                    if level > player.level else "تجهیزاتتان را قوی‌تر کنید و در راه دنبال برکت و آتشگاه باشید."
                )
            return pay
        run.gold += info["gold"]
        run.xp += info["xp"]
        run.hp = max(0.05, hero.hp / max(1, hero.max_hp))
        notes: list[str] = []
        items: dict[str, int] = {}
        chance = maze_data.TIERS[info["path"]][3] if info["path"] in maze_data.TIERS else 0.0
        if self.ctx.rng.random() < chance:
            gear = self._gear_for(player.level)
            if gear:
                items[gear] = 1
                notes.append("سلاح یا زرهی از غول به یغما رفت!")
        crystal = 0
        if floor in maze_data.MILESTONES and not await self._progress(tx, pid, f"maze:milestone:{floor}"):
            await self._set_progress(tx, pid, f"maze:milestone:{floor}", 1)
            crystal, chest = maze_data.MILESTONES[floor]
            items[chest] = items.get(chest, 0) + 1
            notes.append(f"نخستین بار نگهبان طبقه‌ی {fa(floor)} را شکست دادید: جایزه‌ی ماندگار!")
        if floor > await self._progress(tx, pid, "maze:best"):
            await self._set_progress(tx, pid, "maze:best", floor)
            notes.append(f"رکورد تازه‌ی هزارتو: طبقه‌ی {fa(floor)}")
        if floor >= maze_data.chapter_end(floor):
            chapter = maze_data.chapter_of(floor)
            await self._set_progress(tx, pid, "maze:chapters", max(chapter, await self._progress(tx, pid, "maze:chapters")))
            pay = await self._finish_run(tx, pid, run, 1.0)
            title = maze_data.CHAPTERS[chapter - 1][0]
            from ...db.repos import titles

            await titles.award(tx, pid, f"maze:{chapter}", f"{maze_data.CHAPTERS[chapter - 1][1]} فاتح فصل {fa(chapter)} هزارتو", self.ctx.now())
            if chapter >= len(maze_data.CHAPTERS):
                await titles.award(tx, pid, "maze:master", "👑 فاتح هزارتوی ابدی", self.ctx.now())
                notes.append("هر چهار فصل هزارتو را فتح کردید؛ نشان «فاتح هزارتوی ابدی» برای همیشه به نام شماست! 🏆")
            else:
                notes.append(f"فصل «{title}» به پایان رسید؛ فصل بعد باز شد. همه‌ی غنیمت‌تان با شماست.")
            pay.notes = notes
            extra = await self._pay(tx, pid, 0, 0, crystal, items)
            pay.crystal, pay.items = extra.crystal, extra.items
            return pay
        self._enter(run, floor + 1)
        await self._save_run(tx, pid, run)
        pay = await self._pay(tx, pid, 0, 0, crystal, items)
        pay.notes = notes
        return pay

    def _gear_for(self, level: int) -> str:
        from ..data.items import ITEMS

        pool = [i.id for i in ITEMS.values() if i.is_gear and i.buy > 0 and i.level_req <= level and i.rarity <= 3]
        return self.ctx.rng.choice(pool) if pool else ""

    async def _finish_run(self, tx: Tx, pid: int, run: MazeRun, share: float) -> Payout:
        await tx.execute("DELETE FROM maze_runs WHERE player_id = ?", (pid,))
        return await self._pay(tx, pid, round(run.gold * share), round(run.xp * share))

    async def maze_retreat(self, player: Player) -> Payout:
        """Leave with everything gathered so far."""
        async with self.ctx.db.transaction() as tx:
            run = await self._run(tx, player.id)
            if run is None:
                raise GameError("هزارتویی در جریان ندارید.")
            if await tx.scalar("SELECT 1 FROM solo_fights WHERE player_id = ? AND status = 'active'", (player.id,), 0):
                raise GameError("اول نبرد نیمه‌کاره را تمام کنید.")
            return await self._finish_run(tx, player.id, run, 1.0)

    # --- the endless tower ------------------------------------------------------------------------
    async def tower_state(self, player_id: int) -> tuple[int, int, int]:
        """(floors cleared, best floor, climbs today)."""
        async with self.ctx.db.read() as tx:
            cleared = await self._progress(tx, player_id, "tower:floor")
            best = await self._progress(tx, player_id, "tower:best")
            today = await self._daily(tx, player_id, "tower")
        return cleared, best, today

    async def tower_board(self, limit: int = 10) -> list[tuple[int, str, int]]:
        """The tallest climbers of all time: (rank, name, best floor)."""
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.display_name AS name, s.n AS best FROM solo_progress s JOIN players p ON p.id = s.player_id"
                " WHERE s.key = 'tower:best' AND p.banned = 0 ORDER BY s.n DESC, p.id LIMIT ?", (limit,),
            )
        return [(i, r["name"], r["best"]) for i, r in enumerate(rows, 1)]

    async def start_tower(self, player: Player) -> SoloFight:
        async with self.ctx.db.transaction() as tx:
            floor = await self._progress(tx, player.id, "tower:floor") + 1
            foe_id = maze_data.tower_foe(floor)
            level = maze_data.foe_level(min(floor, maze_data.FLOORS), player.level)
            foe = data.get_foe(foe_id).fighter(level, maze_data.tower_mult(floor))
            gold, xp = self._scale(player.level, *maze_data.tower_reward(floor))
            info = {
                "title": f"برج بی‌پایان · طبقه‌ی {fa(floor)}", "floor": floor, "gold": gold, "xp": xp, "foe": foe_id, "level": level,
                "guardian": floor % 10 == 0,
            }
            return await self._begin(tx, player, "tower", foe, info, maze_data.TOWER_ENERGY)

    async def _tower_won(self, tx: Tx, pid: int, info: dict) -> tuple[int, int, int, dict[str, int], list[str]]:
        floor = info["floor"]
        gold, xp, crystal, items, notes = info["gold"], info["xp"], 0, {}, []
        climbs = await self._bump_daily(tx, pid, "tower")
        if climbs > maze_data.TOWER_FULL_CLIMBS:
            gold, xp = round(gold / 3), round(xp / 3)
            notes.append(f"پاداش برج بعد از {fa(maze_data.TOWER_FULL_CLIMBS)} صعود امروز یک‌سوم است.")
        if floor > await self._progress(tx, pid, "tower:floor"):
            await self._set_progress(tx, pid, "tower:floor", floor)
        if floor > await self._progress(tx, pid, "tower:best"):
            await self._set_progress(tx, pid, "tower:best", floor)
            notes.append(f"رکورد تازه‌ی برج: طبقه‌ی {fa(floor)}!")
            if floor % 10 == 0:  # the first time only a guardian floor pays a lasting prize
                crystal = 1 + floor // 20
                items["wooden_chest" if floor < 50 else "magic_chest"] = 1
                notes.append(f"نگهبان طبقه‌ی {fa(floor)} شکست خورد: جایزه‌ی ماندگار!")
        return gold, xp, crystal, items, notes

    # --- events on the road ---------------------------------------------------------------------------------------
    async def wander(self, player: Player) -> data.RoadEvent:
        async with self.ctx.db.transaction() as tx:
            if await self._progress(tx, player.id, "event"):
                raise GameError("یک اتفاق در راه منتظر تصمیم شماست.")
            await self._use_today(tx, player, "wander")
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
                fight = await self._begin(tx, player, "event", foe, {"title": f"گشت‌زنی · {foe.name}", "gold": gold, "xp": xp, "foe": result["fight"]}, 0)
                return EventResult([f"{foe.name} راهتان را بست و شمشیر کشید!"], fight=fight)
            gold = rng.randint(*result["gold"]) if "gold" in result else 0
            xp = rng.randint(*result["xp"]) if "xp" in result else 0
            items = {result["item"][0]: result["item"][1]} if "item" in result else {}
            pay = await self._pay(tx, player.id, round(gold * data.REWARD_SHARE * loot.level_scale(player.level)), round(xp * data.REWARD_SHARE * loot.xp_scale(player.level)), result.get("crystal", 0), items)
            lines.insert(0, result.get("text", "ماجرا گذشت."))
            await self._set_progress(tx, player.id, "event", 0)
            return EventResult(lines, pay)
