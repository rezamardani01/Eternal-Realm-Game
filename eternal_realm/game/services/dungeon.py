"""The dungeon: five rooms in a row - monsters or strange events - ending with a guardian boss.

Health carries over from room to room. Treasure is paid only when the run ends: all of it for a
victory, half of it if the hero falls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import duration, fa
from ..data.items import get_item
from ..data.monsters import MONSTERS, Monster
from ..engine.combat import Battle, Fighter, auto_fight
from ..models import Player
from .characters import CharacterService
from .inventory import InventoryService
from .players import PlayerService

ROOMS = 5
ENERGY_COST = 30
COOLDOWN = 2 * 3600
DUNGEON_BOSS = "نگهبان سیاه‌چال"


@dataclass
class RunView:
    stage: int
    hp: int
    max_hp: int
    gold: int
    xp: int
    items: dict[str, int]
    status: str  # active | won | dead | none
    #: what just happened (empty when only looking at the run)
    lines: list[str] = field(default_factory=list)
    emoji: str = "🕳️"
    title: str = ""
    level_up: int | None = None
    paid_gold: int = 0
    paid_xp: int = 0


class DungeonService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, inventory: InventoryService, characters: CharacterService
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory
        self.characters = characters

    # --- reading ---------------------------------------------------------------------------------
    async def current(self, player_id: int) -> RunView | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM player_dungeon WHERE player_id = ?", (player_id,))
        return self._view(row) if row else None

    @staticmethod
    def _view(row) -> RunView:  # noqa: ANN001
        loot = json.loads(row["loot"] or "{}")
        return RunView(row["stage"], row["hp"], row["max_hp"], row["gold"], row["xp"], loot, "active")

    # --- entering --------------------------------------------------------------------------------
    async def enter(self, player: Player) -> RunView:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            if await tx.fetchone("SELECT 1 FROM player_dungeon WHERE player_id = ?", (player.id,)):
                raise GameError("شما همین حالا داخل سیاه‌چال هستید! دکمه‌ی «اتاق بعدی» را بزنید.")
            until = int(await tx.scalar("SELECT until FROM cooldowns WHERE player_id = ? AND key = 'dungeon'", (player.id,), 0))
            if until > now:
                raise GameError(f"🕯️ سیاه‌چال هنوز بسته است. {duration(until - now)} دیگر دوباره می‌توانید وارد شوید.")
            await self.players.spend_energy(tx, player.id, ENERGY_COST)
            stats = await self.characters.stats_in(tx, player)
            await tx.execute(
                "INSERT INTO player_dungeon (player_id, stage, hp, max_hp, gold, xp, loot, started_at)"
                " VALUES (?, 0, ?, ?, 0, 0, '{}', ?)",
                (player.id, stats.hp, stats.hp, now),
            )
            await tx.execute(
                "INSERT INTO cooldowns (player_id, key, until) VALUES (?, 'dungeon', ?)"
                " ON CONFLICT (player_id, key) DO UPDATE SET until = excluded.until",
                (player.id, now + COOLDOWN),
            )
            return RunView(0, stats.hp, stats.hp, 0, 0, {}, "active")

    async def leave(self, player: Player) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("DELETE FROM player_dungeon WHERE player_id = ?", (player.id,))

    # --- one room --------------------------------------------------------------------------------
    def _monster(self, level: int, stage: int) -> Monster:
        band = [m for m in MONSTERS if m.min_level <= level <= m.max_level] or [MONSTERS[0]]
        return self.ctx.rng.choice(band)

    async def advance(self, player: Player) -> RunView:
        rng = self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM player_dungeon WHERE player_id = ?", (player.id,))
            if row is None:
                raise GameError("شما داخل سیاه‌چال نیستید. اول وارد شوید.")
            stage = row["stage"] + 1
            hp, max_hp, gold, xp = row["hp"], row["max_hp"], row["gold"], row["xp"]
            loot: dict[str, int] = json.loads(row["loot"] or "{}")
            fresh = await player_repo.get(tx, player.id)
            assert fresh is not None
            lines: list[str] = []
            emoji, title = "🕳️", f"اتاق {fa(stage)}"
            died = False
            boss_room = stage == ROOMS
            if boss_room or rng.random() < 0.7:
                monster = self._monster(fresh.level, stage)
                stats = await self.characters.stats_in(tx, fresh)
                hero = Fighter.for_player(fresh.id, fresh.name, fresh.char_class, stats)
                hero.hp = hp
                foe = monster.fighter(fresh.level)
                scale = 1.7 if boss_room else 1 + 0.08 * stage
                foe.max_hp = foe.hp = round(foe.max_hp * scale)
                foe.atk = round(foe.atk * (1.15 if boss_room else 1.0))
                if boss_room:
                    foe.name, emoji, title = DUNGEON_BOSS, "👑", "اتاق نگهبان"
                else:
                    emoji, title = monster.emoji, f"اتاق {fa(stage)} · {monster.name}"
                battle = Battle.start(hero, foe, 20, rng)
                auto_fight(battle, rng)
                hp = max(0, hero.hp)
                won = battle.winner == 0 and not battle.surrendered
                if won:
                    gold += round(rng.randint(*monster.gold) * (3 if boss_room else 1) * (1 + 0.1 * fresh.level))
                    xp += round(rng.randint(*monster.xp) * (3 if boss_room else 1))
                    lines.append(f"با {foe.name} جنگیدید و برنده شدید!")
                    lines.append(f"از جانتان {fa(max(0, row['hp'] - hp))} کم شد." if row["hp"] > hp else "تقریباً زخمی نشدید.")
                    hp = min(max_hp, hp + round(max_hp * 0.10))
                    if boss_room:
                        loot["magic_chest"] = loot.get("magic_chest", 0) + 1
                else:
                    died = True
                    lines.append(f"با {foe.name} جنگیدید، اما او قوی‌تر بود و جانتان تمام شد.")
            else:
                kind = rng.choice(("treasure", "trap", "spring", "shrine"))
                if kind == "treasure":
                    emoji, title = "💰", f"اتاق {fa(stage)} · گنج"
                    found = rng.randint(40, 90) + 8 * fresh.level
                    gold += found
                    lines.append(f"یک صندوق قدیمی پیدا کردید! توی آن {fa(found)} سکه بود.")
                elif kind == "trap":
                    emoji, title = "🪤", f"اتاق {fa(stage)} · تله"
                    hurt = max(1, round(max_hp * rng.uniform(0.12, 0.22)))
                    hp = max(1, hp - hurt)
                    lines.append(f"آخ! پایتان روی یک تله رفت و {fa(hurt)} از جانتان کم شد.")
                elif kind == "shrine":
                    from .effects import EffectService

                    service = EffectService(self.ctx)
                    effect = service.roll(0.6)
                    await service.give(tx, player.id, effect)
                    emoji, title = effect.emoji, f"اتاق {fa(stage)} · محراب"
                    lines.append(f"یک محراب قدیمی پیدا کردید. {'یک برکت خوب' if effect.blessing else 'یک نفرین'} به نام «{effect.name}» گرفتید!")
                else:
                    emoji, title = "⛲", f"اتاق {fa(stage)} · چشمه"
                    healed = min(max_hp - hp, round(max_hp * 0.30))
                    hp += healed
                    lines.append(f"یک چشمه‌ی درخشان پیدا کردید. از آبش خوردید و {fa(healed)} جان گرفتید.")

            view = RunView(stage, hp, max_hp, gold, xp, loot, "active", lines, emoji, title)
            if died or boss_room:
                await tx.execute("DELETE FROM player_dungeon WHERE player_id = ?", (player.id,))
                share = 0.5 if died else 1.0
                view.status = "dead" if died else "won"
                from ...db.repos import season as season_repo

                await season_repo.add_points(tx, player.id, "dungeon", self.ctx.now())
                if not died:
                    await season_repo.add_points(tx, player.id, "dungeon_win", self.ctx.now())
                boost = await self.players.boost_factor(tx, player.id)
                view.paid_gold, view.paid_xp = round(gold * share) * boost, round(xp * share) * boost
                loot = {item_id: qty * boost for item_id, qty in loot.items()}
                now = self.ctx.now()
                await wallet.apply(
                    tx, player.id, gold=view.paid_gold, reason="dungeon", now=now, ref=f"dungeon:{player.id}:{now}"
                )
                if not died:
                    for item_id, qty in loot.items():
                        await self.inventory.grant(tx, player.id, item_id, qty)
                if view.paid_xp:
                    up = await self.players.grant_xp(tx, player.id, view.paid_xp)
                    view.level_up = up.new_level if up else None
            else:
                await tx.execute(
                    "UPDATE player_dungeon SET stage = ?, hp = ?, gold = ?, xp = ?, loot = ? WHERE player_id = ?",
                    (stage, hp, gold, xp, json.dumps(loot), player.id),
                )
            return view


def loot_lines(items: dict[str, int]) -> list[str]:
    return [f"{get_item(i).label} ×{fa(q)}" for i, q in items.items()]
