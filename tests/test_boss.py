import asyncio
import json
import random

import pytest

from eternal_realm.bot import boss as boss_ui
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.bosses import BOSSES, boss_attack, boss_defense, boss_max_hp, pick_boss
from eternal_realm.game.data.classes import CLASSES
from eternal_realm.game.engine import progression
from eternal_realm.game.engine.boss_fight import Boss, Hero, is_over, run_round
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


async def squad(services, db, n=4):
    """A summoner plus ``n - 1`` friends, all signed up for the same boss."""
    names = ["آرش", "سارا", "رها", "امیر", "علی", "محمد", "نگار", "پویا", "مینا", "کیان"]
    classes = list(CLASSES)
    players = [await hero(services, db, 10 + i, names[i], cls=classes[i % 5], gold=5_000) for i in range(n)]
    view = await services.bosses.summon(players[0], CHAT)
    for p in players[1:]:
        view = await services.bosses.join(view.id, await services.players.require(p.platform_user_id))
    return players, view


async def advance_until_ended(services, clock, limit=500):
    updates = []
    for _ in range(limit):
        clock.advance(services.ctx.balance.boss_round_seconds)
        batch = await services.bosses.process_due()
        updates += batch
        if any(u.kind in ("final", "cancelled") for u in batch):
            return updates
    raise AssertionError("fight did not end")


async def edit_state(db, boss_id, change):
    async with db.transaction() as tx:
        row = await tx.fetchone("SELECT state, hp FROM bosses WHERE id = ?", (boss_id,))
        state = json.loads(row["state"])
        change(state)
        await tx.execute(
            "UPDATE bosses SET state = ?, hp = ? WHERE id = ?", (json.dumps(state), state["boss"]["hp"], boss_id)
        )


# --- summoning and sign-up ----------------------------------------------------------------------
async def test_summon_rules_and_cost(services, db, clock):
    rookie = await hero(services, db, 10, "تازه‌کار", level=1)
    with pytest.raises(GameError, match="سطح"):
        await services.bosses.summon(rookie, CHAT)

    poor = await hero(services, db, 11, "آرش", gold=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 50 WHERE id = ?", (poor.id,))
    with pytest.raises(wallet.InsufficientFunds):
        await services.bosses.summon(await services.players.require(11), CHAT)

    lead = await hero(services, db, 12, "سارا", gold=0)
    view = await services.bosses.summon(lead, CHAT)
    assert view.phase == "recruiting" and len(view.fighters) == 1 and view.fighters[0].name == "سارا"
    assert (await services.players.require(12)).gold == services.ctx.balance.start_gold - 200
    with pytest.raises(GameError, match="باس زنده"):
        await services.bosses.summon(lead, CHAT)


async def test_join_rules(services, db, clock):
    players, view = await squad(services, db, 2)
    with pytest.raises(GameError, match="همین الان"):
        await services.bosses.join(view.id, await services.players.require(11))  # already in
    capped = services.ctx.balance.__class__(**{**services.ctx.balance.__dict__, "boss_max_players": 2})
    object.__setattr__(services.ctx.settings, "balance", capped)
    third = await hero(services, db, 20, "رها")
    with pytest.raises(GameError, match="ظرفیت"):
        await services.bosses.join(view.id, third)
    clock.advance(services.ctx.balance.boss_recruit_seconds + 1)
    with pytest.raises(GameError, match="بسته شده"):
        await services.bosses.join(view.id, third)


async def test_only_the_summoner_starts_and_needs_enough_fighters(services, db):
    players, view = await squad(services, db, 2)
    with pytest.raises(GameError, match="فقط احضارکننده"):
        await services.bosses.start(view.id, await services.players.require(11))
    with pytest.raises(GameError, match="حداقل"):
        await services.bosses.start(view.id, await services.players.require(10))

    third = await hero(services, db, 20, "رها")
    await services.bosses.join(view.id, third)
    started = await services.bosses.start(view.id, await services.players.require(10))
    assert started.phase == "fighting" and started.hp == started.max_hp > 0
    with pytest.raises(GameError, match="در جریان"):
        await services.bosses.start(view.id, await services.players.require(10))
    with pytest.raises(GameError, match="بسته شده"):
        await services.bosses.join(view.id, await hero(services, db, 21, "امیر"))


async def test_more_fighters_means_a_bigger_boss(services, db):
    _, small = await squad(services, db, 3)
    big_players = [await hero(services, db, 40 + i, f"ج{i}") for i in range(6)]
    big = await services.bosses.summon(big_players[0], -777)
    for p in big_players[1:]:
        big = await services.bosses.join(big.id, p)
    a = await services.bosses.start(small.id, await services.players.require(10))
    b = await services.bosses.start(big.id, big_players[0])
    assert b.max_hp > a.max_hp * 1.7


async def test_recruiting_ends_by_itself_start_or_refund(services, db, clock):
    players, view = await squad(services, db, 4)
    clock.advance(services.ctx.balance.boss_recruit_seconds + 1)
    updates = await services.bosses.process_due()
    assert [u.kind for u in updates] == ["started"] and updates[0].view.phase == "fighting"

    lonely = await hero(services, db, 60, "تنها", gold=0)
    before = (await services.players.require(60)).gold
    view = await services.bosses.summon(lonely, -888)
    assert (await services.players.require(60)).gold == before - 200
    clock.advance(services.ctx.balance.boss_recruit_seconds + 1)
    cancelled = [u for u in await services.bosses.process_due() if u.view.chat_id == -888]
    assert cancelled and cancelled[0].kind == "cancelled" and cancelled[0].view.outcome == "cancelled"
    assert (await services.players.require(60)).gold == before  # the ritual fee came back
    assert await services.bosses.process_due() == []


# --- the automatic fight ------------------------------------------------------------------------
async def test_rounds_run_on_a_timer_and_reports_are_throttled(services, db, clock):
    players, view = await squad(services, db, 4)
    await services.bosses.start(view.id, players[0])
    assert await services.bosses.process_due() == []  # the first round is not due yet
    kinds = []
    for _ in range(8):
        clock.advance(services.ctx.balance.boss_round_seconds)
        kinds += [u.kind for u in await services.bosses.process_due()]
    assert "report" in kinds
    assert len(kinds) <= 3  # 40 seconds of fight, a report every 15 seconds at most


async def test_a_won_fight_pays_everybody_exactly_once(services, db, clock):
    players, view = await squad(services, db, 5)
    await services.bosses.start(view.id, players[0])
    await edit_state(db, view.id, lambda s: s["boss"].update(hp=300, max_hp=300, atk=3))
    updates = await advance_until_ended(services, clock)
    final = updates[-1]
    assert final.kind == "final" and final.view.outcome == "won" and final.view.status == "defeated"
    assert len(final.view.payouts) == 5 and abs(sum(p.share for p in final.view.payouts) - 1) < 1e-9
    assert final.view.payouts[0].chest == "magic_chest"
    async with db.read() as tx:
        rewards = await tx.scalar("SELECT COUNT(*) FROM transactions WHERE reason = 'boss_reward'")
    assert rewards == 5
    assert await services.bosses.process_due() == []
    assert await services.bosses.active(CHAT) is None


async def test_a_wiped_out_squad_still_gets_a_consolation(services, db, clock):
    players, view = await squad(services, db, 4)
    await services.bosses.start(view.id, players[0])
    await edit_state(db, view.id, lambda s: s["boss"].update(hp=10**9, max_hp=10**9, atk=9_999))
    final = (await advance_until_ended(services, clock))[-1]
    assert final.view.outcome == "lost" and final.view.status == "expired"
    assert final.view.payouts and all(p.chest is None for p in final.view.payouts)
    assert all(p.gold >= 10 for p in final.view.payouts)


async def test_a_boss_that_outlasts_the_time_limit_flees(services, db, clock):
    players, view = await squad(services, db, 3)
    await services.bosses.start(view.id, players[0])
    await edit_state(db, view.id, lambda s: s["boss"].update(hp=10**9, max_hp=10**9, atk=1))
    await edit_state(db, view.id, lambda s: [x.update(hp=10**6, max_hp=10**6) for x in s["heroes"]])  # only the clock can end it
    clock.advance(services.ctx.balance.boss_fight_seconds + 1)
    ended = [u for u in await services.bosses.process_due() if u.kind == "final"]
    assert ended and ended[0].view.outcome == "fled"


async def test_the_fight_survives_a_restart(services, db, clock, rng):
    players, view = await squad(services, db, 4)
    await services.bosses.start(view.id, players[0])
    clock.advance(30)
    await services.bosses.process_due()
    reborn = Services.build(AppContext(db, services.ctx.settings, clock=clock, rng=rng))  # a fresh process
    clock.advance(10)
    await reborn.bosses.process_due()
    live = await reborn.bosses.active(CHAT)
    assert live is None or live.round >= 6  # it carried on from the stored state, not from zero


async def test_two_processors_at_once_never_pay_twice(services, db, clock):
    players, view = await squad(services, db, 4)
    await services.bosses.start(view.id, players[0])
    await edit_state(db, view.id, lambda s: s["boss"].update(hp=1, max_hp=1))
    clock.advance(services.ctx.balance.boss_round_seconds)
    await asyncio.gather(services.bosses.process_due(), services.bosses.process_due())
    async with db.read() as tx:
        rewards = await tx.scalar("SELECT COUNT(*) FROM transactions WHERE reason = 'boss_reward'")
    assert rewards == 4


# --- the engine ---------------------------------------------------------------------------------
def make_hero(i, cls, level=5):
    st = progression.base_stats("human", cls, level)
    return Hero(i, f"h{i}", cls, st.hp, st.hp, st.atk, st.defense, st.magic, st.speed, st.luck)


def test_every_class_deals_damage_and_hp_stays_in_bounds():
    rng = random.Random(1)
    for cls in CLASSES:
        boss = Boss("b", 10**6, 10**6, 20, 6)
        heroes = [make_hero(0, cls), make_hero(1, "warrior")]
        for _ in range(30):
            run_round(boss, heroes, rng)
        assert heroes[0].damage > 0, cls
        assert all(0 <= h.hp <= h.max_hp for h in heroes) and boss.hp >= 0


def test_guardians_protect_allies():
    rng = random.Random(2)
    boss = Boss("b", 10**6, 10**6, 25, 6)
    heroes = [make_hero(0, "guardian"), make_hero(1, "mage"), make_hero(2, "archer")]
    texts = []
    for _ in range(40):
        texts += [t for _, t in run_round(boss, heroes, rng)]
    assert heroes[0].absorbed > 0 and any("جلوی ضربه‌ی باس" in t for t in texts)


def test_rare_events_happen():
    rng = random.Random(4)
    boss = Boss("b", 10**7, 10**7, 40, 6)
    heroes = [make_hero(i, c) for i, c in enumerate(CLASSES)]
    texts = []
    for _ in range(150):
        texts += [t for _, t in run_round(boss, heroes, rng)]
        if is_over(boss, heroes):
            break
    joined = " ".join(texts)
    from tests.test_ui_rules import bad_lines

    assert not [line for text in texts for line in bad_lines(text)]  # one emoji per line in the report too
    for marker in ("نقطه‌ی ضعف", "از پا افتاد", "ضربه‌ی کاری", "جاخالی"):
        assert marker in joined, marker


def fight(n, level, kind, seed):
    rng = random.Random(seed)
    classes = list(CLASSES)
    heroes = [make_hero(i, classes[i % 5], level) for i in range(n)]
    hp = boss_max_hp(kind, n, level)
    boss = Boss(kind.name, hp, hp, boss_attack(kind, level), boss_defense(level),
                special=kind.special, weak_class=kind.weak_class)
    while boss.round < 400:
        run_round(boss, heroes, rng)
        if outcome := is_over(boss, heroes):
            return outcome == "won"
    return False


def win_rate(n, level, samples=40):
    return sum(fight(n, level, pick_boss(level, random.Random(s)), s) for s in range(samples)) / samples


def test_balance_group_size_matters_and_big_groups_almost_always_win():
    for level in (5, 10, 20, 30):
        three, five, ten = win_rate(3, level), win_rate(5, level), win_rate(10, level)
        assert ten >= 0.95, (level, ten)
        assert five >= 0.65, (level, five)
        assert three < five or three > 0.95, (level, three, five)  # more fighters help, except trivial early bosses


def test_the_roster_is_large_varied_and_consistent():
    from eternal_realm.game.data.bosses import ARCHETYPES, ELEMENTS, boss_by_id

    assert len(BOSSES) >= 40 and len(ELEMENTS) >= 8
    assert len({b.id for b in BOSSES}) == len({b.name for b in BOSSES}) == len(BOSSES)
    assert len(BOSSES) == len(ELEMENTS) * len(ARCHETYPES)
    for b in BOSSES:
        assert b.weak_class in CLASSES and b.min_level >= 3 and b.story and b.special
        assert boss_by_id(b.id) is b
    assert {b.element.id for b in BOSSES} == {e.id for e in ELEMENTS}


def test_picked_bosses_fit_the_level_and_vary():
    rng = random.Random(0)
    seen = set()
    for level in (3, 10, 25, 45):
        for _ in range(60):
            boss = pick_boss(level, rng)
            assert boss.min_level <= max(level, BOSSES[0].min_level)
            seen.add(boss.id)
    assert len(seen) >= 15


def test_the_weak_class_hits_harder():
    boss_type = BOSSES[0]
    results = {}
    for cls in ("archer", "guardian"):
        dealt = 0
        for seed in range(200):
            rng = random.Random(seed)
            boss = Boss("b", 10**9, 10**9, 1, 6, weak_class=cls)
            hero = make_hero(0, cls)
            hero.atk = hero.magic = 100
            run_round(boss, [hero], rng)
            dealt += hero.damage
        results[cls] = dealt
    assert results["archer"] > 0 and results["guardian"] > 0 and boss_type


# --- through the bot ----------------------------------------------------------------------------
async def test_full_fight_in_a_group_with_buttons(h, services, db, clock):
    names = ["آرش", "سارا", "رها", "امیر"]
    for i, name in enumerate(names):
        await hero(services, db, 10 + i, name, gold=5_000, cls=list(CLASSES)[i % 5])
    await h.say(10, "احضار باس", group=True)
    assert "بیدار شده است" in h.session.last_text() and "(uid:10)" in h.session.last_text()
    join = h.button_data("پیوستن")
    start = h.button_data("شروع")

    await h.click(10, start, group=True)  # one fighter is not enough
    assert any("حداقل" in a.get("text", "") for a in h.session.callback_answers())
    await h.click(11, join, group=True)
    await h.click(11, join, group=True)  # a double tap is harmless
    await h.click(12, join, group=True)
    assert "سارا" in h.session.last_text() and "رها" in h.session.last_text()
    await h.click(11, start, group=True)  # only the summoner may start
    assert any("فقط احضارکننده" in a.get("text", "") for a in h.session.callback_answers())

    await h.click(10, start, group=True)
    assert "نبرد آغاز شد" in h.session.last_text() and "ویژگی باس" in h.session.last_text()
    assert any(name == "deleteMessage" for name, _ in h.session.calls)  # the sign-up message is gone
    assert not h.session.sent("sendMessage")[-1].get("reply_markup")

    boss_id = (await services.bosses.active(-500)).id
    await edit_state(db, boss_id, lambda s: s["boss"].update(hp=200, max_hp=200, atk=3))
    for _ in range(300):
        clock.advance(services.ctx.balance.boss_round_seconds)
        await boss_ui.apply_updates(h.bot, services, await services.bosses.process_due())
        if await services.bosses.active(-500) is None:
            break
    assert "شکست خورد" in h.session.last_text() and "آسیب" in h.session.last_text()
    assert "(uid:" in h.session.last_text()
    deletes = [c for c in h.session.calls if c[0] == "deleteMessage"]
    assert len(deletes) >= 2  # the sign-up message, then the live fight message
    chips = h.labels()
    assert any("پیروزی" in label for label in chips) and any("🪙" in label for label in chips)


async def test_boss_word_shows_the_live_boss_and_admins_can_disable_it(h, services, db):
    await hero(services, db, 10, "آرش", gold=5_000)
    await h.say(10, "باس", group=True)
    first = len(h.session.sent("sendMessage"))
    await h.say(10, "باس", group=True)  # still recruiting: the same boss is brought back down
    assert len(h.session.sent("sendMessage")) == first + 1 and any("پیوستن" in t for t in h.labels())
    h.session.chat_admins.add(99)
    await h.say(99, "غیرفعال باس", group=True)
    assert "غیرفعال شد" in h.session.last_text()


async def test_the_panel_button_summons_in_groups_only(h, services, db):
    await hero(services, db, 10, "آرش", gold=5_000)
    await h.say(10, "قلمرو", group=True)
    assert not any("باس گروه" in t for t in h.labels())  # the short group menu leaves it out; the word «باس» still works
    await h.panel(10, "boss", group=True)
    assert "احضار" in h.session.last_text()
    await h.tap(10, "احضار", group=True)
    assert any("بیدار شده است" in t for t in h.session.texts())
    assert await services.bosses.active(CHAT) is not None
    await h.say(10, "قلمرو")
    assert not any("باس گروه" in t for t in h.labels())


async def test_a_lost_boss_comes_back_angrier_and_pays_more(services, db, clock):
    players, view = await squad(services, db, 3)
    assert not view.revenge and await services.bosses.revenge_boss(CHAT) is None
    await services.bosses.start(view.id, players[0])
    await edit_state(db, view.id, lambda s: s["boss"].update(hp=10**9, max_hp=10**9, atk=1))
    await edit_state(db, view.id, lambda s: [x.update(hp=10**6, max_hp=10**6) for x in s["heroes"]])
    clock.advance(services.ctx.balance.boss_fight_seconds + 1)
    assert [u for u in await services.bosses.process_due() if u.kind == "final"][0].view.outcome == "fled"

    owed = await services.bosses.revenge_boss(CHAT)
    assert owed is not None and owed.id == view.type.id
    clock.advance(services.ctx.balance.boss_cooldown_seconds + 1)
    again = await services.bosses.summon(await services.players.require(players[0].platform_user_id), CHAT)
    assert again.revenge and again.type.id == view.type.id
    assert "انتقام" in boss_ui.text_for(services, again)
    await services.bosses.join(again.id, await services.players.require(players[1].platform_user_id))
    await services.bosses.join(again.id, await services.players.require(players[2].platform_user_id))
    started = await services.bosses.start(again.id, await services.players.require(players[0].platform_user_id))
    plain_hp = boss_max_hp(again.type, 3, started.level)
    assert started.revenge and started.max_hp >= round(plain_hp * 0.95 * 1.15 * 0.3)
    # one rematch per defeat: when this one is lost too, the next summon is an ordinary boss again
    await edit_state(db, again.id, lambda s: s["boss"].update(hp=10**9, max_hp=10**9, atk=1))
    await edit_state(db, again.id, lambda s: [x.update(hp=10**6, max_hp=10**6) for x in s["heroes"]])
    clock.advance(services.ctx.balance.boss_fight_seconds + 1)
    await services.bosses.process_due()
    assert await services.bosses.revenge_boss(CHAT) is None


async def test_the_revenge_window_closes_after_a_day(services, db, clock):
    players, view = await squad(services, db, 3)
    await services.bosses.start(view.id, players[0])
    await edit_state(db, view.id, lambda s: s["boss"].update(hp=10**9, max_hp=10**9, atk=1))
    await edit_state(db, view.id, lambda s: [x.update(hp=10**6, max_hp=10**6) for x in s["heroes"]])
    clock.advance(services.ctx.balance.boss_fight_seconds + 1)
    await services.bosses.process_due()
    assert await services.bosses.revenge_boss(CHAT) is not None
    clock.advance(25 * 3600)
    assert await services.bosses.revenge_boss(CHAT) is None


async def test_every_summoning_has_a_hidden_strength_tier_that_changes_the_odds(services, db, clock):
    from eternal_realm.game.data.bosses import TIERS, roll_tier, squad_scaling, tier_by_id

    seen = set()
    rng = random.Random(5)
    for _ in range(400):
        seen.add(roll_tier(rng).id)
    assert seen == {t.id for t in TIERS}  # all five tiers happen
    assert tier_by_id("nonsense").id == "normal"
    plain_hp, plain_atk = squad_scaling(1.3, 3)
    geared_hp, geared_atk = squad_scaling(2.0, 3)
    assert geared_hp > plain_hp and geared_atk > plain_atk  # a stronger squad meets a stronger boss
    assert squad_scaling(1.3, 8)[1] > squad_scaling(1.3, 3)[1]  # and more fighters make it hit harder

    players, view = await squad(services, db, 4)
    assert view.tier in {t.id for t in TIERS}
    async with db.transaction() as tx:
        await tx.execute("UPDATE bosses SET state = ? WHERE id = ?", (json.dumps({"tier": "legend"}), view.id))
    started = await services.bosses.start(view.id, players[0])
    assert started.tier == "legend"
    assert "افسانه‌ای" in boss_ui.text_for(services, started)  # revealed once the fight begins


async def test_a_legendary_boss_beats_a_small_squad(services, db, clock):
    players, view = await squad(services, db, 3)
    async with db.transaction() as tx:
        await tx.execute("UPDATE bosses SET state = ? WHERE id = ?", (json.dumps({"tier": "legend"}), view.id))
    await services.bosses.start(view.id, players[0])
    updates = await advance_until_ended(services, clock)
    final = [u for u in updates if u.kind == "final"][-1]
    assert final.view.outcome in ("lost", "fled")  # bosses can and do win


def test_long_fights_get_harder_and_the_dreaded_blow_exists():
    rng = random.Random(2)
    boss = Boss("باس", 10**9, 10**9, 50, 10)
    heroes = [Hero(i, f"h{i}", "warrior", 10**6, 10**6, 20, 20, 5, 10, 5) for i in range(4)]
    start_atk, texts = boss.atk, []
    for _ in range(300):
        texts += [t for _, t in run_round(boss, heroes, rng)]
        for h in heroes:
            h.hp, h.alive = h.max_hp, True
    assert boss.atk > start_atk * 1.3  # the boss kept growing angrier as the fight dragged on
    assert any("حمله‌ی نابودگر" in t for t in texts) and any("خشمگین‌تر شد" in t for t in texts)
