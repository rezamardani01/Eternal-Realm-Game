import pytest

from eternal_realm.bot import events as events_ui
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


async def hero(services, db, uid, name, level=5, gold=3_000):
    p = await services.players.register(uid, f"u{uid}", name, "dragonborn", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def active_group(services, db, players):
    await services.groups.touch(CHAT, "گروه")
    async with db.transaction() as tx:
        for p in players:
            await tx.execute(
                "INSERT INTO group_members (chat_id, player_id, points, last_active) VALUES (?, ?, 0, ?)",
                (CHAT, p.id, services.ctx.now()),
            )


async def test_mystery_chest_opens_for_exactly_one_player(services, db, clock):
    a, b = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    view = await services.events.spawn(CHAT, "mystery_chest")
    assert view is not None and view.status == "active"
    won = None
    for _ in range(60):
        clock.advance(25)
        for p in (a, b):
            if won is None:
                try:
                    view, ok = await services.events.try_open(view.id, p)
                except GameError:
                    continue
                if ok:
                    won = p
    assert won is not None
    with pytest.raises(GameError):
        await services.events.try_open(view.id, b)
    stored = await services.events.get(view.id)
    assert stored.status == "done" and stored.state["winner"] == won.name
    assert "گشوده" in events_ui.text_for(stored)


async def test_chest_try_has_a_gap(services, db):
    a = await hero(services, db, 1, "آرش")
    view = await services.events.spawn(CHAT, "mystery_chest")
    await services.events.try_open(view.id, a)
    with pytest.raises(GameError, match="ثانیه"):
        await services.events.try_open(view.id, a)


async def test_one_event_at_a_time_and_expiry(services, db, clock):
    assert await services.events.spawn(CHAT, "merchant") is not None
    assert await services.events.spawn(CHAT, "double_xp") is None
    clock.advance(10_000)
    actions = await services.events.tick()
    assert [a.what for a in actions] == ["ended"]
    assert await services.events.active(CHAT) == []


async def test_merchant_sells_limited_stock_and_charges_gold(services, db):
    a = await hero(services, db, 1, "آرش")
    view = await services.events.spawn(CHAT, "merchant")
    entry = view.state["stock"][0]
    before = (await services.players.require(1)).gold
    view, label = await services.events.buy(view.id, a, 0)
    assert (await services.players.require(1)).gold == before - entry["price"]
    assert view.state["stock"][0]["left"] == entry["left"] - 1 and label
    poor = await hero(services, db, 2, "سارا", gold=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 0 WHERE id = ?", (poor.id,))
    with pytest.raises(GameError):
        await services.events.buy(view.id, poor, 0)
    with pytest.raises(GameError):
        await services.events.buy(view.id, a, 9)


async def test_tick_spawns_in_active_groups_only(services, db, clock):
    ps = [await hero(services, db, i, f"قهرمان{i}") for i in (1, 2, 3)]
    await services.groups.touch(CHAT, "گروه")
    clock.advance(3_000)
    assert await services.events.tick() == []  # nobody active yet: tries again later
    async with db.transaction() as tx:
        await tx.execute("UPDATE groups SET next_event_at = 0")
    await active_group(services, db, ps)
    actions = await services.events.tick()
    assert [a.what for a in actions] == ["spawned"]
    async with db.read() as tx:
        nxt = await tx.scalar("SELECT next_event_at FROM groups WHERE chat_id = ?", (CHAT,), 0)
    assert nxt > services.ctx.now()


async def test_disabled_events_are_not_spawned(services, db, clock):
    ps = [await hero(services, db, i, f"قهرمان{i}") for i in (1, 2, 3)]
    await active_group(services, db, ps)
    await services.groups.set_command(CHAT, "events", False)
    async with db.transaction() as tx:
        await tx.execute("UPDATE groups SET next_event_at = 0")
    assert await services.events.tick() == []


async def _fighters(db, boss_id):
    async with db.read() as tx:
        return await tx.fetchall("SELECT player_id FROM boss_hits WHERE boss_id = ?", (boss_id,))


async def test_hidden_boss_is_free_to_start_and_pays_no_refund(services, db):
    ps = [await hero(services, db, i, f"قهرمان{i}") for i in (1, 2, 3)]
    await active_group(services, db, ps)
    before = [p.gold for p in ps]
    view = await services.events.spawn(CHAT, "hidden_boss")
    assert view is not None and view.boss is not None and view.boss.free
    boss = view.boss
    for p in ps:
        if p.id not in [f["player_id"] for f in await _fighters(db, boss.id)]:
            boss = await services.bosses.join(boss.id, p)
    gold = [(await services.players.require(p.platform_user_id)).gold for p in ps]
    boss = await services.bosses.start(boss.id, ps[1])
    assert boss.phase == "fighting"
    assert gold == [(await services.players.require(p.platform_user_id)).gold for p in ps] == before


async def test_double_xp_doubles_activity_xp_in_that_group(services, db):
    a = await hero(services, db, 1, "آرش", level=3)
    await services.events.spawn(CHAT, "double_xp")
    services.ctx.rng.seed(5)
    normal = await services.activities.perform(a.id, "fishing")
    services.ctx.rng.seed(5)
    async with db.transaction() as tx:
        await tx.execute("DELETE FROM cooldowns")
        await tx.execute("UPDATE players SET energy = 100, energy_at = ? WHERE id = ?", (services.ctx.now(), a.id))
    doubled = await services.activities.perform(a.id, "fishing", CHAT)
    assert doubled.double_xp and not normal.double_xp
    assert doubled.rolled.xp == normal.rolled.xp * 2


async def test_greeting_and_commands(h, services, db, clock):
    await hero(services, db, 1, "آرش", level=7)
    await hero(services, db, 2, "سارا", level=7)
    await h.say(2, "رویدادها", group=True)
    assert "رویدادهای گروه" in h.session.sent()[-1]["text"]
    await h.say(2, "/event merchant", group=True)
    assert "مدیران" in h.session.sent()[-1]["text"]
    await h.say(1, "/event merchant", group=True)
    assert "تاجر دوره‌گرد" in h.session.sent()[-1]["text"]
    assert h.session.sent()[-1]["reply_markup"]
    await h.say(1, "/event bogus", group=True)
    assert "نوع رویداد" in h.session.sent()[-1]["text"]


async def _finished_boss(db, chat, summoner, hits, status, ended, kind="beast_fire"):
    async with db.transaction() as tx:
        boss_id = await tx.execute(
            "INSERT INTO bosses (chat_id, boss_type, level, max_hp, hp, status, summoner_id, created_at, expires_at,"
            " ended_at) VALUES (?, ?, 5, 100, 0, ?, ?, ?, ?, ?)",
            (chat, kind, status, summoner, ended - 100, ended, ended),
        )
        for pid, damage in hits:
            await tx.execute("INSERT INTO boss_hits (boss_id, player_id, damage) VALUES (?, ?, ?)", (boss_id, pid, damage))


async def test_boss_boards_and_history(h, services, db, clock):
    a, b = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    now = services.ctx.now()
    await _finished_boss(db, CHAT, a.id, [(a.id, 500), (b.id, 900)], "defeated", now - 3_600)
    await _finished_boss(db, CHAT, a.id, [(a.id, 100)], "expired", now - 1_800)
    await _finished_boss(db, -9, a.id, [(a.id, 10_000)], "defeated", now - 30 * 86_400, kind="dragon_ice")

    hunters = await services.rankings.boss_hunters(a)
    assert [e.name for e in hunters.entries] == ["آرش", "سارا"] and hunters.my_position == 1
    week = await services.rankings.hero_of_the_week(CHAT)
    assert [(e.name, e.value) for e in week.entries] == [("سارا", 900), ("آرش", 600)]

    history = await services.rankings.battle_history(CHAT)
    assert [r.won for r in history] == [False, True] and "سارا" in history[1].top_name

    await h.say(1, "رتبه", group=True)
    for label in ("شکارچیان باس", "قهرمان هفته", "تاریخچه"):
        await h.click(1, h.button_data(label), group=True)
        assert "سارا" in h.session.sent("editMessageText")[-1]["text"] or label == "شکارچیان باس"
    text = h.session.sent("editMessageText")[-1]["text"]
    assert "تاریخچه‌ی نبردها" in text and "پیروزی" in text and "شکست" in text


async def test_hidden_chest_is_found_by_searching_the_places(services, db, clock):
    a = await hero(services, db, 1, "آرش")
    b = await hero(services, db, 2, "سارا")
    view = await services.events.spawn(CHAT, "hidden_chest")
    assert view is not None and view.state["target"] in view.state["places"] and view.state["clue"]
    wrong = next(p for p in view.state["places"] if p != view.state["target"])
    view, outcome = await services.events.search(view.id, a, wrong)
    assert outcome == "empty" and wrong in view.state["tried"]
    with pytest.raises(GameError, match="قبلاً"):
        await services.events.search(view.id, b, wrong)
    with pytest.raises(GameError, match="خسته"):
        await services.events.search(view.id, a, view.state["target"])  # a searched a moment ago
    clock.advance(30)
    view, outcome = await services.events.search(view.id, a, view.state["target"])
    assert outcome == "found" and view.status == "done" and view.state["winner"] == "آرش"
    with pytest.raises(GameError):
        await services.events.search(view.id, b, view.state["target"])
    assert "صندوقچه‌ی مخفی پیدا شد" in events_ui.text_for(view)


async def test_invasion_is_beaten_together_and_pays_by_share(services, db, clock):
    a, b = await hero(services, db, 1, "آرش", level=20), await hero(services, db, 2, "سارا", level=20)
    await active_group(services, db, [a, b])
    view = await services.events.spawn(CHAT, "invasion")
    assert view is not None and view.state["hp"] == view.state["max_hp"] > 0
    assert "🚨" in events_ui.text_for(view)
    before = (await services.players.require(1)).gold
    final = False
    for _ in range(400):
        for p in (a, b):
            try:
                view, damage, final = await services.events.defend(view.id, p)
            except GameError:
                continue
            if final:
                break
        if final:
            break
        clock.advance(13)
    assert final and view.status == "done" and view.state["payouts"]
    assert (await services.players.require(1)).gold > before
    assert "قلمرو نجات یافت" in events_ui.text_for(view)


async def test_a_lost_invasion_still_pays_a_consolation(services, db, clock):
    a = await hero(services, db, 1, "آرش")
    await active_group(services, db, [a])
    view = await services.events.spawn(CHAT, "invasion")
    before = (await services.players.require(1)).gold
    view, _, _ = await services.events.defend(view.id, a)
    clock.advance(1_000)
    actions = await services.events.tick()
    ended = [x for x in actions if x.what == "ended" and x.view.kind == "invasion"]
    assert ended and ended[0].view.status == "expired" and ended[0].view.state["payouts"]
    assert (await services.players.require(1)).gold > before


async def test_meteor_pieces_are_limited_and_shared(services, db, clock):
    from eternal_realm.game.data.world_events import METEOR_PER_PLAYER, METEOR_PIECES

    players = [await hero(services, db, 10 + i, f"p{i}") for i in range(3)]
    view = await services.events.spawn(CHAT, "meteor")
    assert view is not None and view.state["left"] == METEOR_PIECES
    taken = 0
    for _ in range(METEOR_PER_PLAYER):
        for p in players:
            view, item = await services.events.collect(view.id, p)
            taken += 1
        clock.advance(16)
    assert view.state["left"] == METEOR_PIECES - taken
    with pytest.raises(GameError, match="حداکثر"):
        await services.events.collect(view.id, players[0])
    extra = await hero(services, db, 99, "تازه")
    for _ in range(METEOR_PIECES - taken):
        view, _ = await services.events.collect(view.id, extra)
        clock.advance(16)
    assert view.status == "done" and view.state["left"] == 0
    with pytest.raises(GameError):
        await services.events.collect(view.id, players[1])


async def test_rare_boss_alert_goes_to_eligible_group_members_only(h, services, db):
    from eternal_realm.game.services.events import EventAction

    strong, weak = await hero(services, db, 1, "آرش", level=20), await hero(services, db, 2, "سارا", level=1)
    await active_group(services, db, [strong, weak])
    view = await services.events.spawn(CHAT, "hidden_boss")
    assert view is not None and view.boss is not None
    events_ui._alerted.clear()
    await events_ui.announce(h.bot, services, EventAction("spawned", view))
    dms = [p for p in h.session.sent("sendMessage") if p["chat_id"] == 1]
    assert dms and "اعلان شکار" in dms[0]["text"]
    assert not [p for p in h.session.sent("sendMessage") if p["chat_id"] == 2]
    n = len(h.session.sent("sendMessage"))
    await events_ui.alert_hunters(h.bot, services, view)  # no second alert within the gap
    assert len(h.session.sent("sendMessage")) == n


async def test_event_buttons_work_through_the_glass_keyboard(h, services, db):
    a = await hero(services, db, 1, "آرش")
    await active_group(services, db, [a])
    view = await services.events.spawn(CHAT, "meteor")
    await h.click(1, f"e:collect:{view.id}:0", group=True)
    assert any("برداشتید" in x.get("text", "") for x in h.session.callback_answers())


async def _bot_added(h, chat=CHAT, adder=1):
    h._update_id += 1
    h._message_id += 1
    await h.dp.feed_raw_update(h.bot, {"update_id": h._update_id, "message": {
        "message_id": h._message_id, "from": h._user(adder), "chat": {"id": chat, "type": "group", "title": "گروه کوچک"}, "date": 0,
        "new_chat_members": [{"id": 1, "is_bot": True, "first_name": "bot", "username": "er_bot"}],
    }})


async def test_a_small_group_gets_a_note_and_the_bot_leaves(h, services):
    h.session.member_count = 8
    await _bot_added(h, adder=7)
    text = h.session.last_text()
    assert "۲۵ عضو" in text and "۸ نفر" in text
    assert h.session.sent("leaveChat")
    group = await services.groups.get(CHAT)
    assert group is not None and not group.enabled


async def test_a_big_group_or_the_owner_adding_keeps_the_bot(h):
    h.session.member_count = 80
    await _bot_added(h, adder=7)
    assert not h.session.sent("sendMessage") and not h.session.sent("leaveChat")
    h.session.member_count = 3
    await _bot_added(h, adder=1)  # the owner may keep the bot in a tiny test group
    assert not h.session.sent("leaveChat")


def test_busy_groups_get_events_sooner_and_more_team_events():
    from eternal_realm.game.services.events import BASE_WEIGHTS, CROWD_KINDS, KINDS, event_interval, weight_of

    assert set(BASE_WEIGHTS) == set(KINDS) and len(KINDS) >= 11
    assert event_interval(7200, 2) > event_interval(7200, 12) > event_interval(7200, 40)
    assert event_interval(7200, 200) == 7200 / 3.0  # at most three times as often
    for kind in CROWD_KINDS:
        assert weight_of(kind, 40) > weight_of(kind, 2)
    assert weight_of("wheel", 40) == weight_of("wheel", 2)


async def test_gold_rain_is_limited_per_player(services, db, clock):
    a = await hero(services, db, 1, "آرش", gold=0)
    view = await services.events.spawn(CHAT, "gold_rain")
    assert view is not None and view.state["left"] == 20
    gold = (await services.players.require(1)).gold
    for _ in range(4):
        view, got = await services.events.grab(view.id, a)
        assert got > 0
        clock.advance(11)
    assert (await services.players.require(1)).gold > gold
    with pytest.raises(GameError, match="حداکثر"):
        await services.events.grab(view.id, a)
    assert "باران سکه" in events_ui.text_for(view)


async def test_spring_refills_energy_once_for_the_first_visitors(services, db):
    a, b = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 0")
    view = await services.events.spawn(CHAT, "spring")
    view = await services.events.drink(view.id, a)
    assert (await services.players.require(1)).energy > 5
    with pytest.raises(GameError, match="یک بار"):
        await services.events.drink(view.id, a)
    view = await services.events.drink(view.id, b)
    assert view.state["left"] == 10 and "چشمه‌ی برکت" in events_ui.text_for(view)


async def test_wheel_gives_one_spin_each_and_a_prize(services, db):
    a, b = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    view = await services.events.spawn(CHAT, "wheel")
    view, prize = await services.events.spin(view.id, a)
    assert prize and "آرش" in events_ui.text_for(view)
    with pytest.raises(GameError, match="یک بار"):
        await services.events.spin(view.id, a)
    view, _ = await services.events.spin(view.id, b)
    assert len(view.state["spins"]) == 2


async def test_dragon_egg_hatches_together_and_pays_everybody(services, db, clock):
    a, b = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    await active_group(services, db, [a, b])
    view = await services.events.spawn(CHAT, "egg")
    need = view.state["need"]
    assert need >= 12 and "تخم اژدها" in events_ui.text_for(view)
    gold = [(await services.players.require(u)).gold for u in (1, 2)]
    hatched = False
    for _ in range(need * 3):
        for p in (a, b):
            try:
                view, hatched = await services.events.warm(view.id, p)
            except GameError:
                continue
            if hatched:
                break
        if hatched:
            break
        clock.advance(7)
    assert hatched and view.status == "done" and len(view.state["payouts"]) == 2
    for uid, before in zip((1, 2), gold):
        assert (await services.players.require(uid)).gold > before
    assert (await services.players.require(1)).crystal >= 2


async def test_owner_can_summon_the_new_events_and_players_can_tap_them(h, services, db):
    a = await hero(services, db, 1, "ارباب")
    await services.groups.touch(CHAT, "گروه")
    for word in ("باران سکه", "چشمه", "چرخ شانس", "تخم اژدها"):
        await h.say(1, f"احضار {word}", group=True)
    kinds = sorted(v.kind for v in await services.events.active(CHAT))
    assert kinds == ["egg", "gold_rain", "spring", "wheel"]
    wheel = next(v for v in await services.events.active(CHAT) if v.kind == "wheel")
    await h.click(1, f"e:spin:{wheel.id}:0", group=True)
    assert any("🎡" in x.get("text", "") for x in h.session.callback_answers())


async def test_an_invasion_can_be_beaten_within_three_minutes_by_a_few_players(services, db, clock):
    from eternal_realm.game.services.events import DEFEND_GAP, LIFETIME

    assert LIFETIME["invasion"] <= 180 and LIFETIME["egg"] <= 180
    players = [await hero(services, db, 20 + i, f"p{i}", level=10) for i in range(3)]
    await active_group(services, db, players + [await hero(services, db, 40 + i, f"q{i}", level=10) for i in range(15)])
    view = await services.events.spawn(CHAT, "invasion")
    started = clock()
    final = False
    while not final and clock() - started < LIFETIME["invasion"] - DEFEND_GAP:
        for p in players:
            try:
                view, _, final = await services.events.defend(view.id, p)
            except GameError:
                continue
            if final:
                break
        clock.advance(DEFEND_GAP + 1)
    assert final and view.status == "done"  # three tappers are enough, however big the group is
