import pytest

from eternal_realm.bot import art
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data import bosses, cards, items, pets
from eternal_realm.game.services.events import KINDS

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


def _all(group):
    return list(group.values()) if isinstance(group, dict) else list(group)


def test_every_item_pet_card_boss_and_event_has_a_small_picture():
    wanted = (
        [f"items/{i.id}" for i in _all(items.ITEMS)] + [f"pets/{p.id}" for p in _all(pets.PETS)]
        + [f"cards/{c.id}" for c in _all(cards.CARDS)] + [f"bosses/{b.id}" for b in _all(bosses.BOSSES)]
        + [f"events/{k}" for k in KINDS]
    )
    missing = [name for name in wanted if not art.has(name)]
    assert not missing, missing
    assert all(art.path(name).stat().st_size < 60_000 for name in wanted)  # small enough to load instantly


def test_art_names_cannot_escape_the_art_folder():
    assert art.path("../../config") is None and art.path("/etc/passwd") is None and art.path(None) is None


async def test_item_screens_come_with_a_picture_and_text_screens_replace_it(h, services):
    await services.players.register(4, "u4", "نگار", "elf", "warrior")
    await h.say(4, "فروشگاه", group=True)
    await h.click(4, h.button_data("سلاح و زره"), group=True)
    await h.click(4, h.button_data("شمشیر آهنی"), group=True)
    photos = h.session.sent("sendPhoto")
    assert photos and "شمشیر آهنی" in photos[-1]["caption"] and photos[-1]["reply_markup"]
    assert h.session.sent("deleteMessage")  # the old text panel was replaced by the picture
    await h.click(4, h.button_data("خرید"), group=True)
    assert "شمشیر آهنی" in h.session.last_text() and h.session.sent("sendPhoto")[-1]["reply_markup"]
