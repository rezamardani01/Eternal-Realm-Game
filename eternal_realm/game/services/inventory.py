"""What players own: stackable items (materials, potions, chests, tickets) and consumables.

War gear is a separate system (``arms.py``)."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import inventory as repo
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.items import ITEMS, Item, Kind, get_item
from ..models import Player
from .players import PlayerService


@dataclass
class InventoryView:
    stacks: list[tuple[Item, int]]

    def stack_qty(self, item_id: str) -> int:
        return next((q for item, q in self.stacks if item.id == item_id), 0)


class InventoryService:
    def __init__(self, ctx: AppContext, players: PlayerService) -> None:
        self.ctx = ctx
        self.players = players

    # --- granting / removing (inside the caller's transaction) --------------------------------
    async def grant(self, tx: Tx, player_id: int, item_id: str, qty: int = 1, origin: str = "") -> None:
        """Give items (``origin`` is kept for old callers; stackable items have no history)."""
        get_item(item_id)
        if qty > 0:
            await repo.add_stack(tx, player_id, item_id, qty)

    async def take(self, tx: Tx, player_id: int, item_id: str, qty: int = 1) -> None:
        if not await repo.remove_stack(tx, player_id, item_id, qty):
            have = await repo.stack_qty(tx, player_id, item_id)
            raise GameError(
                f"📦 {get_item(item_id).label} کافی نیست.\n"
                f"دارید {fa(have)} · نیاز دارید {fa(qty)} · کمبود {fa(qty - have)}"
            )

    async def on_registered(self, tx: Tx, player: Player) -> None:
        """Starter kit: a few energy potions."""
        await self.grant(tx, player.id, "energy_potion", self.ctx.balance.start_energy_potions)

    # --- reading ------------------------------------------------------------------------------
    async def view(self, player_id: int) -> InventoryView:
        async with self.ctx.db.read() as tx:
            stacks = [(get_item(i), q) for i, q in await repo.stacks(tx, player_id) if i in ITEMS]
        return InventoryView(stacks)

    # --- consumables --------------------------------------------------------------------------
    async def use(self, player: Player, item: Item) -> str:
        if item.kind is not Kind.CONSUMABLE:
            raise GameError(f"{item.label} را نمی‌شود نوشید یا مصرف کرد؛ فقط معجون‌ها قابل مصرف‌اند.")
        async with self.ctx.db.transaction() as tx:
            await self.take(tx, player.id, item.id)
            restored = await self.players.add_energy(tx, player.id, item.energy)
            if restored <= 0:
                raise GameError("انرژی شما پر پر است، فرمانده! معجون را برای وقتی نگه دارید که خسته شدید.")  # raising rolls the transaction back: nothing is used up
        return f"🧪 {item.label} را نوشیدید و {restored} انرژی تازه در رگ‌هایتان دوید! ⚡"
