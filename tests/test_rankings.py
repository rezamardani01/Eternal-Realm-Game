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


async def seed(services, db):
    names = ["آرش", "سارا", "رها"]
    players = [
        await services.players.register(10 + i, f"u{i}", n, "elf", "archer") for i, n in enumerate(names)
    ]
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 9, gold = 100 WHERE id = ?", (players[1].id,))
        await tx.execute("UPDATE players SET level = 3, gold = 9000, wins = 4 WHERE id = ?", (players[2].id,))
    return players


async def test_global_boards_order(services, db):
    players = await seed(services, db)
    level = await services.rankings.global_board("level")
    assert [e.name for e in level.entries] == ["سارا", "رها", "آرش"]
    rich = await services.rankings.global_board("rich", await services.players.require(10))
    assert rich.entries[0].name == "رها" and rich.my_position == 2
    wins = await services.rankings.global_board("wins")
    assert wins.entries[0].name == "رها"
    assert players


async def test_banned_players_are_hidden(services, db):
    await seed(services, db)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET banned = 1 WHERE display_name = 'سارا'")
    level = await services.rankings.global_board("level")
    assert "سارا" not in [e.name for e in level.entries]


async def test_group_board_counts_command_points(h, services, db):
    await seed(services, db)
    await h.say(10, "ماهیگیری", group=True)
    await h.say(11, "ماهیگیری", group=True)
    await h.say(11, "معدن", group=True)
    await h.say(10, "رتبه", group=True)
    text = h.session.last_text()
    assert "سارا" in text and "آرش" in text
    assert text.index("سارا") < text.index("آرش")  # two activities beat one


async def test_ranking_commands(h, services, db):
    await seed(services, db)
    for word in ["برترین‌ها", "ثروتمندان", "قهرمانان"]:
        await h.say(10, word, group=True)
        assert "🥇" in h.session.last_text()
    await h.say(10, "رتبه", group=True)
    assert "هنوز کسی" in h.session.last_text()
