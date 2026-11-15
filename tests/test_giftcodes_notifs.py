import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data import notifs
from eternal_realm.game.engine import coaching
from eternal_realm.game.engine.combat import Action, Battle, Fighter, act, auto_action
from eternal_realm.game.notify import queue
from eternal_realm.game.services.giftcodes import parse_spec
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1, admin_ids=(5,)), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "warrior")


# --- gift codes --------------------------------------------------------------------------------------------------------------------
def test_the_owner_writes_a_code_in_one_line():
    spec = parse_spec("سکه=5000 کریستال=10 آیتم=سنگ آهن*5 تعداد=100 روز=7 کد=eid1405")
    assert spec["gold"] == 5000 and spec["crystal"] == 10 and spec["uses"] == 100 and spec["days"] == 7
    assert spec["code"] == "EID1405" and spec["items"] == {"iron_ore": 5}
    for bad in ("سکه=abc", "جایزه=5", "آیتم=چیزی نامعلوم*2", "سکه"):
        with pytest.raises(GameError):
            parse_spec(bad)


async def test_a_code_pays_once_per_hero_and_stops_when_its_uses_run_out(services, db):
    a, b, c = await hero(services, 11, "آرش"), await hero(services, 12, "بهرام"), await hero(services, 13, "کاوه")
    made = await services.giftcodes.create(5, parse_spec("سکه=700 کریستال=3 آیتم=سنگ آهن*2 تعداد=2 کد=TEST2"))
    before = await services.players.require(11)
    found = await services.giftcodes.redeem(a, " test2 ")  # case and spaces do not matter
    after = await services.players.require(11)
    assert found.code == made.code == "TEST2"
    assert after.gold == before.gold + 700 and after.crystal == before.crystal + 3
    async with db.read() as tx:
        assert await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = 'iron_ore'", (a.id,), 0) == 2
    with pytest.raises(GameError, match="قبلاً"):
        await services.giftcodes.redeem(a, "TEST2")  # a second tap pays nothing
    await services.giftcodes.redeem(b, "TEST2")
    with pytest.raises(GameError, match="ظرفیت"):
        await services.giftcodes.redeem(c, "TEST2")
    assert (await services.players.require(13)).gold == (await hero_gold(services, 13))
    with pytest.raises(GameError, match="وجود ندارد"):
        await services.giftcodes.redeem(c, "NOPE1234")


async def hero_gold(services, uid):
    return (await services.players.require(uid)).gold


async def test_a_code_can_expire_or_be_switched_off(services, clock):
    a = await hero(services, 21, "الف‌ب")
    await services.giftcodes.create(5, parse_spec("سکه=100 روز=1 کد=SHORT1"))
    await services.giftcodes.create(5, parse_spec("سکه=100 کد=OFF123"))
    clock.advance(2 * 86400)
    with pytest.raises(GameError, match="مهلت"):
        await services.giftcodes.redeem(a, "SHORT1")
    await services.giftcodes.set_active(5, "OFF123", False)
    with pytest.raises(GameError, match="غیرفعال"):
        await services.giftcodes.redeem(a, "OFF123")
    await services.giftcodes.set_active(5, "OFF123", True)
    await services.giftcodes.redeem(a, "OFF123")


async def test_codes_need_a_reward_and_a_fresh_name(services):
    with pytest.raises(GameError, match="جایزه"):
        await services.giftcodes.create(5, parse_spec("تعداد=3"))
    await services.giftcodes.create(5, parse_spec("سکه=1 کد=ONLY1"))
    with pytest.raises(GameError, match="از قبل"):
        await services.giftcodes.create(5, parse_spec("سکه=1 کد=ONLY1"))
    random_one = await services.giftcodes.create(5, parse_spec("سکه=1"))
    assert len(random_one.code) == 8


async def test_the_admin_panel_makes_a_code_and_the_hero_claims_it_with_a_word(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 31, "بازیکن")
    await h.panel(1, "admcode")
    assert any("ساخت کد جدید" in b for b in h.labels())
    await h.panel(1, "admask", "code_new")
    await h.say(1, "سکه=250 تعداد=5 کد=PANEL5")
    assert "PANEL5" in h.session.last_text()
    await h.panel(1, "admcode")
    assert "PANEL5" in h.session.last_text()
    gold = await hero_gold(services, 31)
    await h.say(31, "کد هدیه panel5")
    assert await hero_gold(services, 31) == gold + 250 and "کد هدیه فعال شد" in h.session.last_text()
    await h.panel(1, "admcodev", "PANEL5")
    await h.tap(1, "غیرفعال کردن")
    assert not (await services.giftcodes.get("PANEL5")).active


async def test_the_hero_can_type_a_code_after_the_button(h, services):
    await hero(services, 32, "نگار")
    await services.giftcodes.create(5, parse_spec("سکه=90 کد=BTN90"))
    await h.panel(32, "giftcode")
    gold = await hero_gold(services, 32)
    await h.say(32, "BTN90")
    assert await hero_gold(services, 32) == gold + 90


# --- notifications -----------------------------------------------------------------------------------------------------------------
def test_every_known_alert_key_has_a_category_and_the_unknown_ones_cannot_be_muted():
    assert notifs.category_of("energyfull:123") == "energy" and notifs.category_of("ach:wins:3") == "news"
    assert notifs.category_of("tip:5") == "tips" and notifs.category_of("gift_all:5") is None
    assert notifs.parse("energy,bogus,city") == {"energy", "city"} and notifs.dump({"city", "energy"}) == "energy,city"


async def test_muted_categories_are_dropped_and_the_rest_still_arrive(services, db):
    p = await hero(services, 41, "مینا")
    now = services.ctx.now()
    async with db.transaction() as tx:
        await queue(tx, p.id, "energyfull:1", "⚡ پر شد", now, "adv")
        await queue(tx, p.id, "tip:1", "💡 نکته", now)
        await queue(tx, p.id, "gift_all:1", "🎁 هدیه‌ی مدیر", now)
    assert await services.alerts.toggle(p.id, "energy") is False
    texts = [a.text for a in await services.alerts.pending()]
    assert texts == ["💡 نکته", "🎁 هدیه‌ی مدیر"]
    assert await services.alerts.pending() == []  # a muted message is gone, not delayed
    assert await services.alerts.toggle(p.id, "energy") is True
    with pytest.raises(GameError):
        await services.alerts.toggle(p.id, "bogus")


async def test_the_notification_screen_flips_each_switch_and_all_at_once(h, services):
    p = await hero(services, 42, "سارا")
    await h.panel(42, "profile")
    assert "🧰 امکانات بیشتر" in h.labels()
    await h.panel(42, "more")
    assert "🔔 اعلان‌ها" in h.labels() and "🎁 کد هدیه" in h.labels()
    await h.panel(42, "notifs")
    assert len([b for b in h.labels() if b.startswith(("✅", "⛔"))]) == len(notifs.CATEGORIES) + 1
    await h.panel(42, "notiftog", "city")
    assert "city" in await services.alerts.muted(p.id)
    await h.panel(42, "notiftog", "offers")
    assert not await services.offers.enabled(await services.players.require(42))
    await h.panel(42, "notifall", "1")
    assert await services.alerts.muted(p.id) == set() and await services.offers.enabled(await services.players.require(42))
    await h.panel(42, "notifall", "0")
    assert await services.alerts.muted(p.id) == {c.id for c in notifs.CATEGORIES}


async def test_a_muted_city_category_silences_the_village_messages_too(services, db, clock):
    from .test_city import hero as city_hero

    p = await city_hero(services, db, 43, "شهری")
    city = await services.city.found(p, "پارس", "🦁")
    await services.alerts.toggle(p.id, "city")
    async with db.transaction() as tx:
        await services.city._alert(tx, city.id, "x", services.ctx.now(), "hi")
    assert [a for a in await services.city.collect_alerts() if "hi" in a.text] == []


# --- the after-fight review ---------------------------------------------------------------------------------------------------------
def fighter(name, atk=20, hp=200):
    return Fighter(name=name, emoji="⚔️", max_hp=hp, hp=hp, atk=atk, defense=5, magic=0, speed=10, luck=0, player_id=hash(name) % 1000)


def test_the_fight_counts_damage_and_the_kind_of_every_turn(rng):
    battle = Battle.start(fighter("a"), fighter("b"), 15, rng)
    first, second = battle.current, battle.other
    act(battle, Action.ATTACK, rng)
    act(battle, Action.DEFEND, rng)
    assert first.n_attack == 1 and second.n_defend == 1 and first.dealt > 0 and second.dealt == 0


def test_a_lost_fight_without_skills_or_defence_says_so_and_a_win_gets_praise(rng):
    weak, strong = fighter("weak", atk=5, hp=90), fighter("strong", atk=40, hp=400)
    battle = Battle.start(weak, strong, 15, rng)
    while not battle.finished:
        act(battle, Action.ATTACK, rng)
    loser = 0 if battle.winner == 1 else 1
    tips = coaching.tips(battle, loser)
    assert 1 <= len(tips) <= 4 and any("قوی‌تر" in t for t in tips)
    summary = coaching.summary(battle, loser)
    assert len(summary) == 3 and "آسیب" in summary[0]
    assert coaching.tips(battle, 1 - loser)


async def test_a_lost_solo_fight_shows_why_and_build_tips(h, services, db):
    import json

    from eternal_realm.db.repos import wallet

    p = await hero(services, 51, "تازه")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 10 WHERE id = ?", (p.id,))
        await wallet.apply(tx, p.id, gold=1000, reason="t", now=services.ctx.now())
    await h.panel(51, "arenago", "normal")
    async with db.transaction() as tx:  # the hero is on his last legs
        row = await tx.fetchone("SELECT id, state FROM solo_fights WHERE player_id = ? AND status = 'active'", (p.id,))
        state = json.loads(row["state"])
        state["fighters"][0]["hp"] = 1
        state["fighters"][1]["atk"] = 10_000
        await tx.execute("UPDATE solo_fights SET state = ? WHERE id = ?", (json.dumps(state), row["id"]))
    for _ in range(6):
        if await services.solo.active(p.id) is None:
            break
        await h.panel(51, "sact", "defend")
    text = h.session.last_text()
    assert "چرا شکست خوردید" in text and "تجهیزات" in text
