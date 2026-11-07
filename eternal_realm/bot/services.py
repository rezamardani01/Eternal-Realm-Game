"""Everything handlers need, built once at start-up and injected by the dispatcher."""

from __future__ import annotations

from dataclasses import dataclass

from ..context import AppContext
from ..game.services.characters import CharacterService
from ..game.services.players import PlayerService


@dataclass
class Services:
    ctx: AppContext
    players: PlayerService
    characters: CharacterService
    bot_username: str = ""

    @classmethod
    def build(cls, ctx: AppContext) -> Services:
        return cls(ctx=ctx, players=PlayerService(ctx), characters=CharacterService(ctx))
