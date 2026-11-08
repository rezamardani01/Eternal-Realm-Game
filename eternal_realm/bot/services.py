"""Everything handlers need, built once at start-up and injected by the dispatcher."""

from __future__ import annotations

from dataclasses import dataclass

from ..context import AppContext
from ..game.services.activities import ActivityService
from ..game.services.admin import AdminService
from ..game.services.bosses import BossService
from ..game.services.cards import CardService
from ..game.services.characters import CharacterService
from ..game.services.chests import ChestService
from ..game.services.clans import ClanService
from ..game.services.crafting import CraftingService
from ..game.services.duels import DuelService
from ..game.services.dungeon import DungeonService
from ..game.services.economy import EconomyService
from ..game.services.events import EventService
from ..game.services.groups import GroupService
from ..game.services.hunting import HuntService
from ..game.services.inventory import InventoryService
from ..game.services.market import MarketService
from ..game.services.missions import MissionService
from ..game.services.offers import OfferService
from ..game.services.payments import PaymentService
from ..game.services.pets import PetService
from ..game.services.players import PlayerService
from ..game.services.quests import QuestService
from ..game.services.rankings import RankingService
from ..game.services.season import SeasonService
from ..game.services.shop import ShopService
from .throttle import Throttle


@dataclass
class Services:
    ctx: AppContext
    players: PlayerService
    inventory: InventoryService
    activities: ActivityService
    hunting: HuntService
    duels: DuelService
    shop: ShopService
    economy: EconomyService
    market: MarketService
    rankings: RankingService
    chests: ChestService
    payments: PaymentService
    admin: AdminService
    bosses: BossService
    events: EventService
    clans: ClanService
    quests: QuestService
    cards: CardService
    pets: PetService
    dungeon: DungeonService
    crafting: CraftingService
    season: SeasonService
    offers: OfferService
    missions: MissionService
    characters: CharacterService
    groups: GroupService
    throttle: Throttle
    bot_username: str = ""

    @classmethod
    def build(cls, ctx: AppContext) -> Services:
        balance = ctx.balance
        players = PlayerService(ctx)
        inventory = InventoryService(ctx, players)
        players.after_register.append(inventory.on_registered)
        characters = CharacterService(ctx, inventory)
        cards = CardService(ctx)
        offers = OfferService(ctx)
        bosses = BossService(ctx, players, inventory, characters, cards)
        return cls(
            ctx=ctx,
            players=players,
            inventory=inventory,
            activities=ActivityService(ctx, players, inventory),
            hunting=HuntService(ctx, players, inventory, characters, cards),
            duels=DuelService(ctx, players, characters),
            shop=ShopService(ctx, inventory),
            economy=EconomyService(ctx, inventory),
            market=MarketService(ctx, inventory),
            rankings=RankingService(ctx),
            chests=ChestService(ctx, inventory),
            payments=PaymentService(ctx, inventory),
            admin=AdminService(ctx, inventory),
            bosses=bosses,
            events=EventService(ctx, inventory, bosses),
            clans=ClanService(ctx),
            quests=QuestService(ctx, players, inventory),
            cards=cards,
            pets=PetService(ctx),
            dungeon=DungeonService(ctx, players, inventory, characters),
            crafting=CraftingService(ctx, inventory),
            season=SeasonService(ctx, inventory, cards),
            offers=offers,
            missions=MissionService(ctx, offers),
            characters=characters,
            groups=GroupService(ctx),
            throttle=Throttle(
                balance.command_gap_seconds, balance.group_flood_window, balance.group_flood_max
            ),
        )
