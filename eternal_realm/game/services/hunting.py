"""Hunting: an auto-resolved fight against a monster scaled to the hero."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import events as event_repo
from ...db.repos import inventory as inv_repo
from ...db.repos import players as player_repo
from ...db.repos import season as season_repo
from ...db.repos import wallet
from ...shared.errors import GameError, NotRegistered
from ...shared.text import duration
from ..data.items import get_item
from ..data.monsters import MONSTERS, Monster
from ..engine import loot
from ..engine.combat import Battle, Fighter, auto_fight
from ..models import Player
from .characters import CharacterService
from .inventory import InventoryService
from .players import LevelUp, PlayerService

HUNT_ENERGY = 10
HUNT_COOLDOWN = 30
LOSS_XP_SHARE = 0.25


def _power(f: Fighter) -> float:
    return f.max_hp * max(f.atk, f.magic * 0.8)


@dataclass
class HuntResult:
    monster: Monster
    won: bool
    rounds: int
    hero_hp: int
    hero_max_hp: int
    gold: int
    xp: int
    items: list[tuple[str, int, str]]
    level_up: LevelUp | None
    player: Player
    highlights: list[str]
    log: list[str]
    next_in: int = 0
    double_xp: bool = False
    card: object | None = None


class HuntService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, inventory: InventoryService,
        characters: CharacterService, cards: object | None = None,
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory
        self.characters = characters
        self.cards = cards

    def pick_monster(self, level: int, hero: Fighter) -> Monster:
        """Random monster of the hero's level band that is not far stronger than the hero."""
        band = [m for m in MONSTERS if m.min_level <= level <= m.max_level] or [MONSTERS[0]]
        fair = [m for m in band if _power(m.fighter(level)) <= 1.1 * _power(hero)]
        pool = fair or [min(band, key=lambda m: _power(m.fighter(level)))]
        return self.ctx.rng.choices(pool, weights=[m.weight for m in pool], k=1)[0]

    async def hunt(self, player_id: int, chat_id: int | None = None) -> HuntResult:
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            player = await player_repo.get(tx, player_id)
            if player is None:
                raise NotRegistered
            until = await inv_repo.cooldown_until(tx, player_id, "hunt")
            if until > now:
                raise GameError(
                    f"⏳ زخم‌هایتان هنوز تازه است، فرمانده!\n\nتا {duration(until - now)} دیگر می‌توانید دوباره شکار کنید."
                )
            await self.players.spend_energy(tx, player_id, HUNT_ENERGY)

            stats = await self.characters.stats_in(tx, player)
            hero = Fighter.for_player(player.id, player.name, player.char_class, stats)
            monster = self.pick_monster(player.level, hero)
            foe = monster.fighter(player.level)
            battle = Battle.start(hero, foe, self.ctx.balance.duel_max_rounds, rng)
            log = auto_fight(battle, rng)
            won = battle.winner == 0 and not battle.surrendered

            gold = xp = 0
            items: dict[str, int] = {}
            if won:
                perk = player.race.perks.get("hunt", 1.0)
                gold = round(rng.randint(*monster.gold) * loot.level_scale(player.level) * perk)
                xp = round(rng.randint(*monster.xp) * loot.xp_scale(player.level))
                for drop in monster.drops:
                    if rng.random() <= drop.chance:
                        items[drop.item_id] = rng.randint(*drop.qty)
            else:
                xp = round(rng.randint(*monster.xp) * loot.xp_scale(player.level) * LOSS_XP_SHARE)
            double = chat_id is not None and await event_repo.double_xp_active(tx, chat_id, now)
            if double:
                xp *= 2
            await wallet.apply(tx, player_id, gold=gold, reason="hunt", now=now)
            for item_id, qty in items.items():
                await self.inventory.grant(tx, player_id, item_id, qty)
            level_up = await self.players.grant_xp(tx, player_id, xp) if xp else None
            card = None
            await season_repo.add_points(tx, player_id, "hunt", now)
            if won and self.cards is not None:
                card = await self.cards.drop_for_monster(tx, player_id, monster.id)
            wait = await self.players.schedule_cooldown(tx, player_id, "hunt")
            after = await player_repo.get(tx, player_id)
            assert after is not None
        return HuntResult(
            monster=monster, won=won, rounds=min(battle.round, battle.max_rounds),
            hero_hp=max(0, hero.hp), hero_max_hp=hero.max_hp, gold=gold, xp=xp,
            items=[(get_item(i).label, q, i) for i, q in items.items()], level_up=level_up,
            player=self.players.with_energy(after), highlights=log[-3:], log=log, next_in=wait, double_xp=double, card=card,
        )
