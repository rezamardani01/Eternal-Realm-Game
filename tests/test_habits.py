"""The habits that bring heroes back: streak rescue, the week of missions, waiting alerts, the ranked season, friends,
the group's goal, market sellers, the endless tower, pop-up happenings and the festivals of the calendar."""

import json

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import maze as md
from eternal_realm.game.data import popups as pop_data
from eternal_realm.game.data import raids as raid_data
from eternal_realm.game.services import ladder
from eternal_realm.shared.errors import GameError

from .harness import Harness

DAY = 86400
CHAT = -500


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid=1, level=10, gold=5_000, crystal=0):
    p = await services.players.register(uid, f"u{uid}", f"قهرمان{uid}", "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, energy = 500 WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, crystal=crystal, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def tehran_noon(day: int) -> int:
    return day * DAY + 12 * 3600 - 12600


# --- the daily streak can be rescued -----------------------------------------------------------------------------------
async def test_a_streak_broken_by_one_missed_day_can_be_rescued_with_crystals(services, db, clock):
    p = await hero(services, db, crystal=20)
    for _ in range(4):
        await services.players.claim_daily(p.id)
        clock.advance(DAY + 60)
    me = await services.players.require(1)
    assert me.daily_streak == 4
    assert services.players.streak_status(me) == (0, False) or not services.players.streak_status(me)[1]  # not broken yet
    clock.advance(DAY)  # a whole day was missed
    me = await services.players.require(1)
    assert services.players.streak_status(me) == (4, True)
    before = me.crystal
    assert await services.players.rescue_streak(p.id) == 4
    assert (await services.players.require(1)).crystal == before - services.players.RESCUE_COST
    reward = await services.players.claim_daily(p.id)
    assert reward.streak == 5  # the chain went on instead of starting again
    with pytest.raises(GameError):
        await services.players.rescue_streak(p.id)


async def test_a_streak_cannot_be_rescued_when_it_is_short_or_long_gone(services, db, clock):
    p = await hero(services, db, crystal=20)
    await services.players.claim_daily(p.id)
    clock.advance(2 * DAY + 60)
    assert not services.players.streak_status(await services.players.require(1))[1]  # a one-day streak is not worth saving
    with pytest.raises(GameError):
        await services.players.rescue_streak(p.id)


async def test_the_home_screen_offers_the_rescue_only_when_it_applies(h, services, db, clock):
    p = await hero(services, db, crystal=20)
    for _ in range(3):
        await services.players.claim_daily(p.id)
        clock.advance(DAY + 60)
    await h.panel(1, "home")
    assert not any("نجات" in t for t in h.labels())
    clock.advance(DAY)
    await h.panel(1, "home")
    assert any("نجات زنجیره" in t for t in h.labels())
    await h.tap(1, "نجات زنجیره")
    await h.tap(1, "بله")
    assert "نجات پیدا کرد" in h.session.last_text()


# --- a week of missions ------------------------------------------------------------------------------------------------------
async def finish_missions_today(services, db, p):
    for m in await services.missions.today(p):
        async with db.transaction() as tx:
            await tx.execute(
                "UPDATE daily_missions SET progress = target WHERE player_id = ? AND slot = ? AND day = ?",
                (p.id, m.slot, (services.ctx.now() + 12600) // DAY),
            )
        await services.missions.claim(p, m.slot)


async def test_a_week_of_complete_days_pays_a_better_prize_the_more_days_there_are(services, db, clock):
    p = await hero(services, db)
    clock.t = tehran_noon(19_700 - (19_700 + 5) % 7)  # a Saturday noon: the start of a week
    week = await services.missions.week(p)
    assert week.days == 0 and week.earned is None and week.next_prize[0] == 3
    with pytest.raises(GameError, match="۳ روز"):
        await services.missions.claim_week(p)
    for _ in range(7):
        await finish_missions_today(services, db, await services.players.require(1))
        clock.advance(DAY)
    clock.advance(-DAY)  # still inside the same week
    week = await services.missions.week(p)
    assert week.days == 7 and week.earned[2] == "royal_chest"
    before = (await services.players.require(1)).crystal
    days, crystal, chest = await services.missions.claim_week(p)
    assert (days, chest) == (7, "royal_chest") and (await services.players.require(1)).crystal == before + crystal
    with pytest.raises(GameError, match="قبلاً"):
        await services.missions.claim_week(p)


async def test_the_missions_screen_shows_the_week(h, services, db):
    await hero(services, db)
    await h.panel(1, "missions")
    text = h.session.last_text()
    assert "جایزه‌ی هفته" in text and "روز کامل" in text


# --- «your hero is waiting» --------------------------------------------------------------------------------------------------
async def test_a_full_energy_bar_and_a_ready_daily_gift_send_one_message_each(services, db, clock):
    p = await hero(services, db)
    clock.t = tehran_noon(19_800)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 10, energy_at = ?, daily_at = ?, daily_streak = 2 WHERE id = ?", (clock.t - 3600, clock.t - 30 * 3600, p.id))
    assert await services.alerts.waiting() == 1  # the daily gift (the bar is still filling)
    assert await services.alerts.waiting() == 0  # never twice for the same gift
    clock.advance(3600)
    assert await services.alerts.waiting() == 0  # an hour does not fill a bar from 10 (40 energy an hour)
    clock.advance(2 * 3600)
    assert await services.alerts.waiting() == 1
    alerts = await services.alerts.pending()
    assert {a.screen for a in alerts} == {"daily", "adv"}
    assert await services.alerts.waiting() == 0


async def test_waiting_messages_keep_quiet_at_night_and_for_those_who_opted_out(services, db, clock):
    p = await hero(services, db)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 0, energy_at = ?, daily_at = ? WHERE id = ?", (clock.t - 5 * 3600, clock.t - 30 * 3600, p.id))
    clock.t = 19_800 * DAY + 2 * 3600 - 12600  # two at night
    assert await services.alerts.waiting() == 0
    clock.t = tehran_noon(19_800)
    await services.offers.set_enabled(p, False)
    assert await services.alerts.waiting() == 0


# --- the ranked season -----------------------------------------------------------------------------------------------------
async def test_experience_counts_for_the_season_and_the_best_ten_are_paid_when_it_ends(services, db, clock):
    clock.t = tehran_noon(ladder.SEASON_DAYS * 700 + 3)
    players = [await hero(services, db, uid=10 + i, level=5) for i in range(12)]
    async with db.transaction() as tx:
        for i, p in enumerate(players):
            await services.players.grant_xp(tx, p.id, 100 * (i + 1))
    standing = await services.ladder.standing(players[0].id)
    assert [r.name for r in standing.top][0] == "قهرمان21" and len(standing.top) == 10
    assert standing.mine.rank == 12 and standing.ends_in > 0
    assert await services.ladder.close_due() == 0  # still running
    clock.advance(ladder.SEASON_DAYS * DAY)
    assert await services.ladder.close_due() == 1
    assert await services.ladder.close_due() == 0  # once
    winner = await services.players.require(21)
    assert winner.crystal >= 30 and "رتبه" in winner.honor
    assert (await services.players.require(10)).crystal == 0  # the twelfth got nothing
    assert await services.social.titles(winner.id)
    after = await services.ladder.standing(21)
    assert after.top == [] or after.top[0].score < 1200  # the board started again


async def test_the_season_screen_and_its_command(h, services, db):
    await hero(services, db)
    await h.panel(1, "rseason")
    assert "فصل رتبه‌بندی" in h.session.last_text() and "جایزه‌ی ده نفر برتر" in h.session.last_text()
    await h.say(1, "فصل", group=True)
    assert "فصل رتبه‌بندی" in h.session.last_text()


# --- friends -----------------------------------------------------------------------------------------------------------------
async def test_friends_ask_accept_and_gift_energy_once_a_day(services, db, clock):
    a, b = await hero(services, db, 1, level=10), await hero(services, db, 2, level=10)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 10, energy_at = ? WHERE id = ?", (clock.t, b.id))
    with pytest.raises(GameError):
        await services.social.request(a, a.id)
    await services.social.request(a, b.id)
    with pytest.raises(GameError, match="فرستاده"):
        await services.social.request(a, b.id)
    assert [x[0] for x in await services.social.pending(b)] == [a.id]
    with pytest.raises(GameError, match="او در فهرست"):
        await services.social.gift_energy(a, b.id)
    await services.social.respond(b, a.id, True)
    assert [f.player_id for f in await services.social.friends(a)] == [b.id]
    assert [f.player_id for f in await services.social.friends(b)] == [a.id]
    gained = await services.social.gift_energy(a, b.id)
    assert gained == 20 and (await services.players.require(2)).energy == 30
    with pytest.raises(GameError, match="امروز"):
        await services.social.gift_energy(a, b.id)
    clock.advance(DAY)
    await services.social.gift_energy(a, b.id)
    await services.social.remove(a, b.id)
    assert await services.social.friends(a) == [] and await services.social.friends(b) == []


async def test_asking_someone_who_asked_you_first_makes_you_friends_at_once(services, db):
    a, b = await hero(services, db, 1), await hero(services, db, 2)
    await services.social.request(a, b.id)
    await services.social.request(b, a.id)
    assert len(await services.social.friends(a)) == 1


async def test_friend_screens_and_the_reply_word(h, services, db):
    a, b = await hero(services, db, 1), await hero(services, db, 2)
    await h.say(1, "دوست", group=True, reply_to=h.message_of(2))
    assert "درخواست دوستی" in h.session.last_text()
    await h.panel(2, "friends")
    assert any("قهرمان1" in t for t in h.labels())
    await h.tap(2, "قهرمان1")
    await h.panel(2, "friendyes", str(a.id))
    await h.panel(2, "friends")
    await h.tap(2, "قهرمان1")
    assert any("ارسال" in t for t in h.labels())
    await h.tap(2, "ارسال")
    assert any("امروز" in x.get("text", "") or "انرژی" in x.get("text", "") for x in h.session.callback_answers())
    await h.say(1, "دوست", group=True)
    assert "ریپلای" in h.session.last_text()
    assert b


# --- the group's goal --------------------------------------------------------------------------------------------------------
async def test_a_group_fills_its_weekly_goal_together_and_the_helpers_are_paid(services, db, clock):
    from eternal_realm.game.services.social import GOAL_MIN, GOAL_MIN_HITS

    a, b, lazy = await hero(services, db, 1), await hero(services, db, 2), await hero(services, db, 3)
    assert await services.social.goal(CHAT) is None
    goal = None
    for i in range(GOAL_MIN):
        who = a if i % 2 == 0 else b
        if i == 0:
            await services.social.hit(CHAT, lazy)  # one stray hit is not enough for a prize
            continue
        goal = await services.social.hit(CHAT, who)
    assert goal.completed_now and goal.rewarded == [a.id, b.id]
    assert lazy.id not in goal.rewarded and GOAL_MIN_HITS == 3
    again = await services.social.hit(CHAT, a)
    assert not again.completed_now
    assert (await services.players.require(1)).crystal >= 2 and (await services.players.require(3)).crystal == 0
    clock.advance(8 * DAY)
    assert await services.social.goal(CHAT) is None  # a fresh week, a fresh goal


async def test_hunting_in_a_group_counts_and_the_goal_word_shows_it(h, services, db):
    await hero(services, db, 1)
    await services.groups.touch(CHAT, "گروه")
    await h.say(1, "هدف گروه", group=True)
    assert "هنوز شکاری" in h.session.last_text()
    await h.say(1, "شکار", group=True)
    await h.say(1, "هدف گروه", group=True)
    assert "شکارهای گروه: ۱" in h.session.last_text()


# --- the market's best seller ------------------------------------------------------------------------------------------------
async def test_the_best_seller_of_a_week_gets_a_badge_and_pays_a_smaller_fee(services, db, clock):
    seller, buyer = await hero(services, db, 1, gold=0), await hero(services, db, 2, gold=50_000)
    clock.t = tehran_noon(19_700 - (19_700 + 5) % 7)  # a Saturday
    start_gold = seller.gold
    async with db.transaction() as tx:
        await services.inventory.grant(tx, seller.id, "iron_ore", 40)
    ore = __import__("eternal_realm.game.data.items", fromlist=["x"]).get_item("iron_ore")
    for _ in range(3):  # three sales of 360 pass the weekly minimum
        listing = await services.market.list_stack(await services.players.require(1), ore, 4, 360)
        await services.market.buy(buyer, listing.id)
    normal_fee = services.market.fee_for(360)
    assert (await services.players.require(1)).gold == start_gold + 3 * (360 - normal_fee)
    clock.advance(7 * DAY)  # the week is over
    assert await services.market.weekly_sellers() == seller.id
    assert await services.market.weekly_sellers() is None  # once a week
    assert any("فروشنده‌ی برتر" in t for t in await services.social.titles(seller.id))
    assert await services.market.is_top_seller(seller.id)
    seller = await services.players.require(1)
    gold_before = seller.gold
    again = await services.market.list_stack(seller, __import__("eternal_realm.game.data.items", fromlist=["x"]).get_item("iron_ore"), 4, 360)
    await services.market.buy(buyer, again.id)
    assert (await services.players.require(1)).gold - gold_before == 360 - services.market.fee_for(360, True)
    assert services.market.fee_for(360, True) < normal_fee


# --- the endless tower ---------------------------------------------------------------------------------------------------------
async def climb(services, db, p, win=True):
    from tests.test_solo import finish, rig  # noqa: PLC0415

    await services.solo.start_tower(p)
    if win:
        await rig(db, p.id)
    return await finish(services, db, p, win=False) if not win else await finish(services, db, p, win=True)


async def test_the_tower_never_ends_a_win_climbs_a_loss_costs_nothing_but_energy(services, db):
    p = await hero(services, db, level=30)
    for expected in range(1, 4):
        update = await climb(services, db, p)
        assert update.won and (await services.solo.tower_state(p.id))[0] == expected
    cleared, best, today = await services.solo.tower_state(p.id)
    assert (cleared, best, today) == (3, 3, 3)
    async with db.transaction() as tx:  # the next floor is far too strong to beat
        await tx.execute("UPDATE solo_progress SET n = 9 WHERE player_id = ? AND key = 'tower:floor'", (p.id,))
    first = await services.solo.start_tower(p)
    assert first.info["floor"] == 10 and first.info["guardian"]
    await services.solo.abandon(p)
    assert (await services.solo.tower_state(p.id))[0] == 9  # giving up loses no floor


async def test_a_guardian_floor_pays_a_lasting_prize_once_and_the_board_ranks_climbers(services, db):
    a, b = await hero(services, db, 1, level=30), await hero(services, db, 2, level=30)
    for p, floors in ((a, 10), (b, 3)):
        async with db.transaction() as tx:
            await tx.execute("INSERT INTO solo_progress (player_id, key, n) VALUES (?, 'tower:floor', ?)", (p.id, floors - 1))
    before = (await services.players.require(1)).crystal
    update = await climb(services, db, a)
    assert update.won and any("جایزه‌ی ماندگار" in n for n in update.payout.notes)
    assert (await services.players.require(1)).crystal > before
    await climb(services, db, b)
    board = await services.solo.tower_board()
    assert [(r, n) for r, n, _ in board] == [(1, "قهرمان1"), (2, "قهرمان2")]
    assert [floor for _, _, floor in board] == [10, 3]


async def test_the_tower_screens(h, services, db):
    await hero(services, db, level=30)
    await h.panel(1, "trip")
    assert any("برج بی‌پایان" in t for t in h.labels())
    await h.panel(1, "tower")
    assert "رکورد شما" in h.session.last_text() and any("صعود" in t for t in h.labels())
    await h.tap(1, "صعود")
    assert "نوبت شماست" in h.session.last_text()


def test_the_tower_has_a_foe_and_a_strength_for_every_floor():
    from eternal_realm.game.data import solo as data

    for floor in (1, 9, 10, 55, 199, 200, 201, 250, 500, 1000):
        assert md.tower_foe(floor) in data.FOES
        assert md.tower_mult(floor) > 0
    assert md.tower_mult(10) > md.tower_mult(9)


# --- pop-up happenings -------------------------------------------------------------------------------------------------------
async def test_the_bot_starts_a_happening_for_a_hero_who_is_around_and_never_two_a_day(services, db, clock):
    p = await hero(services, db, level=10)
    clock.t = tehran_noon(19_900)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy_at = ? WHERE id = ?", (clock.t - 3600, p.id))
    assert await services.popups.spawn_due(chance=1.0) == 1
    assert await services.popups.spawn_due(chance=1.0) == 0
    alert = (await services.alerts.pending())[0]
    assert alert.screen == "popup" and alert.arg.isdigit()
    open_ = await services.popups.get(p, int(alert.arg))
    assert open_ is not None and open_.seconds_left > 0
    clock.advance(25 * 3600)
    assert await services.popups.spawn_due(chance=1.0) in (0, 1)  # (the hero is idle by now)


async def test_happenings_stay_quiet_at_night_and_for_new_or_opted_out_heroes(services, db, clock):
    p = await hero(services, db, level=10)
    clock.t = 19_900 * DAY + 3600 - 12600  # one at night
    assert await services.popups.spawn_due(chance=1.0) == 0
    clock.t = tehran_noon(19_900)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy_at = ?, level = 1 WHERE id = ?", (clock.t, p.id))
    assert await services.popups.spawn_due(chance=1.0) == 0


@pytest.mark.parametrize("popup", [p.id for p in pop_data.POPUPS])
async def test_every_happening_resolves_for_every_choice(services, db, clock, popup):
    for index in range(len(pop_data.get_popup(popup).choices)):
        p = await hero(services, db, uid=100 + index, level=12, gold=1_000)
        popup_id = await services.popups.start_for(p, popup)
        result = await services.popups.choose(p, popup_id, index)
        assert result.lines
        with pytest.raises(GameError, match="قبلاً"):
            await services.popups.choose(p, popup_id, index)


async def test_a_happening_expires_and_belongs_to_one_hero(services, db, clock):
    p, other = await hero(services, db, 1), await hero(services, db, 2)
    pid = await services.popups.start_for(p, "thief")
    with pytest.raises(GameError, match="برای شما نیست"):
        await services.popups.choose(other, pid, 0)
    clock.advance(10 * 3600)
    assert await services.popups.get(p, pid) is None
    late = await services.popups.choose(p, pid, 0)
    assert "تمام شد" in late.lines[0] and late.gold == 0


async def test_happening_screens_show_choices_and_the_outcome(h, services, db):
    p = await hero(services, db, gold=1_000)
    pid = await services.popups.start_for(p, "old_map")
    await h.panel(1, "popup", str(pid))
    assert "نقشه‌ی گنج" in h.session.last_text() and len(h.labels()) == 2
    await h.tap(1, "می‌فروشم")
    assert "دستاورد" in h.session.last_text() or "ماجرا" in h.session.last_text() or "نقشه" in h.session.last_text()
    await h.panel(1, "popup", str(pid))
    assert "گذشت" in h.session.last_text()


# --- the festivals of the calendar and the weekly cup -----------------------------------------------------------------------------
def jalali_noon(month: int, day: int, year: int = 1405) -> int:
    """A Unix time at noon Tehran on a Jalali date, found by walking days (no calendar library needed)."""
    from eternal_realm.shared.jalali import gregorian_to_jalali
    import datetime

    start = datetime.date(year + 621, 1, 1)
    for offset in range(0, 400):
        d = start + datetime.timedelta(days=offset)
        if gregorian_to_jalali(d.year, d.month, d.day)[0] == year and gregorian_to_jalali(d.year, d.month, d.day)[1:] == (month, day):
            return int(datetime.datetime(d.year, d.month, d.day, 12, tzinfo=datetime.timezone.utc).timestamp()) - 12600
    raise AssertionError("date not found")


@pytest.mark.parametrize("kind", [k for k in raid_data.SEASONAL])
async def test_each_festival_announces_itself_on_its_day_once_and_gives_everybody_a_badge(services, db, clock, kind):
    players = [await hero(services, db, 10 + i, level=10 + 5 * i) for i in range(3)]
    clock.t = jalali_noon(*kind.date)
    due = await services.raids.scheduled()
    assert due == (kind.id, 30)
    view = await services.raids.create(*due)
    for p in players:
        await services.raids.join(p, view.id)
    assert await services.raids.scheduled() is None  # one is already gathering
    clock.advance(31 * 60)
    gold = [(await services.players.require(p.platform_user_id)).gold for p in players]
    event = (await services.raids.tick())[0]
    assert event.view.status == "done"
    for p, before in zip(players, gold):
        assert (await services.players.require(p.platform_user_id)).gold > before
        assert any(kind.badge in t for t in await services.social.titles(p.id))
    assert await services.raids.scheduled() is None  # not twice a year
    await services.raids.set_flag("seasonal_events", False)
    clock.advance(0)


async def test_a_festival_can_be_switched_off(services, db, clock):
    await services.raids.set_flag("seasonal_events", False)
    clock.t = jalali_noon(1, 1)
    assert await services.raids.scheduled() is None


async def test_the_weekly_cup_starts_on_friday_evening_once_a_week(services, db, clock):
    friday = 19_901 - (19_901 - 1) % 7  # a day index with day % 7 == 1: a Friday
    assert friday % 7 == 1
    clock.t = friday * DAY + 15 * 3600 - 12600  # 15:00 Tehran: too early
    assert await services.raids.scheduled() is None
    clock.t = friday * DAY + 20 * 3600 + 600 - 12600
    assert await services.raids.scheduled() == ("cup", 15)
    assert await services.raids.scheduled() is None  # marked as done for this week
    clock.advance(7 * DAY)
    assert await services.raids.scheduled() == ("cup", 15)
    await services.raids.set_flag("weekly_cup", False)
    clock.advance(7 * DAY)
    assert await services.raids.scheduled() is None


async def test_the_owner_can_switch_the_calendar_events(h, services, db):
    await hero(services, db, 999)
    await h.say(999, "رویداد سراسری جام هفتگی خاموش", group=True)
    assert "خاموش شد" in h.session.last_text() and not await services.raids._flag("weekly_cup")
    await h.say(999, "رویداد سراسری فصلی خاموش", group=True)
    assert not await services.raids._flag("seasonal_events")
    await h.say(999, "رویداد سراسری فصلی روشن", group=True)
    assert await services.raids._flag("seasonal_events")


def test_json_roundtrip_of_popups_is_plain_data():
    json.dumps([c.result for p in pop_data.POPUPS for c in p.choices], ensure_ascii=False)


async def test_the_delivery_loop_runs_every_new_sweep_and_the_happening_arrives_with_its_button(h, services, db, clock):
    from eternal_realm.bot import notifier

    p = await hero(services, db, level=10)
    clock.t = tehran_noon(19_950)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy_at = ? WHERE id = ?", (clock.t - 600, p.id))
    pid = await services.popups.start_for(p, "mystery_box")
    async with db.transaction() as tx:
        from eternal_realm.game.notify import queue

        await queue(tx, p.id, f"popup:{pid}", "🎁 *جعبه‌ی ناشناس*", clock.t, "popup", str(pid))
    h.session.reset()
    sent = await notifier.deliver(h.bot, services)
    assert sent >= 1
    buttons = [b for m in h.session.sent("sendMessage") for row in m.get("reply_markup", {}).get("inline_keyboard", []) for b in row]
    button = next(b for b in buttons if "ببینم" in b["text"])
    await h.click(1, button["callback_data"])
    assert "جعبه‌ی ناشناس" in h.session.last_text()
    await h.tap(1, "بازش")
    assert "دستاورد" in h.session.last_text()


async def test_the_new_screens_read_cleanly_in_a_group_too(h, services, db):
    await hero(services, db, 1)
    await services.groups.touch(CHAT, "گروه")
    for word in ("دوستان", "فصل", "هدف گروه"):
        await h.say(1, word, group=True)
        assert h.session.last_text()


def test_season_numbers_shown_to_players_start_at_one():
    assert ladder.label(ladder.FIRST_SEASON) == 1 and ladder.label(ladder.FIRST_SEASON + 2) == 3 and ladder.label(3) == 1
