"""Inviting friends: each friend who joins and creates a hero pays the inviter a few small random prizes.

Also home of the unopened gift boxes the owner can hand out (``اهدا بسته ...``).
"""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.items import get_item
from ..data.lucky import roll, theme_of_day
from ..data.packs import PACKS
from ..models import Player
from .inventory import InventoryService

INVITE_BOOST_HOURS = 12
DAY = 86400
#: how many invitations per day still pay prizes (the friend is counted either way)
DAILY_REWARDS = 10
PRIZES_PER_INVITE = 2

#: (kind, payload, weight): gold is (low, high); items are (item id, quantity). Nothing here is worth much.
PRIZES: tuple[tuple[str, tuple, int], ...] = (
    ("gold", (40, 100), 30),
    ("gold", (100, 200), 10),
    ("crystal", (1, 1), 6),
    ("item", ("energy_potion", 2), 18),
    ("item", ("wooden_chest", 1), 12),
    ("item", ("iron_ore", 5), 16),
    ("item", ("herb", 3), 8),
    ("item", ("moon_herb", 2), 2),
    ("item", ("gold_ore", 2), 2),
)

#: owner gift names -> the pack they hand out
GIFT_PACKS = {
    "کوچک": "lucky_s", "متوسط": "lucky_m", "بزرگ": "lucky_l", "ماجراجو": "adventurer",
}


@dataclass
class InviteResult:
    inviter: Player
    prizes: list[str]
    capped: bool = False


@dataclass
class OpenedBox:
    pack_title: str
    haul: str


class InviteService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    # --- invitations ---------------------------------------------------------------------------------
    def link(self, bot_username: str, platform_user_id: int) -> str:
        return f"https://ble.ir/{bot_username}?start=ref_{platform_user_id}"

    @staticmethod
    def parse(payload: str) -> int | None:
        """The inviter's Bale id out of a «ref_123» start payload."""
        if payload.startswith("ref_") and payload[4:].isdigit():
            return int(payload[4:])
        return None

    async def count(self, player_id: int) -> int:
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (player_id,), 0))

    async def register(self, invited: Player, inviter_platform_id: int) -> InviteResult | None:
        """Count a new hero as invited by someone and pay the inviter. ``None`` when it does not count."""
        now, rng = self.ctx.now(), self.ctx.rng
        if inviter_platform_id == invited.platform_user_id:
            return None
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT id FROM players WHERE platform_user_id = ? AND banned = 0", (inviter_platform_id,))
            if row is None or await tx.fetchone("SELECT 1 FROM referrals WHERE invited_id = ?", (invited.id,)):
                return None
            inviter_id = int(row["id"])
            await tx.execute(
                "INSERT INTO referrals (invited_id, referrer_id, created_at) VALUES (?, ?, ?)", (invited.id, inviter_id, now)
            )
            today = int(await tx.scalar(
                "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND created_at >= ?", (inviter_id, now - DAY), 0
            ))
            from ...db.repos import players as player_repo

            inviter = await player_repo.get(tx, inviter_id)
            assert inviter is not None
            from ..notify import achievement_check

            total = int(await tx.scalar("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (inviter_id,), 0))
            await achievement_check(tx, inviter_id, "invites", total, now)
            if today > DAILY_REWARDS:
                return InviteResult(inviter, [], capped=True)
            prizes = []
            for kind, payload, _ in rng.choices(PRIZES, weights=[w for *_, w in PRIZES], k=PRIZES_PER_INVITE):
                if kind == "gold":
                    amount = rng.randint(*payload)
                    await wallet.apply(tx, inviter_id, gold=amount, reason="invite", now=now)
                    prizes.append(f"🪙 {fa(amount)} سکه")
                elif kind == "crystal":
                    await wallet.apply(tx, inviter_id, crystal=payload[0], reason="invite", now=now)
                    prizes.append(f"💎 {fa(payload[0])} کریستال")
                else:
                    item_id, qty = payload
                    await self.inventory.grant(tx, inviter_id, item_id, qty)
                    prizes.append(f"{get_item(item_id).label}" + (f" ×{fa(qty)}" if qty > 1 else ""))
            await tx.execute(
                "UPDATE players SET boost_until = MAX(boost_until, ?) + ? WHERE id = ?", (now, INVITE_BOOST_HOURS * 3600, inviter_id)
            )
            prizes.append(f"🚀 بوست دو برابر {fa(INVITE_BOOST_HOURS)} ساعته")
            return InviteResult(inviter, prizes)

    # --- gift boxes from the owner ----------------------------------------------------------------------
    async def give_box(self, admin_id: int, player_id: int, pack_id: str) -> int:
        if pack_id not in PACKS:
            raise GameError("این بسته وجود ندارد.")
        async with self.ctx.db.transaction() as tx:
            box_id = await tx.execute(
                "INSERT INTO gift_boxes (player_id, pack_id, created_at) VALUES (?, ?, ?)", (player_id, pack_id, self.ctx.now())
            )
            await tx.execute(
                "INSERT INTO admin_log (admin_id, action, detail, created_at) VALUES (?, 'gift_box', ?, ?)",
                (admin_id, f"player {player_id} {pack_id}", self.ctx.now()),
            )
        return box_id

    async def open_box(self, player: Player, box_id: int) -> OpenedBox:
        """Open a box exactly once, and only by its owner."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM gift_boxes WHERE id = ?", (box_id,))
            if row is None or row["player_id"] != player.id:
                raise GameError("این صندوق مال شما نیست.")
            if row["opened_at"]:
                raise GameError("این صندوق را قبلاً باز کرده‌اید.")
            await tx.execute("UPDATE gift_boxes SET opened_at = ? WHERE id = ?", (now, box_id))
            pack = PACKS[row["pack_id"]]
            gold, crystal, items = pack.gold, pack.crystal, dict(pack.items)
            if pack.lucky:
                haul = roll(pack.id, theme_of_day(now), self.ctx.rng)
                gold, crystal, items = haul.gold, haul.crystal, haul.items
            await wallet.apply(tx, player.id, gold=gold, crystal=crystal, reason=f"gift_box:{pack.id}", now=now, ref=f"gift_box:{box_id}")
            for item_id, qty in items.items():
                await self.inventory.grant(tx, player.id, item_id, qty)
        from .payments import describe_haul

        return OpenedBox(pack.title, describe_haul(gold, crystal, items))
