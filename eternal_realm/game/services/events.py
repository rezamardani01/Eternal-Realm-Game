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
from ..data.world_events import ARMIES, METEOR_LOOT, METEOR_PER_PLAYER, METEOR_PIECES, PLACES, REGIONS
from ..models import Player
from .bosses import BossService, BossView
from .inventory import InventoryService

KINDS = ("mystery_chest", "merchant", "double_xp", "hidden_boss", "hidden_chest", "invasion", "meteor")
WEIGHTS = (30, 18, 16, 10, 12, 8, 8)
LIFETIME = {
    "mystery_chest": 300, "merchant": 600, "double_xp": 1800, "hidden_chest": 900, "invasion": 900, "meteor": 600,
}
TRY_GAP = 20
SEARCH_GAP = 20
DEFEND_GAP = 25
COLLECT_GAP = 15
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
            elif kind == "hidden_chest":
                state = self._new_hidden_chest()
            elif kind == "invasion":
                state = await self._new_invasion(tx, chat_id, now)
            elif kind == "meteor":
                state = {"region": rng.choice(REGIONS), "left": METEOR_PIECES, "taken": {}, "names": {}, "at": {}}
            elif kind == "merchant":
                picks = rng.sample(MERCHANT_STOCK, 3)
                state = {"stock": [{"item": i, "price": round(p * rng.uniform(0.6, 0.85)), "left": rng.randint(2, 3)}
                                   for i, p in picks]}
            event_id = await repo.create(tx, chat_id, kind, json.dumps(state), now, now + LIFETIME[kind])
            row = await repo.get(tx, event_id)
            assert row is not None
            return self._view(row)

    def _new_hidden_chest(self) -> dict[str, Any]:
        rng = self.ctx.rng
        spots = rng.sample(PLACES, 5)
        target = rng.choice(spots)
        return {"places": [p.id for p in spots], "target": target.id, "clue": target.clue, "tried": {}, "at": {}}

    async def _new_invasion(self, tx: Tx, chat_id: int, now: int) -> dict[str, Any]:
        rng = self.ctx.rng
        row = await tx.fetchone(
            "SELECT COUNT(*) AS n, AVG(p.level) AS lvl FROM group_members m JOIN players p ON p.id = m.player_id"
            " WHERE m.chat_id = ? AND m.last_active >= ?", (chat_id, now - 86400),
        )
        members, level = max(2, int(row["n"] or 0)), max(1.0, float(row["lvl"] or 1))
        army, cry = rng.choice(ARMIES)
        hp = round(max(1_500, 700 * members) * (1 + level / 25))
        return {"army": army, "cry": cry, "hp": hp, "max_hp": hp, "hits": {}, "names": {}, "at": {}, "level": round(level)}

    # --- hidden chest: find the place the clue points at -----------------------------------------
    async def search(self, event_id: int, player: Player, place_id: str) -> tuple[EventView, str]:
        """Search one place. Returns the new view and ``found`` / ``empty``."""
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await self._live(tx, event_id, "hidden_chest")
            state = json.loads(row["state"])
            if place_id not in state["places"] or place_id in state["tried"]:
                raise GameError("اینجا را قبلاً گشته‌اند.")
            wait = state["at"].get(str(player.id), 0) + SEARCH_GAP - now
            if wait > 0:
                raise GameError(f"⏳ هنوز خسته‌اید! {wait} ثانیه دیگر دوباره بگردید.")
            state["at"][str(player.id)] = now
            if place_id == state["target"] and await repo.finish(tx, event_id, "done"):
                chest = rng.choices([c for c, _ in CHEST_ODDS], weights=[w for _, w in CHEST_ODDS], k=1)[0]
                await self.inventory.grant(tx, player.id, chest, 1)
                await wallet.apply(tx, player.id, gold=150, reason="hidden_chest", now=now)
                state["winner"], state["mention"], state["prize"] = player.name, player.mention, chest
                outcome = "found"
            else:
                state["tried"][place_id] = player.mention
                outcome = "empty"
            await repo.save_state(tx, event_id, json.dumps(state))
            fresh = await repo.get(tx, event_id)
            assert fresh is not None
            return self._view(fresh), outcome

    # --- invasion: everybody hits the same army -------------------------------------------------
    async def defend(self, event_id: int, player: Player) -> tuple[EventView, int, bool]:
        """One blow against the invaders. Returns the view, the damage and whether it was the last blow."""
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await self._live(tx, event_id, "invasion")
            state = json.loads(row["state"])
            wait = state["at"].get(str(player.id), 0) + DEFEND_GAP - now
            if wait > 0:
                raise GameError(f"⏳ شمشیرتان هنوز داغ است! {wait} ثانیه دیگر دوباره بزنید.")
            stats = await self.bosses.characters.stats_in(tx, player)
            damage = max(25, round((stats.atk + 0.6 * stats.magic) * rng.uniform(1.2, 1.8)) + 20)
            key = str(player.id)
            state["at"][key] = now
            state["hits"][key] = state["hits"].get(key, 0) + damage
            state["names"][key] = player.mention
            state["hp"] = max(0, state["hp"] - damage)
            final = state["hp"] == 0 and await repo.finish(tx, event_id, "done")
            if final:
                state["payouts"] = await self._pay_invasion(tx, event_id, state, won=True, now=now)
            await repo.save_state(tx, event_id, json.dumps(state))
            fresh = await repo.get(tx, event_id)
            assert fresh is not None
            return self._view(fresh), damage, bool(final)

    async def _pay_invasion(self, tx: Tx, event_id: int, state: dict[str, Any], won: bool, now: int) -> list[dict[str, Any]]:
        factor = 1.0 if won else 0.3
        hits: dict[str, int] = state["hits"]
        total = sum(hits.values()) or 1
        level = state.get("level", 1)
        pool = round((600 + 80 * level) * factor)
        paid: list[dict[str, Any]] = []
        for index, (pid, damage) in enumerate(sorted(hits.items(), key=lambda kv: -kv[1])):
            share = damage / total
            gold = max(round(60 * factor), round(pool * share))
            xp = round((50 + 8 * level) * (0.5 + share) * factor)
            await wallet.apply(tx, int(pid), gold=gold, reason="invasion", now=now, ref=f"invasion:{event_id}:{pid}")
            await self.bosses.players.grant_xp(tx, int(pid), xp)
            chest = ""
            if won:
                chest = "magic_chest" if index == 0 else "wooden_chest" if share >= 0.12 else ""
                if chest:
                    await self.inventory.grant(tx, int(pid), chest, 1)
            paid.append({"mention": state["names"][pid], "damage": damage, "gold": gold, "xp": xp, "chest": chest})
        return paid

    # --- meteor: a limited heap of rare pieces, first come first served ----------------------------
    async def collect(self, event_id: int, player: Player) -> tuple[EventView, str]:
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await self._live(tx, event_id, "meteor")
            state = json.loads(row["state"])
            key = str(player.id)
            if state["left"] <= 0:
                raise GameError("☄️ همه‌ی تکه‌ها برداشته شد.")
            if state["taken"].get(key, 0) >= METEOR_PER_PLAYER:
                raise GameError(f"هر نفر حداکثر {METEOR_PER_PLAYER} تکه می‌تواند بردارد؛ بقیه را برای دیگران بگذارید.")
            wait = state["at"].get(key, 0) + COLLECT_GAP - now
            if wait > 0:
                raise GameError(f"⏳ {wait} ثانیه دیگر دوباره بردارید.")
            item = rng.choices([i for i, _ in METEOR_LOOT], weights=[w for _, w in METEOR_LOOT], k=1)[0]
            await self.inventory.grant(tx, player.id, item, 1)
            state["left"] -= 1
            state["taken"][key] = state["taken"].get(key, 0) + 1
            state["names"][key] = player.mention
            state["at"][key] = now
            if state["left"] == 0:
                await repo.finish(tx, event_id, "done")
            await repo.save_state(tx, event_id, json.dumps(state))
            fresh = await repo.get(tx, event_id)
            assert fresh is not None
            return self._view(fresh), item

    async def hunters(self, chat_id: int, min_level: int, limit: int = 30) -> list[int]:
        """Players of this group who could join a boss now and have not switched personal messages off."""
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT p.platform_user_id AS uid FROM group_members m JOIN players p ON p.id = m.player_id"
                " WHERE m.chat_id = ? AND m.last_active >= ? AND p.level >= ? AND p.banned = 0 AND p.offers_off = 0"
                " ORDER BY m.last_active DESC LIMIT ?", (chat_id, now - 7 * 86400, min_level, limit),
            )
        return [int(r["uid"]) for r in rows]

    async def tick(self) -> list[EventAction]:
        """Close lapsed events and start new ones in groups that are due. Call every ~30 seconds."""
        b, now, rng = self.ctx.balance, self.ctx.now(), self.ctx.rng
        actions: list[EventAction] = []
        async with self.ctx.db.transaction() as tx:
            for row in await repo.lapsed(tx, now):
                status = "done" if row["kind"] == "double_xp" else "expired"
                if await repo.finish(tx, row["id"], status):
                    if row["kind"] == "invasion":
                        state = json.loads(row["state"] or "{}")
                        state["payouts"] = await self._pay_invasion(tx, row["id"], state, won=False, now=now)
                        await repo.save_state(tx, row["id"], json.dumps(state))
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
