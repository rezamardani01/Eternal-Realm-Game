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
