import random

import pytest

from eternal_realm.config import Balance
from eternal_realm.db.database import Database


class FakeClock:
    def __init__(self, start: int = 1_700_000_000) -> None:
        self.t = start

    def __call__(self) -> int:
        return self.t

    def advance(self, seconds: int) -> None:
        self.t += seconds


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def rng() -> random.Random:
    return random.Random(1234)


@pytest.fixture
def balance() -> Balance:
    return Balance()


@pytest.fixture(autouse=True)
def _open_trip_sections(monkeypatch):
    """The trip's daily limit is tested on its own; everywhere else a hero may play a section as often as the test needs."""
    from eternal_realm.game.data import solo

    monkeypatch.setattr(solo, "DAILY_USES", 999)


@pytest.fixture(autouse=True)
def _no_animation_delay(monkeypatch):
    """Animations pause between frames; tests must not wait for them."""
    from eternal_realm.context import AppContext

    async def instant(self, factor: float = 1.0) -> None:
        return None

    monkeypatch.setattr(AppContext, "pause", instant)
