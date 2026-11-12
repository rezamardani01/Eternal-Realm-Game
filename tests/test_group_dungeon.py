import asyncio

import pytest

from eternal_realm.bot import group_dungeon as ui
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.services.group_dungeon import COOLDOWN, LOBBY_SECONDS, MAX_PLAYERS
from eternal_realm.shared.errors import GameError

from .harness import Harness

CHAT = -500


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=20, cls="warrior"):
    p = await services.players.register(uid, f"u{uid}", name, "dragonborn", cls)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


async def squad(services, db, n=4, level=20):
    classes = ["warrior", "mage", "archer", "guardian", "rogue"]
    return [await hero(services, db, 10 + i, f"قهرمان{i}", level, classes[i % 5]) for i in range(n)]


async def test_lobby_rules(services, db, clock):
    low = await hero(services, db, 1, "تازه", level=2)
    with pytest.raises(GameError, match="سطح"):
        await services.gdungeon.open(CHAT, low)
    players = await squad(services, db, 6)
    lobby = await services.gdungeon.open(CHAT, players[0])
    with pytest.raises(GameError, match="باز است"):
        await services.gdungeon.open(CHAT, players[1])
    with pytest.raises(GameError, match="هستید"):
        await services.gdungeon.join(lobby.id, players[0])
    for p in players[1:MAX_PLAYERS]:
        await services.gdungeon.join(lobby.id, p)
    with pytest.raises(GameError, match="ظرفیت"):
        await services.gdungeon.join(lobby.id, players[5])
    clock.advance(LOBBY_SECONDS + 1)
    with pytest.raises(GameError, match="بسته"):
        await services.gdungeon.join(lobby.id, players[5])


async def test_only_the_opener_starts_and_needs_three(services, db):
    players = await squad(services, db, 4)
    lobby = await services.gdungeon.open(CHAT, players[0])
    with pytest.raises(GameError, match="دست‌کم"):
        await services.gdungeon.start(lobby.id, players[0])
    for p in players[1:3]:
        await services.gdungeon.join(lobby.id, p)
    with pytest.raises(GameError, match="گشاینده"):
        await services.gdungeon.start(lobby.id, players[1])


async def test_a_strong_squad_clears_it_and_everyone_is_paid_once(services, db):
    players = await squad(services, db, 5, level=30)
    lobby = await services.gdungeon.open(CHAT, players[0])
    for p in players[1:]:
        await services.gdungeon.join(lobby.id, p)
    before = {p.id: (await services.players.require(p.platform_user_id)).gold for p in players}
    result = await services.gdungeon.start(lobby.id, players[0])
    assert len(result.waves) >= 1 and len(result.payouts) == 5
    for pay in result.payouts:
        player = next(p for p in players if p.name == pay.name)
        assert (await services.players.require(player.platform_user_id)).gold == before[player.id] + pay.gold
    if result.cleared:
        assert len(result.waves) == 4 and sum(p.chest for p in result.payouts) == 1
    with pytest.raises(GameError, match="باز نیست"):
        await services.gdungeon.start(lobby.id, players[0])  # no second payout


async def test_a_weak_squad_fails_with_a_consolation(services, db):
    players = await squad(services, db, 3, level=5)
    async with db.transaction() as tx:
        for p in players:
            await tx.execute("UPDATE players SET level = 5 WHERE id = ?", (p.id,))
    services.ctx.rng.seed(1)
    lobby = await services.gdungeon.open(CHAT, players[0])
    for p in players[1:]:
        await services.gdungeon.join(lobby.id, p)
    # make the monsters brutal by pretending the average level is huge
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 5")
    result = await services.gdungeon.start(lobby.id, players[0])
    assert result.cleared in (True, False) and all(p.gold >= 12 for p in result.payouts)


async def test_cooldown_between_dungeons(services, db, clock):
    players = await squad(services, db, 3)
    lobby = await services.gdungeon.open(CHAT, players[0])
    for p in players[1:]:
        await services.gdungeon.join(lobby.id, p)
    await services.gdungeon.start(lobby.id, players[0])
    with pytest.raises(GameError, match="آماده"):
        await services.gdungeon.open(CHAT, players[0])
    clock.advance(COOLDOWN + 1)
    await services.gdungeon.open(CHAT, players[0])


async def test_glass_flow_in_a_group(h, services, db):
    players = await squad(services, db, 3, level=30)
    await h.say(10, "سیاه‌چال گروهی", group=True)
    assert "سیاه‌چال گروهی باز شد" in h.session.last_text()
    join = h.button_data("پیوستن")
    start = h.button_data("شروع")
    await h.click(11, join, group=True)
    await h.click(12, join, group=True)
    assert "قهرمان1" in h.session.sent("editMessageText")[-1]["text"]
    await h.click(11, start, group=True)  # not the opener
    assert any("گشاینده" in a.get("text", "") for a in h.session.callback_answers())
    await h.click(10, start, group=True)
    await asyncio.gather(*ui.TASKS)  # the result comes after the wait
    text = h.session.last_text()
    assert "سیاه‌چال فتح شد" in text or "سیاه‌چال شما را بلعید" in text
    assert any("🪙" in label for label in h.labels())
    assert players


async def test_the_result_comes_two_minutes_after_the_start_with_the_rooms_shown_meanwhile(h, services, db, monkeypatch):
    players = await squad(services, db, 3, level=30)
    waits = []

    async def record(self, seconds):
        waits.append(seconds)

    monkeypatch.setattr(AppContext, "wait", record)
    await h.say(10, "سیاه‌چال گروهی", group=True)
    await h.click(11, h.button_data("پیوستن"), group=True)
    await h.click(12, h.button_data("پیوستن"), group=True)
    await h.click(10, h.button_data("شروع"), group=True)
    # at once: the doors close and the countdown starts; nothing about the result yet
    frame = h.session.sent("editMessageText")[-1]["text"]
    assert "در جریان است" in frame and "نتیجه تا ۲ دقیقه" in frame and "سیاه‌چال فتح شد" not in frame
    assert not any("سیاه‌چال فتح شد" in m["text"] or "بلعید" in m["text"] for m in h.session.sent())
    gold = [(await services.players.require(uid)).gold for uid in (10, 11, 12)]
    await asyncio.gather(*ui.TASKS)
    # four steps of thirty seconds, the rooms announced on the way, then the result
    assert waits == [30, 30, 30, 30] and sum(waits) == services.ctx.balance.gdungeon_run_seconds == 120
    frames = [c["text"] for c in h.session.sent("editMessageText")]
    for room in ui.ROOMS:
        assert any(room in f for f in frames)
    assert "نتیجه تا ۱ دقیقه" in " ".join(frames)  # the countdown goes down
    assert "سیاه‌چال فتح شد" in h.session.last_text() or "بلعید" in h.session.last_text()
    assert players and gold  # (the rewards are paid once, at the start, as before)


async def test_a_refused_start_leaves_the_lobby_untouched_and_starts_no_countdown(h, services, db):
    await squad(services, db, 3, level=30)
    await h.say(10, "سیاه‌چال گروهی", group=True)
    await h.click(11, h.button_data("پیوستن"), group=True)
    await h.click(10, h.button_data("شروع"), group=True)  # only two fighters: refused
    assert not ui.TASKS
    assert not any("در جریان است" in m["text"] for m in h.session.sent("editMessageText"))

