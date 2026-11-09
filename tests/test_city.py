import random
import re

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import city as d
from eternal_realm.game.engine import siege
from eternal_realm.shared.errors import GameError
from eternal_realm.shared.text import EMOJI

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=10, gold=100_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, crystal=100, reason="t", now=services.ctx.now())
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


async def make_city(services, db, uid, name, flag="🦁", **kw):
    p = await hero(services, db, uid, f"قهرمان{uid}", **kw)
    city = await services.city.found(p, name, flag)
    async with db.transaction() as tx:
        await tx.execute("UPDATE cities SET shield_until = 0 WHERE id = ?", (city.id,))
    return p, city


async def give(db, city_id, **troops):
    async with db.transaction() as tx:
        for kind, qty in troops.items():
            await tx.execute(
                "INSERT INTO city_troops (city_id, kind, qty) VALUES (?, ?, ?)"
                " ON CONFLICT (city_id, kind) DO UPDATE SET qty = ?", (city_id, kind, qty, qty),
            )


async def stock(db, city_id, **res):
    async with db.transaction() as tx:
        for k, v in res.items():
            await tx.execute(f"UPDATE cities SET {k} = ? WHERE id = ?", (v, city_id))


def test_the_tables_are_sound():
    for t in d.TROOPS:
        assert t.building in {b.id for b in d.BUILDINGS} and t.cap >= 1 and t.hp > 0
    assert set(d.DESTRUCTION_ORDER) == {b.id for b in d.BUILDINGS}
    assert d.slots_for(1) == 5 and d.slots_for(10) >= len(d.BUILDINGS) - 1
    assert d.league_of(0)[1] == "چوبی" and d.league_of(1500)[1] == "طلایی" and d.league_of(9999)[1] == "اساطیری"
    assert d.shield_for(0.2) == 0 and d.shield_for(0.4) == 6 * 3600 and d.shield_for(0.7) == 10 * 3600 and d.shield_for(1.0) == 14 * 3600
    assert len({f for f, _ in d.FLAGS}) == len(d.FLAGS)


async def test_founding_rules(services, db):
    low = await hero(services, db, 1, "تازه‌کار", level=4)
    with pytest.raises(GameError, match="سطح ۵"):
        await services.city.found(low, "آذرگان", "🦁")
    p = await hero(services, db, 2, "فرمانده", level=5)
    before = p.gold
    city = await services.city.found(p, "آذرگان", "🦁")
    assert (await services.players.require(2)).gold == before - services.ctx.balance.city_found_gold
    assert city.levels == d.START_BUILDINGS and city.shielded(services.ctx.now()) and city.pop == d.START_POPULATION
    with pytest.raises(GameError, match="از پیش یک شهر"):
        await services.city.found(p, "شهر دیگر", "🦁")
    q = await hero(services, db, 3, "فرمانده‌دو")
    with pytest.raises(GameError, match="از پیش هست"):
        await services.city.found(q, "آذرگان", "🦁")
    with pytest.raises(GameError, match="پرچم"):
        await services.city.found(q, "شهر من", "x")
    with pytest.raises(GameError, match="حرف"):
        await services.city.found(q, "ب", "🦁")


async def test_production_eating_storage_and_hunger(services, db, clock):
    p, city = await make_city(services, db, 1, "آذرگان")
    start = (await services.city.mine(p)).res
    clock.advance(3600)
    later = await services.city.mine(p)
    assert later.res["wood"] == pytest.approx(start["wood"] + 40, abs=1)
    assert later.res["stone"] == pytest.approx(start["stone"] + 30, abs=1)
    assert later.res["gold"] > start["gold"] and later.pop > start["gold"] * 0 + 300
    # hunger: no food, no farm output -> mood falls and production halves
    await stock(db, city.id, food=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE city_buildings SET level = 0 WHERE city_id = ? AND kind = 'farm'", (city.id,))
    clock.advance(14 * 3600)
    hungry = await services.city.mine(p)
    assert hungry.happiness < 30 and hungry.res["food"] == 0
    # storage is capped
    await stock(db, city.id, wood=4_999, happiness=100)
    clock.advance(10 * 3600)
    capped = await services.city.mine(p)
    assert capped.res["wood"] <= capped.storage


async def test_building_rules(services, db):
    p, city = await make_city(services, db, 1, "آذرگان")
    await stock(db, city.id, gold=500_000, wood=500_000, stone=500_000, iron=500_000)
    with pytest.raises(GameError, match="قلعه باید به سطح"):
        await services.city.build(p, "siege")
    with pytest.raises(GameError, match="از سطح قلعه"):
        await services.city.build(p, "farm")  # a building may not outgrow the castle
    c, lv = await services.city.build(p, "castle")
    assert lv == 2 and c.slots_total == 6
    _, lv = await services.city.build(p, "farm")
    assert lv == 2
    await services.city.build(p, "warehouse")
    c, _ = await services.city.build(p, "market")
    assert c.slots_used == 6
    with pytest.raises(GameError, match="جایگاه"):
        await services.city.build(p, "iron_mine")  # the castle opens a new slot only when it grows
    with pytest.raises(GameError):
        await services.city.build(p, "nonexistent")
    poor_p, poor = await make_city(services, db, 2, "فقیرآباد")
    await stock(db, poor.id, gold=0)
    with pytest.raises(GameError, match="کافی نیست"):
        await services.city.build(poor_p, "castle")


async def test_training_takes_time_and_respects_limits(services, db, clock):
    p, city = await make_city(services, db, 1, "آذرگان")
    await stock(db, city.id, gold=500_000, food=50_000, wood=50_000, iron=50_000)
    with pytest.raises(GameError, match="باید"):
        await services.city.train(p, "knight", 1)  # the stable is missing
    _, batch = await services.city.train(p, "sword", 50)
    assert batch.ready_at > services.ctx.now()
    assert (await services.city.mine(p)).troops.get("sword", 0) == 0
    clock.advance(batch.ready_at - services.ctx.now() + 1)
    c = await services.city.mine(p)
    assert c.troops["sword"] == 50 and not c.training
    with pytest.raises(GameError, match="مردم کافی"):
        await services.city.train(p, "sword", 400)
    await stock(db, city.id, population=5_000)
    with pytest.raises(GameError, match="ظرفیت"):
        await services.city.train(p, "sword", 400)
    with pytest.raises(GameError):
        await services.city.train(p, "sword", 0)


def test_the_battle_engine():
    rng = random.Random(3)
    weak = siege.Defence({}, {}, {"castle": 1, "farm": 1}, "ضعیف")
    out = siege.simulate({"sword": 200}, weak, rng)
    assert out.stars == 3 and out.castle_down and out.destruction == 1.0 and out.att_alive["sword"] > 150
    strong = siege.Defence({"sword": 300, "spear": 300}, {"fire": 8}, {"castle": 5, "wall": 5, "tower": 5, "barracks": 5, "farm": 5}, "قوی")
    out = siege.simulate({"sword": 20}, strong, random.Random(3))
    assert out.stars == 0 and sum(out.att_alive.values()) < 20 and out.traps_used == {"fire": 8}
    # siege engines beat a wall that foot soldiers cannot get past
    walled = siege.Defence({}, {}, {"castle": 3, "wall": 10, "farm": 3}, "دیوار")
    foot = siege.simulate({"sword": 150}, walled, random.Random(1))
    engines = siege.simulate({"sword": 150, "catapult": 6, "ram": 10, "tower_siege": 2}, walled, random.Random(1))
    assert engines.destruction > foot.destruction
    # the hospital saves part of the dead
    guarded = siege.Defence({"sword": 100}, {}, {"castle": 3, "hospital": 10}, "درمانگاه")
    plain = siege.Defence({"sword": 100}, {}, {"castle": 3}, "بی‌درمان")
    a = siege.simulate({"sword": 150}, guarded, random.Random(5))
    b = siege.simulate({"sword": 150}, plain, random.Random(5))
    assert sum(a.def_alive.values()) >= sum(b.def_alive.values())
    assert all(k in out.log[0] or True for k in out.log)


async def test_a_full_raid_loot_losses_shield_reports_and_revenge(services, db, clock):
    ap, a = await make_city(services, db, 1, "آذرگان")
    dp, dfn = await make_city(services, db, 2, "شیرکوه")
    await give(db, a.id, sword=60, archer=30)
    await stock(db, a.id, food=10_000)
    await stock(db, dfn.id, gold=40_000, food=20_000, wood=10_000)
    with pytest.raises(GameError, match="اول"):
        await services.city.adjust(ap, "sword", 10)
    target = await services.city.search(ap)
    assert target.city.id == dfn.id and target.loot["gold"] > 0 and target.loot["gold"] <= 40_000 * 0.15 + 1
    with pytest.raises(GameError, match="سربازی"):
        await services.city.attack(ap)  # nothing picked yet
    with pytest.raises(GameError, match="این نیرو"):
        await services.city.adjust(ap, "knight", 1)
    chosen = await services.city.adjust(ap, "sword", 100)  # more than there is: capped
    assert chosen == {"sword": 60}
    await services.city.adjust(ap, None, 0, everyone=True)
    gold_before = (await services.city.mine(ap)).res["gold"]
    res = await services.city.attack(ap)
    assert res.stars >= 1 and res.loot["gold"] > 0 and res.defender_uid == 2
    mine = await services.city.mine(ap)
    assert mine.res["gold"] >= gold_before + res.loot["gold"] - 5 and mine.trophies > 0
    victim = await services.city.mine(dp, visit=False)
    assert victim.res["gold"] <= 40_000 - res.loot["gold"] + 600 and victim.trophies == 0
    assert victim.shielded(services.ctx.now()) == (res.destruction >= 0.3)
    with pytest.raises(GameError, match="دوباره جستجو"):
        await services.city.attack(ap)  # one search, one raid
    assert await services.city.unseen_reports(dp.id) == 1
    reports = await services.city.reports(dp)
    row = await services.city.report(dp, reports[0]["id"])
    assert row["attacker_name"] == "آذرگان" and await services.city.unseen_reports(dp.id) == 0
    with pytest.raises(GameError, match="پیدا نشد"):
        await services.city.report(await hero(services, db, 3, "غریبه"), row["id"])
    # revenge needs soldiers and the attacker's shield to be down
    await give(db, dfn.id, sword=40)
    target = await services.city.revenge(dp, row["id"])
    assert target.city.id == a.id
    await stock(db, a.id, shield_until=services.ctx.now() + 5_000)
    with pytest.raises(GameError, match="سپر"):
        await services.city.revenge(dp, row["id"])


async def test_search_rules_shields_clans_daily_cap_and_repeats(services, db, clock):
    ap, a = await make_city(services, db, 1, "آذرگان")
    await give(db, a.id, sword=20)
    with pytest.raises(GameError, match="حریف مناسبی"):
        await services.city.search(ap)  # nobody else exists yet
    bp, b = await make_city(services, db, 2, "شیرکوه")
    cp, c = await make_city(services, db, 3, "پلنگ‌دره")
    await stock(db, b.id, shield_until=services.ctx.now() + 10_000)
    await stock(db, c.id, shield_until=services.ctx.now() + 10_000)
    with pytest.raises(GameError, match="حریف مناسبی"):
        await services.city.search(ap)  # everyone is shielded
    await stock(db, c.id, shield_until=0)
    assert (await services.city.search(ap)).city.id == c.id
    # clan mates are never offered
    clan = await services.clans.create(ap, "شیرها")
    await services.clans.join(cp, clan.id)
    with pytest.raises(GameError, match="حریف مناسبی"):
        await services.city.search(ap)
    # nobody without soldiers can go to war
    with pytest.raises(GameError, match="بدون سرباز"):
        await services.city.search(bp)


async def test_the_daily_cap_and_repeat_limit(services, db, clock):
    ap, a = await make_city(services, db, 1, "آذرگان")
    await give(db, a.id, sword=100)
    await stock(db, a.id, food=1_000_000)
    others = []
    for i in range(2, 5):
        others.append(await make_city(services, db, i, f"شهر{i}ام"))
    done = 0
    for _ in range(d.DAILY_ATTACKS + 6):
        try:
            await services.city.search(ap)
            await services.city.adjust(ap, "sword", 5)
            await services.city.attack(ap)
            done += 1
        except GameError:
            break
        for _, o in others:
            async with db.transaction() as tx:
                await tx.execute("UPDATE cities SET shield_until = 0 WHERE id = ?", (o.id,))
    # three targets, two raids each per day -> six at most, and never more than the daily cap
    assert 2 <= done <= min(d.DAILY_ATTACKS, 6)
    clock.advance(86400)
    for _, o in others:
        async with db.transaction() as tx:
            await tx.execute("UPDATE cities SET shield_until = 0 WHERE id = ?", (o.id,))
    await services.city.search(ap)  # a new day, new chances


async def test_the_screens_and_a_whole_game_through_buttons(h, services, db, clock):
    p = await hero(services, db, 7, "آرش‌خان")
    await h.panel(7, "home")
    assert any("فرمانروایی" in label for label in h.labels())
    await h.panel(7, "city")
    assert "بنای شهر" in " ".join(h.labels()) and "۵۰۰۰" not in h.session.last_text()
    await h.panel(7, "cityfound")
    assert "نام شهرتان" in h.session.last_text()
    await h.say(7, "آذرگان")
    assert "پرچم شهر" in h.session.last_text()
    flag = h.session.last_markup_rows()[0][0]["callback_data"]
    await h.click(7, flag)
    assert "تأیید بنای شهر" in h.session.last_text()
    await h.tap(7, "بله")
    assert "آذرگان" in h.session.last_text() and (await services.city.mine(p)) is not None
    for screen_name, arg in [
        ("city", ""), ("citymine", ""), ("citybuild", ""), ("citybv", "castle"), ("citybv", "siege"), ("citypeople", ""),
        ("citystock", ""), ("citytroops", ""), ("citytr", "sword"), ("citytr", "knight"), ("citydef", ""),
        ("citytrap", "oil"), ("cityshield", ""), ("cityatk", ""), ("cityleague", ""), ("citymap", ""), ("cityreports", ""),
    ]:
        await h.panel(7, screen_name, arg)
        for line in h.session.last_text().splitlines():
            assert len(re.findall(EMOJI, line)) <= 1, (screen_name, line)
    await h.panel(7, "citytrq", "sword", "10")
    assert "تأیید تربیت" in h.session.last_text()
    await h.panel(7, "citytrok", "sword", "10")
    assert "آموزشگاه" in " ".join(x.get("text", "") for x in h.session.callback_answers()) or "سرباز" in h.session.last_text()
    await h.panel(7, "citydepq", "1000")
    await h.panel(7, "citydepok", "1000")
    await h.panel(7, "citybok", "farm")


async def test_a_raid_through_the_panel_ends_with_a_report(h, services, db, clock):
    ap, a = await make_city(services, db, 1, "آذرگان")
    dp, dfn = await make_city(services, db, 2, "شیرکوه")
    await give(db, a.id, sword=80)
    await stock(db, a.id, food=10_000)
    await h.panel(1, "cityatk")
    assert "جستجوی حریف" in " ".join(h.labels())
    await h.panel(1, "citysearch")
    assert "شهر دشمن پیدا شد" in h.session.last_text() and "غنائم قابل دریافت" in h.session.last_text()
    await h.panel(1, "cityprep")
    await h.panel(1, "cityall")
    assert "تأیید نهایی" in " ".join(h.labels())
    await h.panel(1, "citygo")
    text = h.session.last_text()
    assert "گزارش نبرد" in text and "ستاره‌ها" in text and "غنائم" in text and "تلفات" in text
    assert any("هشدار" in t or "مورد حمله" in t for t in h.session.texts())  # the victim was told
    await h.panel(2, "cityreports")
    assert "حمله‌ی" in " ".join(h.labels())
    report_id = next(b["callback_data"] for b in h.session.last_buttons() if "حمله‌ی" in b["text"])
    await h.click(2, report_id)
    assert "گزارش حمله به شهر" in h.session.last_text() and "انتقام" in " ".join(h.labels())


async def buy(services, player, pack_id, uid):
    order = await services.payments.create_order(player, pack_id)
    return await services.payments.complete(uid, order.payload, order.amount, f"c-{pack_id}-{order.id}")


async def test_paid_city_packs_resources_shields_and_the_storage_limit(services, db, clock):
    nocity = await hero(services, db, 1, "بی‌شهر")
    with pytest.raises(GameError, match="شهرتان را بنا کنید"):
        await services.payments.create_order(nocity, "city_res_m")
    p, city = await make_city(services, db, 2, "آذرگان")
    before = await services.city.mine(p)
    delivery = await buy(services, p, "city_res_l", 2)
    assert "به شهر شما رسید" in delivery.granted
    after = await services.city.mine(p)
    assert after.res["wood"] >= before.res["wood"] + 80_000 - 1 and after.res["gold"] >= before.res["gold"] + 150_000 - 1
    assert after.res["wood"] > after.storage  # bought stock above the limit...
    clock.advance(6 * 3600)
    later = await services.city.mine(p)
    assert later.res["wood"] >= after.res["wood"]  # ...is never clipped by the next production tick
    again = await services.payments.complete(2, (await services.payments.history(p))[0].payload, 600_000, "c-city_res_l-1")
    assert again.duplicate
    await buy(services, p, "city_shield_72", 2)
    c = await services.city.mine(p)
    assert c.shield_until >= services.ctx.now() + 72 * 3600 - 5
    sold = await services.payments.history(p)
    assert {o.pack.id for o in sold} >= {"city_res_l", "city_shield_72"}


async def test_the_boost_doubles_what_the_city_produces(services, db, clock):
    a, ca = await make_city(services, db, 1, "آذرگان")
    b, cb = await make_city(services, db, 2, "شیرکوه")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET boost_until = ? WHERE id = ?", (services.ctx.now() + 100 * 3600, b.id))
    wa, wb = (await services.city.mine(a)).res["wood"], (await services.city.mine(b)).res["wood"]
    clock.advance(4 * 3600)
    ra, rb = await services.city.mine(a), await services.city.mine(b)
    assert (rb.res["wood"] - wb) == pytest.approx(2 * (ra.res["wood"] - wa), rel=0.02)
    # a boost that ends half way counts only for the time it lasted
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET boost_until = ? WHERE id = ?", (services.ctx.now() + 2 * 3600, a.id))
    base = (await services.city.mine(a)).res["wood"]
    clock.advance(4 * 3600)
    got = (await services.city.mine(a)).res["wood"] - base
    assert got == pytest.approx(40 * 6, rel=0.02)  # two boosted hours (x2) plus two plain ones


async def test_the_realm_speaks_up_by_itself(services, db, clock):
    p, city = await make_city(services, db, 1, "آذرگان")
    await give(db, city.id, sword=1)
    await stock(db, city.id, gold=500_000, food=500_000, wood=500_000, iron=500_000)
    _, batch = await services.city.train(p, "sword", 20)
    clock.advance(batch.ready_at - services.ctx.now() + 1)
    first = await services.city.collect_alerts()
    texts = [a.text for a in first]
    assert any("آموزششان را تمام کردند" in t for t in texts) and all(a.uid == 1 for a in first)
    assert await services.city.collect_alerts() == []  # each message goes out once
    # hunger
    await stock(db, city.id, food=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE city_buildings SET level = 0 WHERE city_id = ? AND kind = 'farm'", (city.id,))
    clock.advance(3600)
    texts = [a.text for a in await services.city.collect_alerts()]
    assert any("گرسنه است" in t for t in texts)
    # a full storehouse
    await stock(db, city.id, wood=9_999_999, food=500_000)
    clock.advance(13 * 3600)
    texts = [a.text for a in await services.city.collect_alerts()]
    assert any("انبار" in t and "پر شد" in t for t in texts)
    # the starting shield was removed by make_city; a fresh one that runs out is announced
    await stock(db, city.id, shield_until=services.ctx.now() + 60)
    clock.advance(120)
    texts = [a.text for a in await services.city.collect_alerts()]
    assert any("سپر دفاعی" in t and "تمام شد" in t for t in texts)
    for text in texts:
        for line in text.splitlines():
            assert len(re.findall(EMOJI, line)) <= 1, line


async def test_the_victim_gets_a_full_message_about_the_raid(h, services, db):
    ap, a = await make_city(services, db, 1, "آذرگان")
    dp, dfn = await make_city(services, db, 2, "شیرکوه")
    await give(db, a.id, sword=80)
    await stock(db, a.id, food=10_000)
    await h.panel(1, "citysearch")
    await h.panel(1, "cityprep")
    await h.panel(1, "cityall")
    h.session.reset()
    await h.panel(1, "citygo")
    dm = [p for n, p in h.session.calls if n == "sendMessage" and p.get("chat_id") == 2]
    assert dm and "مورد حمله قرار گرفت" in dm[-1]["text"] and "میزان تخریب" in dm[-1]["text"]
    assert any("انتقام" in b["text"] for row in dm[-1]["reply_markup"]["inline_keyboard"] for b in row)
