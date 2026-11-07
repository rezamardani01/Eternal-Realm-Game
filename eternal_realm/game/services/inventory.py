"""What players own: stackable items, gear pieces, equipping and consumables."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import inventory as repo
from ...shared.errors import GameError
from ..data.items import ITEMS, SLOT_LABELS, STARTER_WEAPON, Item, Kind, get_item, upgraded_stats
from ..data.stats import Stats
from ..models import Player
from .players import PlayerService


@dataclass
class Piece:
    """One owned gear piece with its item definition."""

    id: int
    item: Item
    upgrade: int
    slot: str | None

    @property
    def stats(self) -> Stats:
        return upgraded_stats(self.item, self.upgrade)

    @property
    def label(self) -> str:
        plus = f" +{self.upgrade}" if self.upgrade else ""
        return f"{self.item.emoji} {self.item.name}{plus}"


@dataclass
class InventoryView:
    stacks: list[tuple[Item, int]]
    gear: list[Piece]


class InventoryService:
    def __init__(self, ctx: AppContext, players: PlayerService) -> None:
        self.ctx = ctx
        self.players = players

    # --- granting / removing (inside the caller's transaction) --------------------------------
    async def grant(self, tx: Tx, player_id: int, item_id: str, qty: int = 1) -> list[int]:
        """Give items. Returns the new gear ids (empty for stackable items)."""
        item = get_item(item_id)
        if qty <= 0:
            return []
        if item.is_gear:
            now = self.ctx.now()
            return [await repo.add_gear(tx, player_id, item_id, now) for _ in range(qty)]
        await repo.add_stack(tx, player_id, item_id, qty)
        return []

    async def take(self, tx: Tx, player_id: int, item_id: str, qty: int = 1) -> None:
        if not await repo.remove_stack(tx, player_id, item_id, qty):
            raise GameError(f"{get_item(item_id).label} به اندازه کافی نداری.")

    async def piece(self, tx: Tx, player_id: int, gear_id: int) -> Piece:
        row = await repo.get_gear(tx, gear_id)
        if row is None or row.player_id != player_id:
            raise GameError("چنین تجهیزاتی در کوله‌پشتی تو نیست.")
        if row.listed:
            raise GameError("این تجهیزات برای فروش در بازار گذاشته شده؛ اول آگهی را لغو کن.")
        return Piece(row.id, get_item(row.item_id), row.upgrade, row.slot)

    async def on_registered(self, tx: Tx, player: Player) -> None:
        """Starter kit: a class weapon (equipped) and two energy potions."""
        balance = self.ctx.balance
        weapon_id = STARTER_WEAPON[player.class_id]
        gear_ids = await self.grant(tx, player.id, weapon_id)
        await repo.set_slot(tx, gear_ids[0], get_item(weapon_id).slot)
        await self.grant(tx, player.id, "energy_potion", balance.start_energy_potions)

    # --- reading ------------------------------------------------------------------------------
    async def view(self, player_id: int) -> InventoryView:
        async with self.ctx.db.read() as tx:
            stacks = [(get_item(i), q) for i, q in await repo.stacks(tx, player_id) if i in ITEMS]
            gear = [Piece(g.id, get_item(g.item_id), g.upgrade, g.slot) for g in await repo.list_gear(tx, player_id)]
        return InventoryView(stacks, gear)

    async def equipped_stats(self, tx: Tx, player_id: int) -> Stats:
        total = Stats()
        for row in await repo.list_gear(tx, player_id):
            if row.slot:
                total = total + upgraded_stats(get_item(row.item_id), row.upgrade)
        return total

    # --- equipping ----------------------------------------------------------------------------
    async def equip(self, player: Player, gear_id: int) -> tuple[Piece, Piece | None]:
        """Equip a piece. Returns ``(equipped, replaced_piece)``."""
        async with self.ctx.db.transaction() as tx:
            piece = await self.piece(tx, player.id, gear_id)
            if piece.slot is not None:
                raise GameError("این تجهیزات همین الان پوشیده شده است.")
            if player.level < piece.item.level_req:
                raise GameError(f"برای پوشیدن {piece.item.name} باید حداقل سطح {piece.item.level_req} باشی.")
            slot = piece.item.slot
            assert slot is not None
            old_row = await repo.equipped_in_slot(tx, player.id, slot)
            replaced = None
            if old_row is not None:
                await repo.set_slot(tx, old_row.id, None)
                replaced = Piece(old_row.id, get_item(old_row.item_id), old_row.upgrade, None)
            await repo.set_slot(tx, piece.id, slot)
            piece.slot = slot
            return piece, replaced

    async def unequip(self, player: Player, gear_id: int) -> Piece:
        async with self.ctx.db.transaction() as tx:
            piece = await self.piece(tx, player.id, gear_id)
            if piece.slot is None:
                raise GameError("این تجهیزات پوشیده نیست.")
            await repo.set_slot(tx, piece.id, None)
            piece.slot = None
            return piece

    # --- consumables --------------------------------------------------------------------------
    async def use(self, player: Player, item: Item) -> str:
        if item.kind is not Kind.CONSUMABLE:
            raise GameError(f"{item.label} را نمی‌شود مصرف کرد.")
        async with self.ctx.db.transaction() as tx:
            await self.take(tx, player.id, item.id)
            restored = await self.players.add_energy(tx, player.id, item.energy)
            if restored <= 0:
                raise GameError("انرژی‌ات پر است!")  # raising rolls the transaction back: nothing is used up
        return f"{item.label} را مصرف کردی و {restored} انرژی گرفتی ⚡"


def slot_label(slot: str) -> str:
    return SLOT_LABELS.get(slot, slot)
