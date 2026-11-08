"""Random happenings the bot creates in active groups by itself.

Events live in the database (kind, JSON state, expiry). One central ``tick`` decides when a group is
due for something new, so nothing needs a task per group.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import events as repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.items import get_item
from ..models import Player
from .bosses import BossService, BossView
from .inventory import InventoryService

KINDS = ("mystery_chest", "merchant", "double_xp", "hidden_boss")
WEIGHTS = (35, 25, 20, 20)
LIFETIME = {"mystery_chest": 180, "merchant": 600, "double_xp": 1800}
TRY_GAP = 20
CHEST_ODDS = (("wooden_chest", 70), ("magic_chest", 27), ("royal_chest", 3))
#: (item, price in gold) the travelling merchant may carry
MERCHANT_STOCK = (
    ("energy_potion", 80), ("big_energy_potion", 260), ("iron_sword", 600), ("iron_shield", 560),
    ("chain_mail", 1_800), ("swift_boots", 1_500), ("strength_ring", 1_900), ("luck_ring", 1_900),
    ("life_amulet", 2_000), ("wooden_chest", 400), ("crystal_shard", 150), ("dragon_scale", 900),
)


@dataclass
class EventView:
    id: int
    chat_id: int
    message_id: int | None
    kind: str
    status: str
    expires_at: int
    now: int
    state: dict[str, Any] = field(default_factory=dict)
    boss: BossView | None = None

    @property
    def seconds_left(self) -> int:
        return max(0, self.expires_at - self.now)


@dataclass
class EventAction:
    #: spawned | ended
    what: str
    view: EventView


class EventService:
    def __init__(
        self, ctx: AppContext, inventory: InventoryService, bosses: BossService
    ) -> None:
        self.ctx = ctx
        self.inventory = inventory
        self.bosses = bosses

    def _view(self, row: Row, boss: BossView | None = None) -> EventView:
        return EventView(
            row["id"], row["chat_id"], row["message_id"], row["kind"], row["status"], row["expires_at"],
            self.ctx.now(), json.loads(row["state"] or "{}"), boss,
        )

    async def get(self, event_id: int) -> EventView | None:
        async with self.ctx.db.read() as tx:
            row = await repo.get(tx, event_id)
        return self._view(row) if row else None

    async def active(self, chat_id: int) -> list[EventView]:
        async with self.ctx.db.read() as tx:
            return [self._view(r) for r in await repo.active_in_chat(tx, chat_id, self.ctx.now())]

    async def attach_message(self, event_id: int, message_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await repo.set_message(tx, event_id, message_id)

    # --- creating events ------------------------------------------------------------------------
    async def spawn(self, chat_id: int, kind: str | None = None) -> EventView | None:
        """Start an event in a group. ``None`` when the group is busy or the event cannot happen."""
        rng, now = self.ctx.rng, self.ctx.now()
        kind = kind or rng.choices(KINDS, weights=WEIGHTS, k=1)[0]
        if kind == "hidden_boss":
            try:
                boss = await self.bosses.summon_event(chat_id)
            except GameError:
                return None
            return EventView(0, chat_id, None, kind, "active", boss.recruit_until, now, {}, boss)
        async with self.ctx.db.transaction() as tx:
            if await repo.active_in_chat(tx, chat_id, now):
                return None
            state: dict[str, Any] = {}
            if kind == "mystery_chest":
                state = {"tries": {}, "attempts": 0}
            elif kind == "merchant":
                picks = rng.sample(MERCHANT_STOCK, 3)
                state = {"stock": [{"item": i, "price": round(p * rng.uniform(0.6, 0.85)), "left": rng.randint(2, 3)}
                                   for i, p in picks]}
            event_id = await repo.create(tx, chat_id, kind, json.dumps(state), now, now + LIFETIME[kind])
            row = await repo.get(tx, event_id)
            assert row is not None
            return self._view(row)

    async def tick(self) -> list[EventAction]:
        """Close lapsed events and start new ones in groups that are due. Call every ~30 seconds."""
        b, now, rng = self.ctx.balance, self.ctx.now(), self.ctx.rng
        actions: list[EventAction] = []
        async with self.ctx.db.transaction() as tx:
            for row in await repo.lapsed(tx, now):
                status = "done" if row["kind"] == "double_xp" else "expired"
                if await repo.finish(tx, row["id"], status):
                    fresh = await repo.get(tx, row["id"])
                    assert fresh is not None
                    actions.append(EventAction("ended", self._view(fresh)))
            due = [r["chat_id"] for r in await repo.due_groups(tx, now)]
        for chat_id in due:
            async with self.ctx.db.transaction() as tx:
                busy = await repo.active_members(tx, chat_id, now - 86400) < b.event_min_active
                delay = 1800 if busy else int(b.event_interval_seconds * rng.uniform(0.7, 1.3))
                await repo.schedule(tx, chat_id, now + delay)
            if busy:
                continue
            view = await self.spawn(chat_id)
            if view is not None:
                actions.append(EventAction("spawned", view))
        return actions

    # --- playing events -------------------------------------------------------------------------
    async def _live(self, tx: Tx, event_id: int, kind: str) -> Row:
        row = await repo.get(tx, event_id)
        if row is None or row["kind"] != kind or row["status"] != "active" or row["expires_at"] <= self.ctx.now():
            raise GameError("⌛ این رویداد تمام شده است.")
        return row

    async def try_open(self, event_id: int, player: Player) -> tuple[EventView, bool]:
        """One attempt at the mystery chest's lock. The more people try, the likelier it opens."""
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await self._live(tx, event_id, "mystery_chest")
            state = json.loads(row["state"])
            wait = state["tries"].get(str(player.id), 0) + TRY_GAP - now
            if wait > 0:
                raise GameError(f"⏳ دست‌هایتان از تلاش قبلی هنوز می‌لرزد! {wait} ثانیه دیگر دوباره امتحان کنید.")
            state["attempts"] += 1
            state["tries"][str(player.id)] = now
            success = rng.random() < min(0.6, 0.06 + 0.035 * state["attempts"])
            if success and await repo.finish(tx, event_id, "done"):
                chest = rng.choices([c for c, _ in CHEST_ODDS], weights=[w for _, w in CHEST_ODDS], k=1)[0]
                await self.inventory.grant(tx, player.id, chest, 1)
                state["winner"], state["mention"], state["prize"] = player.name, player.mention, chest
            else:
                success = False
            await repo.save_state(tx, event_id, json.dumps(state))
            fresh = await repo.get(tx, event_id)
            assert fresh is not None
            return self._view(fresh), success

    async def buy(self, event_id: int, player: Player, index: int) -> tuple[EventView, str]:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await self._live(tx, event_id, "merchant")
            state = json.loads(row["state"])
            if not 0 <= index < len(state["stock"]):
                raise GameError("این کالا پیش تاجر نیست.")
            entry = state["stock"][index]
            if entry["left"] <= 0:
                raise GameError("😔 این کالا تمام شد؛ یک نفر زودتر خرید.")
            await wallet.apply(tx, player.id, gold=-entry["price"], reason="merchant", now=now)
            await self.inventory.grant(tx, player.id, entry["item"], 1)
            entry["left"] -= 1
            if all(e["left"] <= 0 for e in state["stock"]):
                await repo.finish(tx, event_id, "done")
            await repo.save_state(tx, event_id, json.dumps(state))
            fresh = await repo.get(tx, event_id)
            assert fresh is not None
            return self._view(fresh), get_item(entry["item"]).label
