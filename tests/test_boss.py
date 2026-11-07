import asyncio

import pytest

from eternal_realm.bot import boss as boss_ui
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.shared.errors import GameError

from .harness import Harness

CHAT = -500


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=5, gold=1_000, cls="warrior"):
    p = await services.players.register(uid, f"u{uid}", name, "dragonborn", cls)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def set_hp(db, boss_id, hp):
    async with db.transaction() as tx:
        await tx.execute("UPDATE bosses SET hp = ? WHERE id = ?", (hp, boss_id))


async def test_summon_rules(services, db, clock):
    rookie = await hero(services, db, 10, "تازه‌کار", level=1)
    with pytest.raises(GameError, match="سطح"):
        await services.bosses.summon(rookie, CHAT)

    poor = await hero(services, db, 11, "آرش", level=5, gold=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 50 WHERE id = ?", (poor.id,))
    with pytest.raises(wallet.InsufficientFunds):
        await services.bosses.summon(await services.players.require(11), CHAT)  # the ritual costs 200 gold
    lead = await hero(services, db, 12, "سارا", level=5, gold=0)
    view = await services.bosses.summon(lead, CHAT)
    assert view.hp == view.max_hp > 0 and view.status == "active"
    assert (await services.players.require(12)).gold == services.ctx.balance.start_gold - 200
    with pytest.raises(GameError, match="باس زنده"):
        await services.bosses.summon(lead, CHAT)


async def test_cooldown_between_bosses_in_the_same_group(services, db, clock):
    lead = await hero(services, db, 10, "آرش", gold=5_000)
    view = await services.bosses.summon(lead, CHAT)
    clock.advance(services.ctx.balance.boss_duration_seconds + 1)  # it fled
    with pytest.raises(GameError, match="باس بعدی"):
        await services.bosses.summon(await services.players.require(10), CHAT)
    clock.advance(services.ctx.balance.boss_cooldown_seconds)
    again = await services.bosses.summon(await services.players.require(10), CHAT)
    assert again.id != view.id
    # another group is not affected
    other = await services.bosses.summon(await services.players.require(10), -999)
    assert other.chat_id == -999


async def test_hits_cost_energy_have_cooldowns_and_reduce_hp(services, db, clock):
    lead = await hero(services, db, 10, "آرش", gold=5_000)
    view = await services.bosses.summon(lead, CHAT)
    hit = await services.bosses.hit(view.id, await services.players.require(10))
    assert hit.damage > 0 and hit.view.hp == view.max_hp - hit.damage
    assert (await services.players.require(10)).energy == lead.energy - services.ctx.balance.boss_hit_energy
    with pytest.raises(GameError, match="خسته"):
        await services.bosses.hit(view.id, await services.players.require(10))
    heavy = await services.bosses.hit(view.id, await services.players.require(10), heavy=True)  # own cooldown
    assert heavy.heavy
    clock.advance(services.ctx.balance.boss_hit_cooldown + 1)
    await services.bosses.hit(view.id, await services.players.require(10))


async def test_defeating_the_boss_pays_by_damage_exactly_once(services, db, clock):
    a = await hero(services, db, 10, "آرش", gold=5_000)
    b = await hero(services, db, 11, "سارا", gold=0)
    c = await hero(services, db, 12, "رها", gold=0)
    view = await services.bosses.summon(a, CHAT)
    await set_hp(db, view.id, 400)
    await services.bosses.hit(view.id, await services.players.require(10))
    await services.bosses.hit(view.id, await services.players.require(11))
    await set_hp(db, view.id, 5)  # the last blow
    done = await services.bosses.hit(view.id, await services.players.require(12))

    assert done.finished and done.view.status == "defeated" and done.view.hp == 0
    names = [p.name for p in done.view.payouts]
    assert set(names) == {"آرش", "سارا", "رها"} and abs(sum(p.share for p in done.view.payouts) - 1) < 1e-9
    assert done.view.payouts[0].chest == "magic_chest"  # whoever hit hardest
    paid = {p.name: p.gold for p in done.view.payouts}
    assert all(g >= 40 for g in paid.values())

    async with db.read() as tx:
        rewards = await tx.scalar("SELECT COUNT(*) FROM transactions WHERE reason = 'boss_reward'")
    assert rewards == 3
    with pytest.raises(GameError, match="دیگر"):
        await services.bosses.hit(view.id, await services.players.require(10))
    assert c


async def test_two_final_blows_at_once_pay_a_single_time(services, db, clock):
    a = await hero(services, db, 10, "آرش", gold=5_000)
    b = await hero(services, db, 11, "سارا")
    c = await hero(services, db, 12, "رها")
    view = await services.bosses.summon(a, CHAT)
    await services.bosses.hit(view.id, await services.players.require(10))
    await set_hp(db, view.id, 3)
    results = await asyncio.gather(
        services.bosses.hit(view.id, await services.players.require(11)),
        services.bosses.hit(view.id, await services.players.require(12)),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in results) == 1
    async with db.read() as tx:
        rewards = await tx.scalar("SELECT COUNT(*) FROM transactions WHERE reason = 'boss_reward'")
    assert rewards == 2  # the first fighter and the one who landed the final blow, each once
    assert b and c


async def test_a_boss_nobody_finished_flees_with_a_small_consolation(services, db, clock):
    a = await hero(services, db, 10, "آرش", gold=5_000)
    view = await services.bosses.summon(a, CHAT)
    await services.bosses.hit(view.id, await services.players.require(10))
    gold_before = (await services.players.require(10)).gold
    clock.advance(services.ctx.balance.boss_duration_seconds + 1)
    fled = await services.bosses.expire_stale()
    assert len(fled) == 1 and fled[0].status == "expired"
    assert fled[0].payouts and fled[0].payouts[0].chest is None
    assert (await services.players.require(10)).gold > gold_before
    assert await services.bosses.expire_stale() == []  # nothing is paid twice


# --- through the bot ----------------------------------------------------------------------------
async def test_summon_and_fight_with_buttons_in_a_group(h, services, db):
    await hero(services, db, 10, "آرش", gold=5_000)
    await hero(services, db, 11, "سارا")
    await h.say(10, "باس", group=True)
    assert "ظاهر شد" in h.session.last_text()
    assert any("حمله سنگین" in t for t in h.labels())

    hit = h.button_data("حمله")
    await h.click(10, hit, group=True)
    assert "آسیب" in h.session.last_text() and "آرش" in h.session.last_text()
    await h.click(11, hit, group=True)
    assert "سارا" in h.session.last_text()

    h.session.reset()
    await h.say(10, "باس", group=True)  # while alive, the same boss is shown again
    assert "برترین ضربه‌ها" in h.session.last_text()
    boss_id = (await services.bosses.active(CHAT)).id
    await set_hp(db, boss_id, 1)
    await h.click(10, hit, group=True)  # 10 is on cooldown ...
    await h.click(11, h.button_data("سنگین"), group=True)  # ... 11 lands the final blow
    assert "شکست خورد" in h.session.last_text()
    assert h.session.sent("editMessageText")[-1].get("reply_markup") is None  # the fight is over: no buttons


async def test_unregistered_players_cannot_hit_and_group_can_switch_bosses_off(h, services, db):
    await hero(services, db, 10, "آرش", gold=5_000)
    await h.say(10, "باس", group=True)
    await h.click(77, h.button_data("حمله"), group=True)
    assert any("قهرمان" in a.get("text", "") or "ماجراجوی ناشناس" in a.get("text", "") for a in h.session.callback_answers())

    h.session.chat_admins.add(99)
    await h.say(99, "غیرفعال باس", group=True)
    assert "غیرفعال شد" in h.session.last_text()


async def test_panel_button_summons_in_groups_only(h, services, db):
    await hero(services, db, 10, "آرش", gold=5_000)
    await h.say(10, "قلمرو", group=True)
    assert any("باس گروه" in t for t in h.labels())
    await h.tap(10, "باس گروه", group=True)
    assert "احضار" in h.session.last_text()
    await h.tap(10, "احضار", group=True)
    assert any("ظاهر شد" in t for t in h.session.texts())
    assert await services.bosses.active(CHAT) is not None
    await h.say(10, "قلمرو")
    assert not any("باس گروه" in t for t in h.labels())


async def test_janitor_edits_the_message_of_a_boss_that_fled(h, services, db, clock):
    await hero(services, db, 10, "آرش", gold=5_000)
    await h.say(10, "باس", group=True)
    clock.advance(services.ctx.balance.boss_duration_seconds + 5)
    h.session.reset()
    await boss_ui.announce_expired(h.bot, services)
    assert "گریخت" in h.session.last_text()
