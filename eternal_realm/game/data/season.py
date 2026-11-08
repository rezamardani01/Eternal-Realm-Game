"""The hero-path ticket: 100 tiers per season, a free track for everyone and a ticket track.

Rewards are computed from the tier number, so changing the table is a matter of editing
:func:`reward_for`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEASON_DAYS = 45
SEASON_SECONDS = SEASON_DAYS * 86400
TIERS = 100
POINTS_PER_TIER = 100
TICKET_PACK = "season_ticket"
TEHRAN = 12600

#: how many path points each kind of deed gives
POINTS = {
    "activity": 5, "hunt": 8, "daily": 10, "duel_win": 15, "duel": 5, "boss": 30, "boss_win": 20,
    "quest": 40, "mission": 20, "dungeon": 25, "dungeon_win": 25, "card_pack": 10,
}


@dataclass(frozen=True)
class TierReward:
    gold: int = 0
    crystal: int = 0
    items: tuple[tuple[str, int], ...] = ()
    title: str = ""
    #: collectible cards given with the tier
    cards: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.gold or self.crystal or self.items or self.title or self.cards)

    def lines(self) -> list[str]:
        from .items import get_item

        out = []
        if self.gold:
            out.append(f"🪙 {self.gold:,} سکه".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))
        if self.crystal:
            out.append(f"💎 {self.crystal} کریستال".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))
        for item_id, qty in self.items:
            out.append(f"{get_item(item_id).label} ×{qty}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))
        for card_id in self.cards:
            from .cards import get_card

            card = get_card(card_id)
            out.append(f"🃏 کارت {card.name}")
        if self.title:
            out.append(f"🏅 عنوان «{self.title}»")
        return out


def season_of(now: int) -> int:
    return (now + TEHRAN) // SEASON_SECONDS


def season_seconds_left(now: int) -> int:
    return (season_of(now) + 1) * SEASON_SECONDS - (now + TEHRAN)


def reward_for(track: str, tier: int) -> TierReward:
    """What a tier gives on the ``free`` or the ``ticket`` track."""
    if track == "free":
        gold = 20 + 3 * tier
        crystal = 2 if tier % 10 == 5 else 0
        items: tuple[tuple[str, int], ...] = ()
        if tier % 20 == 0:
            items = (("wooden_chest", 1),)
        if tier % 7 == 0:
            items += (("energy_potion", 2),)
        title = "قهرمان فصل" if tier == TIERS else ""
        if tier % 10 == 0 and tier != TIERS:
            gold += 200
        cards = (_card_for(tier, 2),) if tier % 15 == 0 else ()
        return TierReward(gold, crystal, items, title, cards)
    gold = 95 + 15 * tier
    crystal = 5 if tier % 5 == 0 else 0
    items = ()
    if tier % 10 == 0:
        items = (("magic_chest", 1),)
    if tier % 25 == 0:
        items += (("dragon_scale", 2),)
    if tier == TIERS:
        items = (("royal_chest", 1), ("magic_chest", 2))
        crystal = 30
    title = "اسطوره‌ی فصل" if tier == TIERS else ""
    cards = (_card_for(tier, 4),) if tier % 4 == 0 else ()
    return TierReward(gold, crystal, items, title, cards)


def _card_for(tier: int, max_rarity: int) -> str:
    """A collectible card for the tier, never repeating inside one run of the path."""
    from .cards import CARDS

    pool = sorted(c.id for c in CARDS if c.rarity <= max_rarity)
    return pool[(tier * 7) % len(pool)]


@dataclass
class PathState:
    season: int
    points: int
    premium: bool
    claimed: set[tuple[str, int]] = field(default_factory=set)

    @property
    def tier(self) -> int:
        return min(TIERS, self.points // POINTS_PER_TIER)

    def available(self) -> list[tuple[str, int]]:
        out = []
        for tier in range(1, self.tier + 1):
            for track in ("free", "ticket"):
                if (track, tier) in self.claimed or (track == "ticket" and not self.premium):
                    continue
                if reward_for(track, tier):
                    out.append((track, tier))
        return out
