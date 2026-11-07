import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def test_full_onboarding_flow(h, services):
    await h.say(10, "/start")
    assert "نامی" in h.session.last_text() or "نام" in h.session.last_text()

    await h.say(10, "آرش")
    assert "نژاد" in h.session.last_text()
    await h.click(10, h.button_data("الف"))
    assert "کلاس" in h.session.last_text()
    await h.click(10, h.button_data("کماندار"))

    player = await services.players.find(10)
    assert player is not None
    assert (player.name, player.race_id, player.class_id) == ("آرش", "elf", "archer")
    assert any("قهرمان شما ساخته شد" in t for t in h.session.texts())


async def test_invalid_and_taken_names_keep_asking(h, services):
    await services.players.register(11, "x", "سارا", "fairy", "mage")
    await h.say(10, "/start")
    await h.say(10, "a")
    assert "حرف" in h.session.last_text()
    await h.say(10, "سارا")
    assert "پیش‌تر" in h.session.last_text()
    await h.say(10, "رها")
    assert "نژاد" in h.session.last_text()


async def test_start_for_existing_player_shows_profile(h, services):
    await services.players.register(10, "x", "آرش", "dwarf", "warrior")
    await h.say(10, "/start")
    assert "آرش" in h.session.last_text()
    assert h.session.last_buttons()


async def test_class_button_without_state_is_ignored(h, services):
    await h.click(10, "cls:mage")
    assert await services.players.find(10) is None
