"""Everything handlers need, built once at start-up and injected by the dispatcher."""

from __future__ import annotations

from dataclasses import dataclass

from ..context import AppContext
from ..game.services.characters import CharacterService
from ..game.services.groups import GroupService
from ..game.services.inventory import InventoryService
from ..game.services.players import PlayerService
from .throttle import Throttle


@dataclass
class Services:
    ctx: AppContext
    players: PlayerService
    inventory: InventoryService
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
        return cls(
            ctx=ctx,
            players=players,
            inventory=inventory,
            characters=CharacterService(ctx, inventory),
            groups=GroupService(ctx),
            throttle=Throttle(
                balance.command_gap_seconds, balance.group_flood_window, balance.group_flood_max
            ),
        )
