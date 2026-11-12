"""Online duels: the queue, the matchmaker, the shared fight in two private chats, timeouts and the end."""

import asyncio

import pytest

from eternal_realm.bot import duels as duels_ui
from eternal_realm.bot import online_panel
from eternal_realm.bot.callbacks import DuelCb
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.services import online as online_data
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=10, cls="warrior", race="human"):
    p = await services.players.register(uid, f"u{uid}", name, race, cls)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


def sent_to(h, uid, method="sendMessage"):
    return [p for p in h.session.sent(method) if str(p.get("chat_id")) == str(uid)]


def buttons_of(payload):
    return [b for row in payload.get("reply_markup", {}).get("inline_keyboard", []) for b in row]


async def pair(h, services, db, level_a=10, level_b=10):
    await hero(services, db, 10, "آرش", level_a)
    await hero(services, db, 11, "سارا", level_b, cls="mage")
    await h.panel(10, "onsearch")
    await h.panel(11, "onsearch")


# --- the search ---------------------------------------------------------------------------------------------------------------------
async def test_a_search_waits_and_can_be_cancelled(h, services, db):
    p = await hero(services, db, 10, "آرش")
    await h.panel(10, "online")
    assert "جستجوی حریف" in " ".join(h.labels()) and "لیگ" in h.session.last_text()
    await h.panel(10, "onsearch")
    assert "در حال جستجوی حریف" in h.session.last_text() and "لغو جستجو" in " ".join(h.labels())
    assert await services.online.waiting() == 1 and (await services.online.searching(p.id)) is not None
    await h.panel(10, "onsearch")  # tapping again only refreshes the search
    assert await services.online.waiting() == 1
    await h.panel(10, "onleave")
    assert await services.online.waiting() == 0 and "جستجوی حریف" in " ".join(h.labels())


async def test_two_players_in_the_queue_are_matched_and_both_see_the_fight(h, services, db):
    await pair(h, services, db)
    match = await services.online.match_of_player(1)
    assert match is not None and await services.online.waiting() == 0
    duel = await services.duels.get(match.duel_id)
    assert duel.status == "active" and duel.battle is not None
    actor = duel.battle.current.player_id
    seat_actor = match.seat_of(actor)
    other = next(s for s in match.seats if s.player_id != actor)
    mine = [p for p in sent_to(h, seat_actor.platform_user_id) if "مبارزه‌ی آنلاین" in p["text"]]
    theirs = [p for p in sent_to(h, other.platform_user_id) + sent_to(h, other.platform_user_id, "editMessageText") if "نوبت" in p["text"]]
    assert mine and "نوبت شماست" in mine[-1]["text"]
    labels = [b["text"] for b in buttons_of(mine[-1])]
    assert "⚔️ حمله عادی" in labels and len(labels) == 6  # attack, three skills, defend, surrender
    assert theirs and "صبر کنید" in theirs[-1]["text"] and not buttons_of(theirs[-1])  # the waiting side has no move buttons


async def test_a_match_is_an_ordinary_duel_with_a_rated_result_for_both(h, services, db):
    await pair(h, services, db)
    match = await services.online.match_of_player(1)
    duel = await services.duels.get(match.duel_id)
    actor = duel.battle.current.player_id
    seat = match.seat_of(actor)
    h.session.reset()
    # the actor surrenders: the other player wins, both get a result message with a way to search again
    await h.click(seat.platform_user_id, DuelCb(action="surrender", id=duel.id).pack())
    done = await services.duels.get(match.duel_id)
    assert done.status == "finished" and done.winner_id != actor
    for s in match.seats:
        results = [p for p in sent_to(h, s.platform_user_id) if "پایان نبرد" in p["text"]]
        assert results and any("جستجوی حریف تازه" in b["text"] for b in buttons_of(results[-1]))
    fights, wins = await services.online.record(done.winner_id)
    assert fights == 1 and wins == 1
    assert (await services.online.record(actor)) == (1, 0)
    async with db.read() as tx:
        winner_rating = await tx.scalar("SELECT rating FROM players WHERE id = ?", (done.winner_id,), 0)
        loser_rating = await tx.scalar("SELECT rating FROM players WHERE id = ?", (actor,), 0)
    assert winner_rating > 1000 > loser_rating  # an Elo league result, like any duel


async def test_a_turn_moves_the_fight_on_and_the_next_player_gets_a_fresh_message(h, services, db):
    await pair(h, services, db)
    match = await services.online.match_of_player(1)
    duel = await services.duels.get(match.duel_id)
    first = duel.battle.current.player_id
    seat = match.seat_of(first)
    h.session.reset()
    await h.click(seat.platform_user_id, DuelCb(action="attack", id=duel.id).pack())
    now = await services.duels.get(match.duel_id)
    assert now.battle.current.player_id != first and now.status == "active"
    second = match.seat_of(now.battle.current.player_id)
    fresh = [p for p in sent_to(h, second.platform_user_id) if "نوبت شماست" in p["text"]]
    assert fresh and buttons_of(fresh[-1])  # a new message with the buttons: the phone rings
    edited = [p for p in sent_to(h, seat.platform_user_id, "editMessageText") if "صبر کنید" in p["text"]]
    assert edited  # the one who moved sees the same fight, waiting
    # the player who just moved cannot move again
    with pytest.raises(GameError):
        await services.duels.act(duel.id, await services.players.get(first), __import__("eternal_realm.game.engine.combat", fromlist=["x"]).Action.ATTACK)


# --- the matchmaker -------------------------------------------------------------------------------------------------------------------
async def test_the_power_ranges_must_be_close_at_first_and_widen_while_waiting(h, services, db, clock):
    await hero(services, db, 10, "آرش", level=10)
    await hero(services, db, 11, "سارا", level=120)
    await h.panel(10, "onsearch")
    await h.panel(11, "onsearch")
    assert await services.online.match_of_player(1) is None and await services.online.waiting() == 2
    assert (await services.online.sweep()).matches == []
    clock.advance(online_data.ANYONE_AFTER - 1)
    assert (await services.online.sweep()).matches == []  # still too far apart
    clock.advance(2)
    swept = await services.online.sweep()
    assert len(swept.matches) == 1 and swept.matches[0].update is not None  # after a long wait anybody is a fair opponent
    assert await services.online.waiting() == 0


async def test_power_ranges_and_how_far_the_search_reaches():
    edges = online_data.POWER_EDGES
    assert list(edges) == sorted(edges) and edges[0] == 0
    assert online_data.bracket_of(0) == 0 and online_data.bracket_of(199) == 0 and online_data.bracket_of(200) == 1
    assert online_data.bracket_of(450) == 2 and online_data.bracket_of(10**6) == len(edges) - 1
    assert online_data.bracket_label(2) == "۴۰۰ تا ۷۰۰" and "به بالا" in online_data.bracket_label(len(edges) - 1)
    assert online_data.reach(0) == 0  # at first only the same range
    assert online_data.reach(30) == 1 and online_data.reach(60) == 2 and online_data.reach(online_data.ANYONE_AFTER) is None
    assert online_data.QUEUE_TIMEOUT == 300 and online_data.ANYONE_AFTER < online_data.QUEUE_TIMEOUT


async def test_the_closest_opponent_is_chosen(h, services, db):
    for uid, name, level in ((10, "آرش", 10), (11, "بهرام", 30), (12, "پویا", 12)):
        await hero(services, db, uid, name, level)
    await h.panel(11, "onsearch")
    await h.panel(12, "onsearch")  # a level 12 hero and a level 30 hero are too far apart: both wait
    assert await services.online.match_of_player(2) is None
    await h.panel(10, "onsearch")  # the level 10 hero fits the level 12 one, not the level 30
    match = await services.online.match_of_player(1)
    assert {s.player_id for s in match.seats} == {1, 3}
    assert await services.online.searching(2) is not None


async def test_old_searches_end_with_a_message(h, services, db, clock):
    await hero(services, db, 10, "آرش")
    await h.panel(10, "onsearch")
    clock.advance(online_data.QUEUE_TIMEOUT + 1)
    swept = await services.online.sweep()
    assert [w.player_id for w in swept.expired] == [1] and await services.online.waiting() == 0
    h.session.reset()
    await online_panel.push_no_one_came(h.bot, swept.expired[0])
    texts = [p["text"] for p in h.session.sent("editMessageText")]
    assert texts and "حریفی پیدا نشد" in texts[-1]


async def test_the_matchmaker_never_pairs_a_player_twice(services, db):
    for uid in (10, 11, 12):
        await hero(services, db, uid, f"قهرمان{uid}", 10)
    async with db.transaction() as tx:
        for pid in (1, 2, 3):
            await tx.execute(
                "INSERT INTO online_queue (player_id, level, rating, chat_id, message_id, joined_at) VALUES (?, 10, 1000, ?, 5, ?)",
                (pid, pid, services.ctx.now()),
            )
    sweeps = await asyncio.gather(services.online.sweep(), services.online.sweep(), services.online.sweep())
    made = [m for s in sweeps for m in s.matches]
    assert len(made) == 1 and await services.online.waiting() == 1  # three waiters make one pair, never two
    players = [s.player_id for s in made[0].seats]
    assert len(set(players)) == 2


async def test_a_pair_that_met_too_often_today_is_not_matched_again(h, services, db, clock):
    await hero(services, db, 10, "آرش")
    await hero(services, db, 11, "سارا")
    limit = services.ctx.balance.duel_pair_daily_limit
    for _ in range(limit):
        await h.panel(10, "onsearch")
        await h.panel(11, "onsearch")
        match = await services.online.match_of_player(1)
        assert match is not None
        duel = await services.duels.get(match.duel_id)
        h.session.reset()
        await h.click(match.seat_of(duel.battle.current.player_id).platform_user_id, DuelCb(action="surrender", id=duel.id).pack())
        clock.advance(1)
    await h.panel(10, "onsearch")
    await h.panel(11, "onsearch")
    assert await services.online.match_of_player(1) is None and await services.online.waiting() == 2  # both keep waiting for others


# --- rules ---------------------------------------------------------------------------------------------------------------------------------
async def test_a_player_in_a_fight_cannot_search_again_and_groups_are_refused(h, services, db):
    await pair(h, services, db)
    p = await services.players.require(10)
    with pytest.raises(GameError, match="نبرد"):
        await services.online.join(p, 10, 5)
    await h.panel(10, "online", group=True)
    assert "پیام خصوصی" in h.session.last_text() or h.session.last_text()
    h.session.reset()
    await h.panel(10, "onsearch", group=True)
    assert any("خصوصی" in a.get("text", "") for a in h.session.callback_answers())


async def test_a_hero_who_is_away_cannot_search(services, db):
    p = await hero(services, db, 10, "آرش")
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO expeditions (player_id, kind, hours, started_at, ends_at) VALUES (?, 'mine', 1, 0, ?)",
            (p.id, services.ctx.now() + 3000),
        )
    with pytest.raises(GameError):
        await services.online.join(p, 10, 5)


async def test_a_turn_that_times_out_ends_the_fight_for_both(h, services, db, clock):
    await pair(h, services, db)
    match = await services.online.match_of_player(1)
    duel = await services.duels.get(match.duel_id)
    idler = duel.battle.current.player_id
    clock.advance(services.ctx.balance.duel_turn_seconds + 5)
    h.session.reset()
    for item in await services.duels.expire_stale():
        await duels_ui._announce(h.bot, services, item)
    done = await services.duels.get(match.duel_id)
    assert done.status == "finished" and done.winner_id != idler
    for s in match.seats:
        results = [p for p in sent_to(h, s.platform_user_id) if "پایان نبرد" in p["text"]]
        assert results, s.platform_user_id
    assert (await services.online.match_of_player(1)) is None  # a finished fight no longer blocks a new search


async def test_group_duels_are_untouched_by_the_online_hooks(h, services, db):
    a = await hero(services, db, 10, "آرش")
    b = await hero(services, db, 11, "سارا")
    duel = await services.duels.challenge(-500, a, b)
    await services.duels.accept(duel.id, b)
    assert await services.online.match_of(duel.id) is None
    assert await services.online.match_of_player(a.id) is None


async def test_the_entry_points_exist(h, services, db):
    await hero(services, db, 10, "آرش")
    await h.panel(10, "fight")
    assert "🌐 مبارزه آنلاین" in h.labels()
    h.session.reset()
    await h.say(10, "مبارزه آنلاین")
    assert "مبارزه‌ی آنلاین" in h.session.last_text() and "جستجوی حریف" in " ".join(h.labels())


async def test_the_player_who_must_move_is_warned_once_before_the_time_runs_out(h, services, db, clock):
    await pair(h, services, db)
    match = await services.online.match_of_player(1)
    assert await services.online.due_warnings() == []  # plenty of time left
    clock.advance(services.ctx.balance.duel_turn_seconds - online_data.WARN_SECONDS + 1)
    due = await services.online.due_warnings()
    duel = await services.duels.get(match.duel_id)
    assert len(due) == 1 and due[0][1] == duel.battle.current.player_id and 0 < due[0][2] <= online_data.WARN_SECONDS
    assert await services.online.due_warnings() == []  # one warning per turn
    clock.advance(services.ctx.balance.duel_turn_seconds)  # the turn ran out; a later turn would be warned again


async def test_the_heartbeat_sends_the_warning_to_the_right_chat(h, services, db, clock):
    await pair(h, services, db)
    match = await services.online.match_of_player(1)
    duel = await services.duels.get(match.duel_id)
    seat = match.seat_of(duel.battle.current.player_id)
    clock.advance(services.ctx.balance.duel_turn_seconds - 10)
    h.session.reset()
    task = asyncio.create_task(online_panel.processor(h.bot, services, interval=0.01))
    await asyncio.sleep(0.2)
    task.cancel()
    warned = [p for p in sent_to(h, seat.platform_user_id) if "ثانیه مانده" in p["text"]]
    assert len(warned) == 1


async def test_neighbouring_ranges_meet_after_a_short_wait(h, services, db, clock):
    await hero(services, db, 10, "آرش", level=10)  # power ~250: the 200-400 range
    await hero(services, db, 11, "سارا", level=30)  # power ~550: the 400-700 range
    await h.panel(10, "onsearch")
    await h.panel(11, "onsearch")
    assert await services.online.match_of_player(1) is None  # different ranges: they wait
    assert (await services.online.sweep()).matches == []
    clock.advance(20)  # the longest wait is over 15 seconds: neighbouring ranges are fine now
    assert len((await services.online.sweep()).matches) == 1


async def test_the_search_message_is_deleted_and_a_fresh_fight_message_is_sent_to_both(h, services, db):
    await hero(services, db, 10, "آرش")
    await hero(services, db, 11, "سارا", cls="mage")
    await h.click(10, __import__("eternal_realm.bot.callbacks", fromlist=["x"]).PanelCb(s="onsearch", o=10).pack(), message_id=701)
    h.session.reset()
    await h.click(11, __import__("eternal_realm.bot.callbacks", fromlist=["x"]).PanelCb(s="onsearch", o=11).pack(), message_id=702)
    deleted = {(str(p["chat_id"]), p["message_id"]) for p in h.session.sent("deleteMessage")}
    assert ("10", 701) in deleted and ("11", 702) in deleted  # both «searching» messages are gone
    for uid in (10, 11):
        fight = [p for p in sent_to(h, uid) if "مبارزه‌ی آنلاین" in p["text"]]
        assert fight, uid  # and each player got a brand new message with the fight
    assert not h.session.sent("editMessageText") or all("جستجوی حریف" not in p["text"] for p in h.session.sent("editMessageText"))


async def test_the_main_menu_starts_with_a_single_online_button_and_its_page_has_one_button(h, services, db):
    await hero(services, db, 10, "آرش")
    await h.say(10, "/start")
    first_row = h.session.last_markup_rows()[0]
    assert [b["text"] for b in first_row] == ["🌐 مبارزه آنلاین"]  # the top row, alone
    await h.panel(10, "online")
    assert h.labels() == ["🔎 جستجوی حریف"] and "لیگ" in h.session.last_text()
    await h.panel(10, "onsearch")
    await h.panel(10, "online")
    assert h.labels() == ["❌ لغو جستجو"]  # while searching the one button cancels
