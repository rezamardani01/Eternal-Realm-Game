"""Collectible cards: heroes, monsters, dragons, places and legends. Cards never change combat strength."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .bosses import ELEMENTS
from .classes import CLASSES
from .monsters import MONSTERS

RARITY_NAMES = {1: "⚪ معمولی", 2: "🟢 غیرمعمول", 3: "🔵 کمیاب", 4: "🟣 حماسی", 5: "🟠 افسانه‌ای", 6: "🔴 اسطوره‌ای"}
#: chance of each rarity in a card pack (shown to players)
PACK_ODDS = {1: 40, 2: 28, 3: 18, 4: 9, 5: 4, 6: 1}
PACK_SIZE = 5
PACK_PRICE = 1500


@dataclass(frozen=True)
class Card:
    id: str
    set_id: str
    emoji: str
    name: str
    rarity: int
    story: str


@dataclass(frozen=True)
class CardSet:
    id: str
    emoji: str
    name: str
    #: title given for completing the set, and the crystals that come with it
    title: str
    crystals: int


SETS: tuple[CardSet, ...] = (
    CardSet("heroes", "🛡️", "قهرمانان", "قهرمان‌شناس", 5),
    CardSet("monsters", "👹", "هیولاها", "شکارچی کهنه‌کار", 5),
    CardSet("dragons", "🐉", "اژدهایان", "اژدهاشناس", 12),
    CardSet("places", "🗺️", "مکان‌ها", "جهان‌گرد", 6),
    CardSet("legends", "📜", "افسانه‌ها", "اسطوره‌شناس", 15),
)

_HERO_STORY = {
    "warrior": "پیشانی‌اش جای زخم هزار نبرد است و شمشیرش هرگز پشت سنگر نمی‌ماند.",
    "mage": "کتاب‌های کهنه را از بر است و آتش و یخ فرمانبردار انگشتانش هستند.",
    "rogue": "سایه‌ها را می‌شناسد؛ تا چشم برهم بزنید پشت سرتان ایستاده است.",
    "archer": "تیرش پیش از صدای کمان به هدف می‌نشیند.",
    "guardian": "سپرش دیواری است که هیچ هیولایی از آن نگذشته.",
}
_PLACES = (
    ("forest", "🌲", "جنگل نفرین‌شده", 2, "درخت‌های این جنگل شب‌ها زمزمه می‌کنند و مسافران را به راه‌های گمشده می‌کشانند."),
    ("castle", "🏰", "قلعه‌ی تاریکی", 3, "برج‌های سیاهش از دور دیده می‌شود، اما هیچ‌کس به یاد ندارد که چه کسی ساخته‌اش."),
    ("lake", "🌊", "دریاچه‌ی آینه", 2, "آب این دریاچه آنقدر ساکن است که آسمان را دو برابر نشان می‌دهد."),
    ("mine", "⛏️", "معدن فراموش‌شده", 3, "تونل‌هایش تا دل زمین می‌رود و گنج و خطر را با هم نگه می‌دارد."),
    ("peak", "🏔️", "قله‌ی بادها", 4, "بالای این قله، طوفان‌ها زاده می‌شوند."),
    ("gate", "🌫️", "دروازه‌ی مه", 4, "دروازه‌ای سنگی که هزار سال بسته مانده است."),
)
_LEGENDS = (
    ("ember_king", "👑", "پادشاه خاکستر", 5, "پادشاهی که قلمروش در آتش سوخت و هنوز بر تخت خاکسترش نشسته است."),
    ("moon_witch", "🌙", "جادوگر ماه", 5, "می‌گویند هر شب از ماه نیرو می‌گیرد و هرگز پیر نمی‌شود."),
    ("iron_titan", "🗿", "تایتان آهنین", 6, "غولی از آهن که پیش از اولین انسان بر زمین قدم گذاشت."),
    ("star_dragon", "🌟", "اژدهای ستاره", 6, "اژدهایی که از ستاره‌ها فرود آمد و نورش کور می‌کند."),
    ("lost_prince", "🕯️", "شاهزاده‌ی گمشده", 5, "وارث تاج فراموش‌شده که هنوز در جست‌وجوی خانه‌اش است."),
)


def _build() -> tuple[Card, ...]:
    cards: list[Card] = []
    for cls in CLASSES.values():
        cards.append(Card(f"hero_{cls.id}", "heroes", cls.emoji, cls.name, 2, _HERO_STORY.get(cls.id, cls.description)))
    for i, m in enumerate(MONSTERS):
        rarity = 1 + min(4, i * 5 // max(1, len(MONSTERS)))
        cards.append(Card(f"mon_{m.id}", "monsters", m.emoji, m.name, max(1, rarity - 1) if rarity > 2 else rarity,
                          f"{m.name} از سطح {m.min_level} در سرزمین‌های وحشی پیدا می‌شود و شکارچیان آن را خوب می‌شناسند."))
    for el in ELEMENTS:
        cards.append(Card(f"dragon_{el.id}", "dragons", el.emoji, f"اژدهای {el.adjective}", 3 + (el.level_offset % 3 == 0),
                          f"اژدهایی که نیروی {el.noun} در رگ‌هایش می‌جوشد. نقطه‌ضعفش: کلاس {CLASSES[el.weak_class].name}."))
    for pid, emoji, name, rarity, story in _PLACES:
        cards.append(Card(f"place_{pid}", "places", emoji, name, rarity, story))
    for lid, emoji, name, rarity, story in _LEGENDS:
        cards.append(Card(f"legend_{lid}", "legends", emoji, name, rarity, story))
    return tuple(cards)


CARDS: tuple[Card, ...] = _build()
_BY_ID = {c.id: c for c in CARDS}
_SET_BY_ID = {s.id: s for s in SETS}


def get_card(card_id: str) -> Card:
    return _BY_ID[card_id]


def get_set(set_id: str) -> CardSet:
    return _SET_BY_ID[set_id]


def cards_in(set_id: str) -> list[Card]:
    return [c for c in CARDS if c.set_id == set_id]


def roll_pack_card(rng: random.Random) -> Card:
    rarity = rng.choices(list(PACK_ODDS), weights=list(PACK_ODDS.values()), k=1)[0]
    pool = [c for c in CARDS if c.rarity == rarity]
    while not pool:  # no card of that rarity exists: fall back to the nearest lower one
        rarity -= 1
        pool = [c for c in CARDS if c.rarity == rarity]
    return rng.choice(pool)


def dust_value(card: Card) -> int:
    """Gold paid for a duplicate card."""
    return {1: 60, 2: 150, 3: 400, 4: 1000, 5: 2500, 6: 6000}[card.rarity]
