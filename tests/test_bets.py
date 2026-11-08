import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.services.bets import FEE_PERCENT, OPEN_SECONDS, prize_for
from eternal_realm.shared.errors import GameError

from .harness import Harness

CHAT = -500


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=5_000, crystal=0, ore=0):
    p = await services.players.register(uid, f"u{uid}", name, "dragonborn", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = ?, crystal = ? WHERE id = ?", (gold, crystal, p.id))
        if ore:
            await services.inventory.grant(tx, p.id, "iron_ore", ore)
    return await services.players.require(uid)


async def ore(db, pid):
    async with db.read() as tx:
        return await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = 'iron_ore'", (pid,), 0)


async def play_to_the_end(h, services, a, b, duel_id=1):
    for _ in range(120):
        duel = await services.duels.get(duel_id)
        if duel.status != "active":
            return duel
        uid = a.platform_user_id if duel.battle.current.player_id == a.id else b.platform_user_id
        await h.click(uid, h.button_data("حمله"), group=True)
    raise AssertionError("duel did not finish")


async def play_with_the_service(services, a, b, duel_id=1):
    from eternal_realm.game.engine.combat import Action

    for _ in range(120):
        duel = await services.duels.get(duel_id)
        if duel.status != "active":
            return duel
        current = a if duel.battle.current.player_id == a.id else b
        await services.duels.act(duel_id, await services.players.require(current.platform_user_id), Action.ATTACK)
    raise AssertionError("duel did not finish")


async def open_bet(h, uid, kind_label="سکه"):
    await h.say(uid, "مبارزه شرطی", group=True)
    await h.tap(uid, kind_label, group=True)


async def test_the_word_opens_a_panel_with_the_three_things_to_bet(h, services, db):
    await hero(services, db, 10, "آرش", crystal=3)
    await h.say(10, "مبارزه شرطی", group=True)
    text = h.session.last_text()
    assert "دوئل شرطی" in text and "سکه‌ی شما" in text and "کریستال شما" in text
    labels = " ".join(h.labels())
    assert "سکه" in labels and "کریستال" in labels and "منابع" in labels
    await h.say(10, "دوئل شرطی", group=True)
    assert "دوئل شرطی" in h.session.last_text()


async def test_a_bet_locks_the_stake_and_shows_a_waiting_message(h, services, db):
    await hero(services, db, 10, "آرش", gold=1_000)
    await open_bet(h, 10)
    assert "مقدار شرط" in h.session.last_text()
    await h.tap(10, "ثبت شرط", group=True)
    text = h.session.last_text()
    for part in ("دوئل شرطی", "شرط هر نفر", "جایزه‌ی برنده", "کارمزد", "مهلت"):
        assert part in text
    assert any("قبول شرط" in l for l in h.labels()) and any("لغو شرط" in l for l in h.labels())
    me = await services.players.require(10)
    assert me.gold < 1_000  # the stake is out of the wallet while the bet is open
    bet = await services.bets.open_for(me.id)
    assert bet is not None and bet.status == "open" and me.gold == 1_000 - bet.amount


async def test_only_one_open_bet_and_it_needs_enough(h, services, db):
    a = await hero(services, db, 10, "آرش", gold=300)
    await services.bets.create(a, CHAT, "gold", "", 100)
    with pytest.raises(GameError, match="شرط باز دارید"):
        await services.bets.create(await services.players.require(10), CHAT, "gold", "", 50)
    with pytest.raises(GameError):
        await services.bets.create(await hero(services, db, 11, "سارا", gold=50), CHAT, "gold", "", 100)  # cannot afford
    with pytest.raises(GameError, match="بین"):
        await services.bets.create(await hero(services, db, 12, "رها", gold=500), CHAT, "gold", "", 5)  # too small
    with pytest.raises(GameError, match="منابع"):
        await services.bets.create(await hero(services, db, 13, "پویا", gold=500), CHAT, "item", "iron_sword", 1)


async def test_the_opponent_must_have_enough_and_nothing_changes_when_not(h, services, db):
    a = await hero(services, db, 10, "آرش", gold=1_000)
    poor = await hero(services, db, 11, "سارا", gold=50)
    bet = await services.bets.create(a, CHAT, "gold", "", 200)
    with pytest.raises(GameError):
        await services.bets.accept(bet.id, poor)
    assert (await services.players.require(11)).gold == 50
    assert (await services.bets.get(bet.id)).status == "open"  # still waiting for somebody who can match it
    with pytest.raises(GameError, match="خودتان"):
        await services.bets.accept(bet.id, await services.players.require(10))


async def test_accepting_starts_the_duel_and_the_winner_takes_the_pot(h, services, db):
    a = await hero(services, db, 10, "آرش", gold=1_000)
    b = await hero(services, db, 11, "سارا", gold=1_000)
    await h.say(10, "مبارزه شرطی", group=True)
    await h.tap(10, "سکه", group=True)
    await h.tap(10, "ثبت شرط", group=True)
    stake = (await services.bets.open_for(a.id)).amount
    await h.click(10, h.button_data("قبول شرط"), group=True)  # the maker cannot accept his own bet
    assert any("خودتان" in x.get("text", "") for x in h.session.callback_answers())
    await h.click(11, h.button_data("قبول شرط"), group=True)
    assert "دوئل شرطی شروع شد" in h.session.last_text() and "میدان نبرد" in h.session.last_text()
    assert (await services.players.require(11)).gold == 1_000 - stake  # the opponent's stake is locked too
    await play_to_the_end(h, services, a, b)
    prize, fee = prize_for("gold", stake)
    gold = [(await services.players.require(u)).gold for u in (10, 11)]
    winner = 0 if gold[0] > gold[1] else 1
    assert gold[winner] - (1_000 - stake) >= prize  # the prize (plus the usual duel reward)
    assert sum(gold) <= 2_000 + 400  # coins never appear out of thin air (only the small duel rewards)
    assert fee == 2 * stake * FEE_PERCENT // 100
    result = h.session.last_text()
    assert "شرط دوئل" in result and "جایزه را برد" in result and "کارمزد" in result
    assert (await services.bets.get(1)).status == "done"
    assert await services.bets.open_for(a.id) is None  # free to bet again


async def test_cancel_and_timeout_refund_the_maker(h, services, db, clock):
    a = await hero(services, db, 10, "آرش", gold=1_000)
    bet = await services.bets.create(a, CHAT, "gold", "", 400)
    assert (await services.players.require(10)).gold == 600
    with pytest.raises(GameError, match="سازنده"):
        await services.bets.cancel(bet.id, await hero(services, db, 11, "سارا"))
    await services.bets.cancel(bet.id, await services.players.require(10))
    assert (await services.players.require(10)).gold == 1_000
    bet = await services.bets.create(await services.players.require(10), CHAT, "gold", "", 250)
    clock.advance(OPEN_SECONDS + 1)
    expired = await services.bets.expire_stale()
    assert [x.id for x in expired] == [bet.id] and (await services.players.require(10)).gold == 1_000
    with pytest.raises(GameError, match="باز نیست"):
        await services.bets.accept(bet.id, await services.players.require(11))


async def test_resources_and_crystals_can_be_bet_too(h, services, db):
    a = await hero(services, db, 10, "آرش", gold=0, crystal=10, ore=20)
    b = await hero(services, db, 11, "سارا", gold=0, crystal=10, ore=20)
    bet = await services.bets.create(a, CHAT, "item", "iron_ore", 8)
    assert await ore(db, a.id) == 12 and "سنگ آهن" in bet.label
    with pytest.raises(GameError):
        await services.bets.accept(bet.id, await hero(services, db, 12, "رها", ore=3))  # not enough ore
    await services.bets.accept(bet.id, b)
    assert await ore(db, b.id) == 12
    duel = await play_with_the_service(services, a, b)
    assert await ore(db, a.id) + await ore(db, b.id) == 40  # nothing is created or lost
    winner_ore = max(await ore(db, a.id), await ore(db, b.id))
    assert winner_ore == 12 + 16 and duel.status == "finished"  # items carry no fee

    c = await hero(services, db, 13, "پویا", gold=0, crystal=10)
    d = await hero(services, db, 14, "نگار", gold=0, crystal=10)
    bet = await services.bets.create(c, CHAT, "crystal", "", 4)
    assert (await services.players.require(13)).crystal == 6 and "کریستال" in bet.label
    await services.bets.accept(bet.id, d)
    assert (await services.players.require(14)).crystal == 6


async def test_a_drawn_duel_gives_both_stakes_back(services, db):
    from eternal_realm.game.services.bets import settle

    a = await hero(services, db, 10, "آرش", gold=1_000)
    b = await hero(services, db, 11, "سارا", gold=1_000)
    bet = await services.bets.create(a, CHAT, "gold", "", 300)
    await services.bets.accept(bet.id, b)
    async with db.transaction() as tx:
        outcome = await settle(tx, services.ctx, 1, None, services.ctx.now())
    assert outcome is not None and outcome.winner_id is None
    assert (await services.players.require(10)).gold == 1_000 and (await services.players.require(11)).gold == 1_000
    async with db.transaction() as tx:
        assert await settle(tx, services.ctx, 1, a.id, services.ctx.now()) is None  # settled once only


async def test_a_duel_that_cannot_start_returns_the_stake(h, services, db):
    a = await hero(services, db, 10, "آرش", gold=1_000)
    b = await hero(services, db, 11, "سارا", gold=1_000)
    bet = await services.bets.create(a, CHAT, "gold", "", 200)
    pair = services.ctx.balance.duel_pair_daily_limit
    for _ in range(pair):  # the two have already fought as often as the daily limit allows
        d = await services.duels.challenge(CHAT, a, b)
        async with db.transaction() as tx:
            await tx.execute("UPDATE duels SET status = 'finished' WHERE id = ?", (d.id,))
    with pytest.raises(GameError):
        await services.bets.accept(bet.id, b)
    assert (await services.players.require(11)).gold == 1_000  # nothing was kept
    assert (await services.bets.get(bet.id)).status == "open"


def test_prize_math():
    assert prize_for("gold", 100) == (190, 10)
    assert prize_for("item", 5) == (10, 0)
    assert prize_for("crystal", 4) == (8, 0)  # tiny pots round the fee down to nothing


async def test_wallet_ledger_unaffected_by_helpers(services, db):
    p = await hero(services, db, 10, "آرش", gold=100)
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=1, reason="t", now=services.ctx.now())
    assert (await services.players.require(10)).gold == 101
