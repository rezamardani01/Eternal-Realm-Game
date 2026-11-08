"""The card collection: finding cards, the album, duplicates and set-completion rewards."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.cards import (
    CARDS, PACK_PRICE, PACK_SIZE, Card, CardSet, SETS, cards_in, dust_value, get_card, get_set, roll_pack_card,
)
from ..models import Player


@dataclass
class SetProgress:
    set: CardSet
    owned: int
    total: int
    claimed: bool

    @property
    def complete(self) -> bool:
        return self.owned >= self.total


@dataclass
class PackResult:
    cards: list[tuple[Card, bool]]  # (card, was it new?)
    price: int


FEE_PERCENT = 5
MIN_PRICE, MAX_PRICE = 50, 5_000_000


@dataclass
class CardListing:
    id: int
    seller_id: int
    seller: str
    card: Card
    price: int


def _listing(row) -> CardListing:  # noqa: ANN001
    return CardListing(row["id"], row["seller_id"], row["seller"], get_card(row["card_id"]), row["price"])


class CardService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # --- granting -------------------------------------------------------------------------------
    async def grant(self, tx: Tx, player_id: int, card_id: str) -> bool:
        """Add one card. ``True`` when it is new to the player's album."""
        row = await tx.fetchone(
            "SELECT qty FROM player_cards WHERE player_id = ? AND card_id = ?", (player_id, card_id)
        )
        if row is None:
            await tx.execute(
                "INSERT INTO player_cards (player_id, card_id, qty, first_at) VALUES (?, ?, 1, ?)",
                (player_id, card_id, self.ctx.now()),
            )
            return True
        await tx.execute(
            "UPDATE player_cards SET qty = qty + 1 WHERE player_id = ? AND card_id = ?", (player_id, card_id)
        )
        return False

    async def drop_for_monster(self, tx: Tx, player_id: int, monster_id: str, chance: float = 0.08) -> Card | None:
        if self.ctx.rng.random() >= chance:
            return None
        card = get_card(f"mon_{monster_id}")
        await self.grant(tx, player_id, card.id)
        return card

    async def drop_for_boss(self, tx: Tx, player_id: int, element_id: str, chance: float) -> Card | None:
        if self.ctx.rng.random() >= chance:
            return None
        pool = [c for c in CARDS if c.id in (f"dragon_{element_id}",) or c.set_id in ("monsters", "places")]
        card = self.ctx.rng.choice(pool)
        await self.grant(tx, player_id, card.id)
        return card

    # --- the album -----------------------------------------------------------------------------------
    async def owned(self, player_id: int) -> dict[str, int]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT card_id, qty FROM player_cards WHERE player_id = ?", (player_id,))
        return {r["card_id"]: r["qty"] for r in rows}

    async def progress(self, player_id: int) -> list[SetProgress]:
        owned = await self.owned(player_id)
        async with self.ctx.db.read() as tx:
            claimed = {
                r["set_id"] for r in await tx.fetchall(
                    "SELECT set_id FROM card_rewards WHERE player_id = ?", (player_id,)
                )
            }
        out = []
        for s in SETS:
            cards = cards_in(s.id)
            out.append(SetProgress(s, sum(1 for c in cards if c.id in owned), len(cards), s.id in claimed))
        return out

    async def claim_set(self, player: Player, set_id: str) -> CardSet:
        """Reward for completing a set: crystals and a title, once."""
        card_set = get_set(set_id)
        owned = await self.owned(player.id)
        if not all(c.id in owned for c in cards_in(set_id)):
            raise GameError("هنوز همه‌ی کارت‌های این مجموعه را ندارید. آلبوم را ببینید و کارت‌های کم را پیدا کنید!")
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT 1 FROM card_rewards WHERE player_id = ? AND set_id = ?", (player.id, set_id)
            )
            if row is not None:
                raise GameError("پاداش این مجموعه را قبلاً گرفته‌اید.")
            await tx.execute(
                "INSERT INTO card_rewards (player_id, set_id, claimed_at) VALUES (?, ?, ?)",
                (player.id, set_id, self.ctx.now()),
            )
            await wallet.apply(
                tx, player.id, crystal=card_set.crystals, reason=f"card_set:{set_id}", now=self.ctx.now(),
                ref=f"cardset:{set_id}:{player.id}",
            )
            await tx.execute("UPDATE players SET title = ? WHERE id = ?", (card_set.title, player.id))
        return card_set

    # --- spending ------------------------------------------------------------------------------------
    async def buy_pack(self, player: Player) -> PackResult:
        rng = self.ctx.rng
        async with self.ctx.db.transaction() as tx:
            await wallet.apply(tx, player.id, gold=-PACK_PRICE, reason="card_pack", now=self.ctx.now())
            result = []
            for _ in range(PACK_SIZE):
                card = roll_pack_card(rng)
                result.append((card, await self.grant(tx, player.id, card.id)))
            from ...db.repos import season as season_repo

            await season_repo.add_points(tx, player.id, "card_pack", self.ctx.now())
        return PackResult(result, PACK_PRICE)

    async def sell_duplicate(self, player: Player, card_id: str) -> int:
        card = get_card(card_id)
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT qty FROM player_cards WHERE player_id = ? AND card_id = ?", (player.id, card_id)
            )
            if row is None or row["qty"] < 2:
                raise GameError("فقط کارت‌های تکراری را می‌شود فروخت؛ از هر کارت یکی باید در آلبومتان بماند.")
            await tx.execute(
                "UPDATE player_cards SET qty = qty - 1 WHERE player_id = ? AND card_id = ?", (player.id, card_id)
            )
            await wallet.apply(tx, player.id, gold=dust_value(card), reason="card_dust", now=self.ctx.now())
        return dust_value(card)

    async def market_page(self, rarity: int, page: int, per: int) -> tuple[list[CardListing], bool]:
        where, args = "l.status = 'active'", []
        ids = [c.id for c in CARDS if rarity == 0 or c.rarity == rarity]
        where += " AND l.card_id IN (" + ",".join("?" * len(ids)) + ")"
        args += ids
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT l.*, p.display_name AS seller FROM card_listings l JOIN players p ON p.id = l.seller_id"  # noqa: S608
                f" WHERE {where} ORDER BY l.price, l.id LIMIT ? OFFSET ?",
                (*args, per + 1, page * per),
            )
        return [_listing(r) for r in rows[:per]], len(rows) > per


    async def my_listings(self, player_id: int) -> list[CardListing]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT l.*, p.display_name AS seller FROM card_listings l JOIN players p ON p.id = l.seller_id"
                " WHERE l.seller_id = ? AND l.status = 'active' ORDER BY l.id DESC",
                (player_id,),
            )
        return [_listing(r) for r in rows]


    async def listing(self, listing_id: int) -> CardListing | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone(
                "SELECT l.*, p.display_name AS seller FROM card_listings l JOIN players p ON p.id = l.seller_id"
                " WHERE l.id = ? AND l.status = 'active'",
                (listing_id,),
            )
        return _listing(row) if row else None


    async def list_card(self, player: Player, card_id: str, price: int) -> CardListing:
        card = get_card(card_id)
        if not MIN_PRICE <= price <= MAX_PRICE:
            raise GameError(f"قیمت کارت باید بین {fa(MIN_PRICE)} تا {fa(MAX_PRICE)} سکه باشد.")
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT qty FROM player_cards WHERE player_id = ? AND card_id = ?", (player.id, card_id)
            )
            if row is None or row["qty"] < 2:
                raise GameError("فقط کارت‌های تکراری را می‌شود برای فروش گذاشت؛ یک نسخه همیشه در آلبومتان می‌ماند.")
            await tx.execute(
                "UPDATE player_cards SET qty = qty - 1 WHERE player_id = ? AND card_id = ?", (player.id, card_id)
            )
            listing_id = await tx.execute(
                "INSERT INTO card_listings (seller_id, card_id, price, status, created_at) VALUES (?, ?, ?, 'active', ?)",
                (player.id, card_id, price, self.ctx.now()),
            )
        return CardListing(listing_id, player.id, player.name, card, price)


    async def buy_card(self, buyer: Player, listing_id: int) -> CardListing:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT l.*, p.display_name AS seller FROM card_listings l JOIN players p ON p.id = l.seller_id"
                " WHERE l.id = ?",
                (listing_id,),
            )
            if row is None or row["status"] != "active":
                raise GameError("این کارت دیگر برای فروش نیست؛ شاید کسی زودتر خریده یا فروشنده پس گرفته است.")
            if row["seller_id"] == buyer.id:
                raise GameError("این کارت خودتان است! برای پس‌گرفتنش از «آگهی‌های من» استفاده کنید.")
            await tx.execute(
                "UPDATE card_listings SET status = 'sold', buyer_id = ? WHERE id = ? AND status = 'active'",
                (buyer.id, listing_id),
            )
            fee = row["price"] * FEE_PERCENT // 100
            await wallet.apply(tx, buyer.id, gold=-row["price"], reason="card_buy", now=now)
            await wallet.apply(tx, row["seller_id"], gold=row["price"] - fee, reason="card_sale", now=now)
            await self.grant(tx, buyer.id, row["card_id"])
        return _listing(row)


    async def cancel_listing(self, player: Player, listing_id: int) -> CardListing:
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT l.*, p.display_name AS seller FROM card_listings l JOIN players p ON p.id = l.seller_id"
                " WHERE l.id = ?",
                (listing_id,),
            )
            if row is None or row["status"] != "active" or row["seller_id"] != player.id:
                raise GameError("این آگهی را نمی‌شود لغو کرد.")
            await tx.execute("UPDATE card_listings SET status = 'cancelled' WHERE id = ?", (listing_id,))
            await self.grant(tx, player.id, row["card_id"])
        return _listing(row)


__all__ = ["CardService", "PackResult", "SetProgress", "fa"]
