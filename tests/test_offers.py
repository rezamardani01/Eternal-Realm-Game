import pytest

from eternal_realm.bot import offers as offers_ui
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.cards import cards_in
from eternal_realm.game.data.offers import DAY, RULES
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=1, gold=0):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, gold = ? WHERE id = ?", (level, gold, p.id))
    return await services.players.require(uid)


def test_every_rule_has_a_unique_id_and_a_known_screen():
    from eternal_realm.bot.panel import SCREENS

    assert len({r.id for r in RULES}) == len(RULES)
    assert all(r.screen in SCREENS for r in RULES)


async def test_a_quiet_new_player_gets_nothing(services, db):
    await hero(services, db, 1, "آرش")
    assert await services.offers.due() == []


async def test_collection_offer_fires_once_per_day_and_respects_cooldown(services, db, clock):
    p = await hero(services, db, 2, "سارا")
    async with db.transaction() as tx:
        for card in cards_in("heroes")[:4]:
            await services.cards.grant(tx, p.id, card.id)
    due = await services.offers.due()
    assert [o.rule.id for _, o in due] == ["collection"] and "کارت کم دارید" in due[0][1].text
    assert await services.offers.due() == []  # the daily cap
    clock.advance(DAY + 1)
    assert await services.offers.due() == []  # the rule's own cooldown (5 days)
    clock.advance(5 * DAY)
    async with db.transaction() as tx:  # the player is active again, so the idle-days offers stay quiet
        await wallet.apply(tx, p.id, gold=1, reason="t", now=services.ctx.now())
    assert [o.rule.id for _, o in await services.offers.due()] == ["collection"]


async def test_the_player_can_switch_offers_off(services, db):
    p = await hero(services, db, 3, "رها", level=20, gold=30_000)
    await services.offers.set_enabled(p, False)
    assert await services.offers.due() == []
    await services.offers.set_enabled(p, True)
    due = await services.offers.due()
    assert due and due[0][1].rule.id in {r.id for r in RULES}


async def test_comeback_gift_needs_an_offer_and_pays_once(services, db, clock):
    p = await hero(services, db, 4, "نگار")
    with pytest.raises(GameError):
        await services.offers.claim_return_gift(p)
    clock.advance(8 * DAY)
    due = await services.offers.due()
    assert [o.rule.id for _, o in due] == ["comeback"]
    gold = (await services.players.require(4)).gold
    assert await services.offers.claim_return_gift(p) == 500
    assert (await services.players.require(4)).gold == gold + 500
    with pytest.raises(GameError, match="قبلاً"):
        await services.offers.claim_return_gift(p)


async def test_delivery_sends_a_private_message_with_buttons(h, services, db):
    p = await hero(services, db, 5, "پویا", level=20, gold=30_000)
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=1, reason="t", now=services.ctx.now())
    assert await offers_ui.deliver(h.bot, services) == 1
    sent = h.session.sent("sendMessage")[-1]
    assert str(sent["chat_id"]) == "5" and "پیشنهاد" not in sent["text"] or sent["text"]
    labels = [b["text"] for row in sent["reply_markup"]["inline_keyboard"] for b in row]
    assert any("دیگر پیشنهاد نفرست" in t for t in labels)
    await h.click(5, next(b["callback_data"] for row in sent["reply_markup"]["inline_keyboard"] for b in row
                          if "دیگر پیشنهاد" in b["text"]))
    assert not await services.offers.enabled(await services.players.require(5))
    assert await offers_ui.deliver(h.bot, services) == 0


async def test_three_idle_days_offer_a_special_mission_worth_triple(h, services, db, clock):
    p = await hero(services, db, 6, "رها", level=5)
    clock.advance(4 * DAY)
    due = await services.offers.due()
    assert [o.rule.id for _, o in due] == ["comeback3"]
    await h.panel(6, "offerwelcome")
    todays = await services.missions.today(p)
    special = next(m for m in todays if m.kind_id == "welcome")
    ordinary = next(m for m in todays if m.kind_id != "welcome" and m.target == 3) if any(
        m.kind_id != "welcome" and m.target == 3 for m in todays) else None
    assert special.target == 3 and special.gold > 0
    if ordinary:
        assert special.gold == 3 * ordinary.gold
    assert await services.missions.grant_welcome(p) is False  # once a day
    for _ in range(3):
        async with db.transaction() as tx:
            from eternal_realm.db.repos import season as season_repo

            await season_repo.add_points(tx, p.id, "hunt", services.ctx.now())
    gold = (await services.players.require(6)).gold
    await services.missions.claim(p, 9)
    assert (await services.players.require(6)).gold == gold + special.gold
