"""Pop-up happenings: the bot starts one in a hero's private chat now and then; the hero has a few hours to decide."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from .. import notify
from ..data import popups as data
from ..engine import loot
from ..models import Player
from .inventory import InventoryService
from .players import PlayerService


@dataclass
class OpenPopup:
    id: int
    popup: data.Popup
    seconds_left: int


@dataclass
class PopupResult:
    popup: data.Popup
    lines: list[str]
    gold: int = 0
    xp: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)


class PopupService:
    def __init__(self, ctx: AppContext, players: PlayerService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory

    # --- the bot starts one ---------------------------------------------------------------------------
    async def spawn_due(self, chance: float = 0.04) -> int:
        """Start a happening for some of the heroes who are around. Call every few minutes; returns how many were started."""
        now, rng = self.ctx.now(), self.ctx.rng
        hour = ((now + 12600) % 86400) // 3600
        if not data.HOURS[0] <= hour < data.HOURS[1]:
            return 0
        started = 0
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT id FROM players WHERE banned = 0 AND offers_off = 0 AND level >= ? AND energy_at >= ?"
                " AND NOT EXISTS (SELECT 1 FROM popups q WHERE q.player_id = players.id AND q.created_at > ?)"
                " ORDER BY RANDOM() LIMIT ?",
                (data.MIN_LEVEL, now - 2 * 86400, now - data.GAP_HOURS * 3600, data.MAX_PER_SWEEP),
            )
            for r in rows:
                if rng.random() >= chance:
                    continue
                popup = rng.choices(data.POPUPS, weights=[p.weight for p in data.POPUPS], k=1)[0]
                popup_id = await tx.execute(
                    "INSERT INTO popups (player_id, kind, status, created_at, expires_at) VALUES (?, ?, 'open', ?, ?)",
                    (r["id"], popup.id, now, now + popup.ttl_hours * 3600),
                )
                await notify.queue(
                    tx, r["id"], f"popup:{popup_id}",
                    f"{popup.emoji} *{popup.title}*\n\n{popup.text}\n\n⏳ فرصت: {popup.ttl_hours} ساعت", now, "popup", str(popup_id),
                )
                started += 1
        return started

    async def start_for(self, player: Player, kind: str) -> int:
        """Start a given happening for a hero (the owner's tool and the tests)."""
        popup = data.get_popup(kind)
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            return await tx.execute(
                "INSERT INTO popups (player_id, kind, status, created_at, expires_at) VALUES (?, ?, 'open', ?, ?)",
                (player.id, popup.id, now, now + popup.ttl_hours * 3600),
            )

    # --- the hero decides ----------------------------------------------------------------------------------
    async def get(self, player: Player, popup_id: int) -> OpenPopup | None:
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone(
                "SELECT * FROM popups WHERE id = ? AND player_id = ? AND status = 'open' AND expires_at > ?", (popup_id, player.id, now)
            )
        return OpenPopup(row["id"], data.get_popup(row["kind"]), row["expires_at"] - now) if row else None

    async def latest(self, player: Player) -> OpenPopup | None:
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone(
                "SELECT id FROM popups WHERE player_id = ? AND status = 'open' AND expires_at > ? ORDER BY id DESC LIMIT 1", (player.id, now)
            )
        return await self.get(player, row["id"]) if row else None

    async def choose(self, player: Player, popup_id: int, index: int) -> PopupResult:
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM popups WHERE id = ? AND player_id = ?", (popup_id, player.id))
            if row is None:
                raise GameError("این اتفاق برای شما نیست.")
            if row["status"] != "open":
                raise GameError("درباره‌ی این اتفاق قبلاً تصمیم گرفته‌اید.")
            if row["expires_at"] <= now:
                await tx.execute("UPDATE popups SET status = 'expired' WHERE id = ?", (popup_id,))
                return PopupResult(data.get_popup(row["kind"]), ["⌛ فرصتتان تمام شد و این اتفاق گذشت."])
            popup = data.get_popup(row["kind"])
            if not 0 <= index < len(popup.choices):
                raise GameError("این گزینه نیست.")
            await tx.execute("UPDATE popups SET status = 'done' WHERE id = ?", (popup_id,))
            result = dict(popup.choices[index].result)
            lines: list[str] = []
            if "pay" in result:
                await wallet.apply(tx, player.id, gold=-result["pay"], reason="popup", now=now)
                lines.append(f"🪙 {result['pay']} سکه پرداختید.".translate(_FA))
            while "chance" in result:
                result = result["win"] if rng.random() < result["chance"] else result["lose"]
            gold = round(rng.randint(*result["gold"]) * data.SHARE * loot.level_scale(player.level)) if "gold" in result else 0
            xp = round(rng.randint(*result["xp"]) * data.SHARE * loot.xp_scale(player.level)) if "xp" in result else 0
            items = {result["item"][0]: result["item"][1]} if "item" in result else {}
            crystal = result.get("crystal", 0)
            if gold or crystal:
                await wallet.apply(tx, player.id, gold=gold, crystal=crystal, reason="popup", now=now)
            for item_id, qty in items.items():
                await self.inventory.grant(tx, player.id, item_id, qty, origin="popup")
            if xp:
                await self.players.grant_xp(tx, player.id, xp)
            lines.insert(0, result.get("text", "ماجرا گذشت."))
            return PopupResult(popup, lines, gold, xp, crystal, items)


_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
