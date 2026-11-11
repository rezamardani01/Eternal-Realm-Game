"""Thanks to the clan: when a hero buys something with real money, every other member of their clan finds a small gift
box in the private chat. A bigger purchase puts better things in the box, but the box stays small and random.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import clans as clan_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from .. import notify
from ..data.items import get_item
from ..models import Player
from .inventory import InventoryService

#: (what the purchase must reach in rials to belong to the tier, name of the box)
TIERS: tuple[tuple[int, str, str], ...] = (
    (0, "کوچک", "🎁"),
    (100_000, "متوسط", "📦"),
    (300_000, "بزرگ", "🎀"),
    (700_000, "سلطنتی", "👑"),
)
#: a member receives at most this many boxes a day, whoever buys
DAILY_BOXES = 3

#: per tier: (draws, [(item, low, high, weight)], gold range, crystal chance)
LOOT: tuple[tuple[tuple[int, int], tuple[tuple[str, int, int, int], ...], tuple[int, int], float], ...] = (
    ((1, 2), (("small_energy_potion", 1, 2, 10), ("herb", 2, 4, 10), ("stone", 3, 6, 10), ("iron_ore", 1, 3, 8), ("small_fish", 2, 4, 6)), (30, 90), 0.0),
    ((2, 2), (("energy_potion", 1, 1, 10), ("iron_ore", 3, 6, 10), ("herb", 3, 6, 8), ("moon_herb", 1, 2, 6), ("monster_fang", 1, 2, 6), ("stone", 5, 9, 6)), (80, 220), 0.0),
    ((2, 3), (("big_energy_potion", 1, 1, 8), ("iron_ore", 5, 9, 10), ("moon_herb", 2, 3, 8), ("crystal_shard", 1, 1, 6), ("monster_fang", 2, 4, 6), ("wooden_chest", 1, 1, 6), ("gold_ore", 1, 3, 5)), (200, 520), 0.25),
    ((3, 3), (("big_energy_potion", 1, 2, 8), ("iron_ore", 8, 14, 8), ("crystal_shard", 1, 2, 8), ("gold_ore", 2, 4, 6), ("wooden_chest", 1, 1, 8), ("magic_chest", 1, 1, 3), ("dragon_scale", 1, 1, 2)), (450, 1_000), 0.6),
)


def tier_of(amount: int) -> int:
    """0..3 from what the purchase cost (in rials)."""
    return max(i for i, (floor, _, _) in enumerate(TIERS) if amount >= floor)


@dataclass
class OpenedGift:
    tier: int
    buyer: str
    gold: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)


class ClanGiftService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    # --- a purchase was paid: leave a box for every clan-mate --------------------------------------------
    async def thank_clan(self, tx: Tx, buyer: Player, amount: int, now: int) -> int:
        """Called inside the transaction that delivers a paid order. Returns how many boxes were left."""
        member = await clan_repo.membership(tx, buyer.id)
        if member is None:
            return 0
        clan = await clan_repo.get(tx, member["clan_id"])
        if clan is None:
            return 0
        tier = tier_of(amount)
        _, name, icon = TIERS[tier]
        left = 0
        day = (now + 12600) // 86400
        for mate in await clan_repo.members(tx, member["clan_id"]):
            if mate["player_id"] == buyer.id:
                continue
            today = int(await tx.scalar(
                "SELECT COUNT(*) FROM clan_gift_boxes WHERE player_id = ? AND created_at >= ?", (mate["player_id"], day * 86400 - 12600), 0
            ))
            if today >= DAILY_BOXES:
                continue
            box_id = await tx.execute(
                "INSERT INTO clan_gift_boxes (player_id, from_id, from_name, clan_name, tier, status, created_at) VALUES (?, ?, ?, ?, ?, 'new', ?)",
                (mate["player_id"], buyer.id, buyer.name, clan["name"], tier, now),
            )
            await notify.queue(
                tx, mate["player_id"], f"clangift:{box_id}",
                f"💝 *هدیه‌ای از خاندانتان رسید!*\n\n"
                f"🏯 {buyer.name}، از اعضای خاندان «{clan['name']}»، از خزانه‌ی قلمرو خرید کرد.\n"
                f"به پاس قدردانی از خاندان شما، یک {icon} «هدیه‌ی {name}» برای شما کنار گذاشته شد.\n\n"
                "👇 دکمه‌ی زیر را بزنید و بازش کنید",
                now, "cgopen", str(box_id),
            )
            left += 1
        return left

    # --- the hero opens one ------------------------------------------------------------------------------------
    async def open(self, player: Player, box_id: int) -> OpenedGift:
        now, rng = self.ctx.now(), self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM clan_gift_boxes WHERE id = ? AND player_id = ?", (box_id, player.id))
            if row is None:
                raise GameError("این هدیه برای شما نیست.")
            if row["status"] != "new":
                raise GameError("این هدیه را قبلاً باز کرده‌اید.")
            await tx.execute("UPDATE clan_gift_boxes SET status = 'opened' WHERE id = ?", (box_id,))
            draws, table, gold_range, crystal_chance = LOOT[row["tier"]]
            opened = OpenedGift(row["tier"], row["from_name"])
            for _ in range(rng.randint(*draws)):
                item_id, low, high, _ = rng.choices(table, weights=[t[3] for t in table], k=1)[0]
                opened.items[item_id] = opened.items.get(item_id, 0) + rng.randint(low, high)
            opened.gold = rng.randint(*gold_range)
            if rng.random() < crystal_chance:
                opened.crystal = 1 + (1 if row["tier"] == 3 and rng.random() < 0.4 else 0)
            await wallet.apply(tx, player.id, gold=opened.gold, crystal=opened.crystal, reason="clan_gift", now=now, ref=f"clangift:{box_id}")
            for item_id, qty in opened.items.items():
                await self.inventory.grant(tx, player.id, item_id, qty, origin="clan_gift")
            return opened

    async def waiting(self, player_id: int) -> int:
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT COUNT(*) FROM clan_gift_boxes WHERE player_id = ? AND status = 'new'", (player_id,), 0))

    @staticmethod
    def describe(opened: OpenedGift) -> list[str]:
        lines = []
        if opened.gold:
            lines.append(f"🪙 {fa(opened.gold)} سکه")
        if opened.crystal:
            lines.append(f"💎 {fa(opened.crystal)} کریستال")
        lines += [f"{get_item(i).emoji} {get_item(i).name} ×{fa(q)}" for i, q in opened.items.items()]
        return lines
