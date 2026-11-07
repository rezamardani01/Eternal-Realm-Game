from dataclasses import replace

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.engine.combat import Action
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def two_players(services):
    a = await services.players.register(10, "a", "آرش", "dragonborn", "warrior")
    b = await services.players.register(11, "b", "سارا", "fairy", "mage")
    return a, b


async def current_player(services, duel_id, a, b):
    duel = await services.duels.get(duel_id)
    return a if duel.battle.current.player_id == a.id else b


async def play_to_end(services, duel_id, a, b):
    for _ in range(100):
        duel = await services.duels.get(duel_id)
        if duel.status != "active":
            return duel
        who = await current_player(services, duel_id, a, b)
        action = Action.SKILL if duel.battle.current.skill_ready_in <= 1 else Action.ATTACK
        await services.duels.act(duel_id, who, action)
    raise AssertionError("duel did not end")


async def test_full_duel_pays_exactly_once(services, db):
    a, b = await two_players(services)
    duel = await services.duels.challenge(-500, a, b)
    await services.duels.accept(duel.id, b)
    final = await play_to_end(services, duel.id, a, b)
    assert final.status == "finished"

    wa, wb = await services.players.require(10), await services.players.require(11)
    assert (wa.wins, wb.wins) in {(1, 0), (0, 1), (0, 0)}
    assert wa.wins + wb.losses <= 2
    async with db.read() as tx:
        rows = await tx.fetchall("SELECT ref FROM transactions WHERE reason = 'duel_win'")
    assert len(rows) <= 1
    with pytest.raises(GameError):  # a finished duel cannot be played or paid again
        await services.duels.act(duel.id, a, Action.ATTACK)


async def test_only_target_may_accept_and_only_current_player_may_act(services):
    a, b = await two_players(services)
    duel = await services.duels.challenge(-500, a, b)
    with pytest.raises(GameError):
        await services.duels.accept(duel.id, a)
    update = await services.duels.accept(duel.id, b)
    with pytest.raises(GameError):
        await services.duels.accept(duel.id, b)  # double click
    waiting = a if update.battle.current.player_id == b.id else b
    with pytest.raises(GameError, match="نوبت"):
        await services.duels.act(duel.id, waiting, Action.ATTACK)


async def test_validations(services):
    a, b = await two_players(services)
    with pytest.raises(GameError):
        await services.duels.challenge(-500, a, a)
    duel = await services.duels.challenge(-500, a, b)
    with pytest.raises(GameError):
        await services.duels.challenge(-500, b, a)  # one open duel at a time
    await services.duels.decline(duel.id, b)
    with pytest.raises(GameError):
        await services.duels.accept(duel.id, b)


async def test_pair_daily_limit(services):
    a, b = await two_players(services)
    for _ in range(services.ctx.balance.duel_pair_daily_limit):
        duel = await services.duels.challenge(-500, a, b)
        await services.duels.accept(duel.id, b)
        who = await current_player(services, duel.id, a, b)
        await services.duels.act(duel.id, who, Action.SURRENDER)
    with pytest.raises(GameError, match="بیش از حد"):
        await services.duels.challenge(-500, a, b)


async def test_invitation_and_turn_timeouts(services, clock):
    a, b = await two_players(services)
    duel = await services.duels.challenge(-500, a, b)
    clock.advance(services.ctx.balance.duel_invite_seconds + 1)
    closed = await services.duels.expire_stale()
    assert len(closed) == 1 and (await services.duels.get(duel.id)).status == "expired"

    duel2 = await services.duels.challenge(-500, a, b)
    await services.duels.accept(duel2.id, b)
    clock.advance(services.ctx.balance.duel_turn_seconds + 1)
    done = await services.duels.expire_stale()
    assert done[0].finished and done[0].timed_out
    assert (await services.duels.get(duel2.id)).status == "finished"


async def test_daily_reward_cap(services):
    a, b = await two_players(services)
    capped = replace(services.ctx.balance, duel_daily_reward_cap=1, duel_pair_daily_limit=50)
    object.__setattr__(services.ctx.settings, "balance", capped)
    gained = []
    for _ in range(3):
        duel = await services.duels.challenge(-500, a, b)
        await services.duels.accept(duel.id, b)
        who = await current_player(services, duel.id, a, b)
        result = await services.duels.act(duel.id, who, Action.SURRENDER)
        gained.append(sum(p.xp for p in result.payouts.values()))
    assert gained[0] > 0 and gained[-1] == 0


async def test_duel_via_chat_buttons(h, services):
    a, b = await two_players(services)
    await h.say(10, "مبارزه", group=True, reply_to=h.message_of(11))
    assert "درخواست مبارزه" in h.session.last_text()
    accept = h.button_data("قبول")

    await services.players.register(12, "c", "رها", "elf", "archer")
    await h.click(12, accept, group=True)  # a stranger cannot accept
    assert any("فقط کسی" in c.get("text", "") for c in h.session.callback_answers())

    await h.click(11, accept, group=True)
    assert "دوئل" in h.session.last_text() and h.session.last_buttons()

    for _ in range(80):
        duel = await services.duels.get(1)
        if duel.status != "active":
            break
        uid = 10 if duel.battle.current.player_id == a.id else 11
        await h.click(uid, h.button_data("حمله"), group=True)
    assert (await services.duels.get(1)).status == "finished"
    assert "پایان دوئل" in h.session.last_text()


async def test_cannot_duel_without_reply_or_with_unregistered(h, services):
    await two_players(services)
    await h.say(10, "مبارزه", group=True)
    assert "ریپلای" in h.session.last_text()
    await h.say(10, "مبارزه", group=True, reply_to=h.message_of(99))
    assert "شخصیت نساخته" in h.session.last_text()
