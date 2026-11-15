import pytest

from eternal_realm.bot.commands import REGISTRY
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, level):
    p = await services.players.register(uid, f"u{uid}", f"قهرمان{uid}", "elf", "archer")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=200_000, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def test_a_new_hero_sees_only_the_few_main_doors(h, services, db):
    await hero(services, db, 1, 2)
    await h.say(1, "/start")
    labels = h.labels()
    assert len(labels) <= 8
    for name in ("ماجراجویی", "سفر قهرمان", "نبرد و چالش", "قهرمان من", "آکادمی", "امکانات بیشتر"):
        assert any(name in t for t in labels), name
    assert not any("دهکده" in t or "آنلاین" in t for t in labels)


async def test_a_grown_hero_gets_the_village_and_the_army_in_front(h, services, db):
    await hero(services, db, 2, 8)
    await h.say(2, "/start")
    assert h.labels()[0] == "🌐 مبارزه آنلاین"
    assert any("بنای دهکده" in t for t in h.labels())  # no village yet: the button invites to found one
    assert "دهکده بساز" in h.session.last_text()
    p = await services.players.require(2)
    await services.city.found(p, "پارسیان", "🦁")
    await h.say(2, "/start")
    labels = h.labels()
    assert "🏰 دهکده من" in labels and "🗡️ لشکرکشی" in labels
    assert "دهکده: ارتش" in h.session.last_text()


async def test_the_more_screen_keeps_the_side_features_one_tap_away(h, services, db):
    await hero(services, db, 3, 10)
    await h.panel(3, "more")
    labels = " ".join(h.labels())
    for name in ("حیوان خانگی", "آلبوم کارت", "ارتقای قهرمان", "مسیر قهرمانی", "مأموریت‌ها", "دستاوردها", "دوستان", "مسابقات", "دعوت", "استراحت", "کد هدیه", "اعلان‌ها"):
        assert name in labels, name
    await h.panel(3, "profile")
    assert len(h.labels()) <= 7


def test_the_altar_is_gone():
    assert REGISTRY.resolve("محراب") is None
    from eternal_realm.bot.panel import SCREENS

    assert "altar" not in SCREENS


async def test_the_advisor_pushes_the_village_and_the_army(services, db):
    p = await hero(services, db, 4, 8)
    tips = await services.advisor.for_player(p, 8)
    assert tips[0].screen == "city"
    await services.city.found(p, "آذرگان", "🦁")
    tips = await services.advisor.for_player(await services.players.require(4), 8)
    assert tips[0].screen == "citytroops"
