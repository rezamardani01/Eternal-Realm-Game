"""Chests: buying with in-game currency and opening."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import inventory as inv_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.chests import CHESTS, Chest, Prize
from ..data.items import Item, Kind, get_item
from ..models import Player
from .arms import FREE_CHANCE, ArmsService
from .inventory import InventoryService


@dataclass
class Opened:
    chest: Item
    prize: Prize
    gold: int
    crystal: int
    item: Item | None
    qty: int
    #: war gear found inside (a lucky free drop)
    arm: str | None = None


@dataclass
class OpenedAll:
    """The sum of many chests opened at once."""

    count: int
    #: how many of each kind of chest were opened: ``{chest item id: n}``
    chests: dict[str, int]
    gold: int
    crystal: int
    items: dict[str, int]
    #: pieces of war gear found: ``{arm id: n}``
    arms: dict[str, int]


#: the most chests one tap opens (a message must stay short and a transaction small)
OPEN_ALL_LIMIT = 100


class ChestService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    def odds(self, chest: Chest) -> list[tuple[Prize, float]]:
        total = chest.total_weight
        return [(p, p.weight / total) for p in chest.prizes]

    def roll(self, chest: Chest) -> Prize:
        return self.ctx.rng.choices(chest.prizes, weights=[p.weight for p in chest.prizes], k=1)[0]

    async def buy(self, player: Player, chest_id: str, qty: int = 1) -> tuple[str, int]:
        """Buy chests with gold or crystals. Returns ``(currency, total_price)``."""
        chest = CHESTS.get(chest_id)
        if chest is None or chest.price is None:
            raise GameError("این صندوقچه فروشی نیست؛ فقط از ماجراجویی به دست می‌آید.")
        if not 1 <= qty <= 20:
            raise GameError("هر بار فقط می‌توانید بین ۱ تا ۲۰ صندوقچه بخرید.")
        currency, unit = chest.price
        total = unit * qty
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(
                tx, player.id, reason="chest_buy", now=self.ctx.now(),
                **{currency: -total},
            )
            await self.inventory.grant(tx, player.id, chest_id, qty)
        return currency, total

    async def _open_one(self, tx, player_id: int, item: Item) -> Opened:  # noqa: ANN001 - Tx
        """Open one chest inside the caller's transaction: take it, pay what was inside."""
        chest = CHESTS.get(item.id)
        if item.kind is not Kind.CHEST or chest is None:
            raise GameError(f"{item.label} صندوقچه نیست و قفلی ندارد که بشکنید!")
        prize = self.roll(chest)
        rng = self.ctx.rng
        gold = rng.randint(*prize.gold) if prize.gold[1] else 0
        crystal = rng.randint(*prize.crystal) if prize.crystal[1] else 0
        qty = rng.randint(*prize.qty) if prize.item_id else 0
        await self.inventory.take(tx, player_id, item.id, 1)
        await wallet.apply(tx, player_id, gold=gold, crystal=crystal, reason="chest_open", now=self.ctx.now())
        if prize.item_id:
            await self.inventory.grant(tx, player_id, prize.item_id, qty)
        found = await ArmsService(self.ctx).free_drop(tx, player_id, FREE_CHANCE["chest"])
        return Opened(item, prize, gold, crystal, get_item(prize.item_id) if prize.item_id else None, qty, found.id if found else None)

    async def open(self, player: Player, item: Item) -> Opened:
        async with self.ctx.db.transaction() as tx:
            return await self._open_one(tx, player.id, item)

    async def open_all(self, player: Player, item: Item | None = None) -> OpenedAll:
        """Open every chest of one kind (or of every kind) the player owns, up to ``OPEN_ALL_LIMIT``, in one go."""
        async with self.ctx.db.transaction() as tx:
            stacks = {i: q for i, q in await inv_repo.stacks(tx, player.id)}
            wanted = [(get_item(i), q) for i, q in stacks.items() if i in CHESTS and (item is None or i == item.id)]
            if not wanted:
                raise GameError("صندوقچه‌ای برای باز کردن ندارید.")
            total = OpenedAll(0, {}, 0, 0, {}, {})
            budget = OPEN_ALL_LIMIT
            for chest_item, qty in sorted(wanted, key=lambda w: w[0].rarity):
                for _ in range(min(qty, budget)):
                    opened = await self._open_one(tx, player.id, chest_item)
                    total.count += 1
                    total.chests[chest_item.id] = total.chests.get(chest_item.id, 0) + 1
                    total.gold += opened.gold
                    total.crystal += opened.crystal
                    if opened.item:
                        total.items[opened.item.id] = total.items.get(opened.item.id, 0) + opened.qty
                    if opened.arm:
                        total.arms[opened.arm] = total.arms.get(opened.arm, 0) + 1
                    budget -= 1
                if budget <= 0:
                    break
            return total
