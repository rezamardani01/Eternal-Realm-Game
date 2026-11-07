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


async def test_non_admin_cannot_change_settings(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(10, "غیرفعال ماهیگیری", group=True)
    assert "مدیران" in h.session.last_text()
    await h.say(10, "ماهیگیری", group=True)
    assert "قلاب" in h.session.last_text()


async def test_admin_toggles_activity(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    h.session.chat_admins.add(99)
    await h.say(99, "غیرفعال ماهیگیری", group=True)
    assert "غیرفعال شد" in h.session.last_text()
    await h.say(10, "ماهیگیری", group=True)
    assert "بسته" in h.session.last_text()
    await h.say(99, "تنظیمات گروه", group=True)
    assert "ماهیگیری" in h.session.last_text()
    await h.say(99, "فعال ماهیگیری", group=True)
    await h.say(10, "ماهیگیری", group=True)
    assert "قلاب" in h.session.last_text()


async def test_admin_pauses_whole_game(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    h.session.chat_admins.add(99)
    await h.say(99, "غیرفعال بازی", group=True)
    h.session.reset()
    await h.say(10, "پروفایل", group=True)
    assert h.session.calls == []  # silent while paused
    await h.say(99, "فعال بازی", group=True)  # admin tools keep working
    assert "باز شد" in h.session.last_text()
    await h.say(10, "پروفایل", group=True)
    assert "آرش" in h.session.last_text()


async def test_unknown_or_fixed_commands_cannot_be_toggled(h):
    h.session.chat_admins.add(99)
    await h.say(99, "غیرفعال پروفایل", group=True)
    assert "نمی‌شود خاموش کرد" in h.session.last_text()


async def test_bot_owner_is_always_allowed(h, services):
    await h.say(1, "غیرفعال معدن", group=True)  # owner_id=1 in the test settings
    assert "غیرفعال شد" in h.session.last_text()


async def test_ordinary_chat_with_these_words_is_ignored(h):
    await h.say(10, "فعال باش دیگه", group=True)
    await h.say(10, "خاموش", group=True)
    assert h.session.calls == []
