import re

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import season as season_repo
from eternal_realm.game.data.achievements import FAMILIES, reward_text
from eternal_realm.game.data.items import ITEMS
from eternal_realm.shared.errors import GameError
from eternal_realm.shared.text import EMOJI

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def _do(services, db, player, deed: str, times: int):
    async with db.transaction() as tx:
        for _ in range(times):
            await season_repo.add_points(tx, player.id, deed, services.ctx.now())


def test_the_tables_are_sound():
    assert len({f.id for f in FAMILIES}) == len(FAMILIES)
    for f in FAMILIES:
        targets = [s.target for s in f.steps]
        assert targets == sorted(set(targets)) and "{n}" in f.how, f.id
        for s in f.steps:
            assert s.gold or s.crystal or s.items, f.id
            assert all(i in ITEMS for i, _ in s.items), f.id
            assert reward_text(s)


async def test_deeds_are_counted_and_the_step_is_paid_once(services, db):
    p = await services.players.register(7, "u", "آرش", "elf", "archer")
    await _do(services, db, p, "hunt", 9)
    view = await services.achievements.view(p, "hunt")
    assert view.value == 9 and not view.claimable and view.paid == 0
    with pytest.raises(GameError):
        await services.achievements.claim(p, "hunt")
    await _do(services, db, p, "hunt", 1)
    before = (await services.players.get(p.id)).gold
    family, number, step = await services.achievements.claim(p, "hunt")
    assert (family.id, number, step.target) == ("hunt", 1, 10)
    assert (await services.players.get(p.id)).gold == before + step.gold
    with pytest.raises(GameError):  # the next step needs 100
        await services.achievements.claim(p, "hunt")
    view = await services.achievements.view(p, "hunt")
    assert view.paid == 1 and view.step.target == 100


async def test_live_facts_count_too(services, db):
    p = await services.players.register(8, "u", "سینا", "human", "warrior")
    levels = await services.achievements.view(p, "level")
    assert levels.value == p.level
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 10 WHERE id = ?", (p.id,))
    assert (await services.achievements.view(p, "level")).claimable
    assert await services.achievements.claimable_count(p) >= 1


async def test_a_title_reward_and_items_arrive(services, db):
    p = await services.players.register(9, "u", "نیما", "elf", "archer")
    await _do(services, db, p, "boss_win", 1)
    await services.achievements.claim(p, "bossbane")
    async with db.read() as tx:
        have = await tx.scalar("SELECT COALESCE(SUM(qty), 0) FROM inventory WHERE player_id = ? AND item_id = 'magic_chest'", (p.id,), 0)
    assert have == 1
    await _do(services, db, p, "boss_win", 49)
    for _ in range(2):
        await services.achievements.claim(p, "bossbane")
    assert (await services.players.get(p.id)).honor == "اژدهاکش"


async def test_the_screens(h, services, db):
    p = await services.players.register(7, "u", "آرش", "elf", "archer")
    await _do(services, db, p, "duel_win", 5)
    await h.panel(7, "profile")
    assert any("دستاوردها" in b["text"] for b in h.session.last_buttons())
    await h.panel(7, "ach")
    text = h.session.last_text()
    assert "دوئل‌باز" in text and "آماده‌ی دریافت" in text
    await h.panel(7, "achf", "duel")
    text = h.session.last_text()
    assert "۵ دوئل را ببر" in text and "۵۰ دوئل را ببر" in text and "پاداش" in text
    for line in text.splitlines():  # house rule: at most one emoji per line, and only at its start
        assert len(re.findall(EMOJI, line)) <= 1, line
    await h.panel(7, "achc", "duel")
    assert "پاداش گرفته شد" in h.session.last_text()
    await h.panel(7, "achc", "duel")  # a second tap changes nothing
    assert (await services.achievements.view(p, "duel")).paid == 1
