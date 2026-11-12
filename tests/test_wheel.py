import random
import re

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data import wheel as data
from eternal_realm.game.data.items import ITEMS
from eternal_realm.game.data.packs import PACKS
from eternal_realm.shared.errors import GameError
from eternal_realm.shared.text import EMOJI

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid=7):
    return await services.players.register(uid, f"u{uid}", f"آرش{uid}", "elf", "archer")


def test_the_table_is_sound():
    assert all(i in ITEMS for s in data.SLICES for i, _ in s.items)
    assert not any(s.empty for s in data.SLICES)  # every spin pays something
    assert len({s.id for s in data.SLICES}) == len(data.SLICES)
    small = sum(share for s, share in data.odds() if s.id in ("ore", "potion", "herb"))
    assert 0.05 < small < 0.2  # the cheap prizes are a minority
    strong = {"knight_sword", "knight_armor", "war_hammer", "storm_staff", "elven_bow", "fire_sword", "dragon_armor"}
    assert strong <= {i for s in data.SLICES for i, _ in s.items}  # gear for high levels
    rng = random.Random(1)
    assert {data.spin(rng).id for _ in range(5000)} >= {s.id for s in data.SLICES if s.weight >= 5}


async def test_buying_a_pack_adds_spins_and_spinning_pays(services, db, h):
    p = await hero(services)
    order = await services.payments.create_order(p, "wheel_5")
    assert order.amount == 455_000 and PACKS["wheel_5"].price_toman == 45_500
    delivery = await services.payments.complete(7, order.payload, order.amount, "c1")
    assert "۵ فرصت" in delivery.granted
    assert await services.wheel.spins(p.id) == 5
    again = await services.payments.complete(7, order.payload, order.amount, "c1")  # a repeated confirmation
    assert again.duplicate and await services.wheel.spins(p.id) == 5
    for left in (4, 3, 2, 1, 0):
        prize, got = await services.wheel.spin(p)
        assert got == left
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM wheel_log WHERE player_id = ?", (p.id,), 0) == 5
    with pytest.raises(GameError, match="فرصت"):
        await services.wheel.spin(p)


async def test_the_wheel_screens_and_the_spin(h, services, db):
    p = await hero(services)
    await h.panel(7, "premium")
    assert h.session.last_markup_rows()[0][0]["text"].endswith("گردونه شانس")  # the top row of the treasury
    await h.panel(7, "wheel")
    text = h.session.last_text()
    assert "گردونه شانس" in text and "هیچ چرخشی پوچ نیست" in text and "۱۰٬۴۰۰ تومان" in text
    for line in text.splitlines():
        assert len(re.findall(EMOJI, line)) <= 1, line
    assert not any("بچرخان" in label for label in h.labels())
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET wheel_spins = 2 WHERE id = ?", (p.id,))
    await h.panel(7, "wheel")
    await h.panel(7, "wheelspin")
    result = h.session.last_text()
    assert "فرصت باقی‌مانده: ۱" in result and any("چرخاندن دوباره" in label for label in h.labels())
    assert len([t for t in h.session.texts() if "🔻" in t]) >= 6  # the wheel turned through several frames
    await h.panel(7, "wheelspin")
    assert "فرصت باقی‌مانده: ۰" in h.session.last_text() and any("خرید فرصت" in label for label in h.labels())
    await h.panel(7, "wheelodds")
    assert "جایزه‌ها و شانس‌ها" in h.session.last_text()
