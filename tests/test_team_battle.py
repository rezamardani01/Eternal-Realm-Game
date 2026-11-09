import re

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.engine.combat import Action
from eternal_realm.shared.errors import GameError
from eternal_realm.shared.text import EMOJI

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def heroes(services, n):
    classes = ["warrior", "archer", "mage", "warrior", "archer"]
    return [await services.players.register(100 + i, f"u{i}", f"قهرمان{i}", "human", classes[i]) for i in range(n)]


async def play_to_end(services, battle_id):
    for _ in range(400):
        lobby = await services.teams.get(battle_id)
        if lobby.status != "active":
            return lobby
        battle = lobby.battle
        who = next(p for _t, _s, p in lobby.members if p.id == battle.current.player_id)
        action = Action.SKILL if battle.current.skill_ready_in <= 1 else Action.ATTACK
        await services.teams.act(battle_id, who, action)
    raise AssertionError("team battle did not end")


async def test_seats_start_rules_and_a_full_fight(services, db):
    a, b, c = await heroes(services, 3)
    lobby = await services.teams.create(-500, a)
    assert lobby.seat_of(a.id) == (0, 0)
    with pytest.raises(GameError):  # the other team is empty
        await services.teams.start(lobby.id, a)
    lobby, _ = await services.teams.sit(lobby.id, b, 1, 0)
    lobby, _ = await services.teams.sit(lobby.id, c, 1, 1)
    with pytest.raises(GameError):  # taken
        await services.teams.sit(lobby.id, c, 1, 0)
    lobby, _ = await services.teams.sit(lobby.id, c, 0, 1)  # moving over to the first team
    assert lobby.seat_of(c.id) == (0, 1)
    lobby, _ = await services.teams.sit(lobby.id, c, 0, 1)  # tapping your own seat stands you up
    assert lobby.seat_of(c.id) is None
    lobby, _ = await services.teams.sit(lobby.id, c, 1, 1)
    with pytest.raises(GameError):  # only the creator starts
        await services.teams.start(lobby.id, b)
    update = await services.teams.start(lobby.id, a)
    assert len(update.battle.fighters) == 3 and update.battle.teams == [0, 1, 1]
    with pytest.raises(GameError):
        await services.teams.act(lobby.id, a if update.battle.current.player_id != a.id else b, Action.ATTACK)
    final = await play_to_end(services, lobby.id)
    assert final.status == "finished" and final.battle.finished
    async with db.read() as tx:
        paid = await tx.scalar("SELECT COUNT(*) FROM team_battle_members WHERE battle_id = ? AND paid_at > 0", (lobby.id,), 0)
        refs = await tx.fetchall("SELECT ref FROM transactions WHERE ref LIKE 'teambattle:%'")
    assert paid == 3 and len({r["ref"] for r in refs}) == len(refs)
    with pytest.raises(GameError):
        await services.teams.act(lobby.id, a, Action.ATTACK)


async def test_a_hero_can_only_be_in_one_battle(services):
    a, b = await heroes(services, 2)
    first = await services.teams.create(-500, a)
    again = await services.teams.create(-500, a)  # a new request closes the old open lobby
    with pytest.raises(GameError):
        await services.teams.sit(first.id, b, 1, 0)
    second = await services.teams.create(-500, b)
    await services.teams.sit(second.id, a, 1, 0)  # joining another lobby takes the hero out of their own
    with pytest.raises(GameError):
        await services.teams.sit(again.id, b, 1, 0)


async def test_turns_go_team_by_team(services):
    a, b, c, d = await heroes(services, 4)
    lobby = await services.teams.create(-500, a)
    for p, team, seat in ((b, 0, 1), (c, 1, 0), (d, 1, 1)):
        await services.teams.sit(lobby.id, p, team, seat)
    update = await services.teams.start(lobby.id, a)
    battle = update.battle
    order = []
    for _ in range(4):  # one full round: the opening team's two heroes, then the other team's two
        order.append(battle.current_team)
        lobby = await services.teams.get(lobby.id)
        who = next(p for _t, _s, p in lobby.members if p.id == lobby.battle.current.player_id)
        update = await services.teams.act(lobby.id, who, Action.DEFEND)
        battle = update.battle
    assert order[0] == order[1] and order[2] == order[3] and order[0] != order[2]


async def test_idle_heroes_are_played_automatically(services, clock):
    a, b = await heroes(services, 2)
    lobby = await services.teams.create(-500, a)
    await services.teams.sit(lobby.id, b, 1, 0)
    await services.teams.start(lobby.id, a)
    seen = False
    for _ in range(80):
        clock.advance(200)
        for item in await services.teams.expire_stale():
            seen = seen or hasattr(item, "battle")
        if (await services.teams.get(lobby.id)).status == "finished":
            break
    assert seen and (await services.teams.get(lobby.id)).status == "finished"


async def test_unstarted_lobbies_expire(services, clock):
    (a,) = await heroes(services, 1)
    lobby = await services.teams.create(-500, a)
    clock.advance(400)
    closed = await services.teams.expire_stale()
    assert [x.id for x in closed] == [lobby.id]
    await services.teams.create(-500, a)  # free again


async def test_the_group_flow_with_buttons(h, services):
    a, b = await heroes(services, 2)
    await h.say(100, "مبارزه تیمی", group=True)
    text = h.session.last_text()
    assert "تیم اول" in text and "تیم دوم" in text and "جایگاه" in text
    for line in text.splitlines():  # house rule: at most one emoji per line, and only at its start
        assert len(re.findall(EMOJI, line)) <= 1, line
    assert len(h.session.last_markup_rows()) == 7  # team names, five rows of seats and the control row
    await h.click(101, h.session.last_markup_rows()[1][2]["callback_data"], group=True)  # the second team's first seat
    assert "قهرمان1" in h.session.last_text()
    await h.click(101, h.button_data("شروع"), group=True)  # not the creator
    assert "فقط سازنده" in " ".join(x.get("text", "") for x in h.session.callback_answers())
    await h.click(100, h.button_data("شروع"), group=True)
    text = h.session.last_text()
    assert "نبرد تیمی" in text and "نوبت" in text and "❤️" in text
    assert {"حمله", "دفاع", "تسلیم"} <= {w for lab in h.labels() for w in lab.split()}


async def test_the_result_panel_is_tidy(services):
    from eternal_realm.bot import team_battle

    a, b = await heroes(services, 2)
    lobby = await services.teams.create(-500, a)
    await services.teams.sit(lobby.id, b, 1, 0)
    await services.teams.start(lobby.id, a)
    for _ in range(400):
        lobby = await services.teams.get(lobby.id)
        who = next(p for _t, _s, p in lobby.members if p.id == lobby.battle.current.player_id)
        update = await services.teams.act(lobby.id, who, Action.ATTACK)
        if update.finished:
            break
    text = team_battle.result_text(update)
    assert "پایان نبرد تیمی" in text and "پیروز شد" in text and "برنده" in text and "بازنده" in text and "🎁" in text
    for line in text.splitlines():
        if not line.startswith("•"):  # the story lines come from the duel engine
            assert len(re.findall(EMOJI, line)) <= 1, line


async def test_the_creator_can_cancel_even_mid_fight(services):
    a, b = await heroes(services, 2)
    lobby = await services.teams.create(-500, a)
    await services.teams.sit(lobby.id, b, 1, 0)
    await services.teams.start(lobby.id, a)
    with pytest.raises(GameError):
        await services.teams.cancel(lobby.id, b)
    await services.teams.cancel(lobby.id, a)
    assert (await services.teams.get(lobby.id)).status == "cancelled"
    with pytest.raises(GameError):
        await services.teams.act(lobby.id, a, Action.ATTACK)
    await services.teams.create(-500, b)  # everyone is free again


async def test_the_creator_throws_a_hero_out_for_good(services):
    a, b, c = await heroes(services, 3)
    lobby = await services.teams.create(-500, a)
    await services.teams.sit(lobby.id, b, 1, 0)
    with pytest.raises(GameError):  # another hero cannot take someone's seat
        await services.teams.sit(lobby.id, c, 1, 0)
    lobby, note = await services.teams.sit(lobby.id, a, 1, 0)  # the creator taps b's name
    assert "بیرون" in note and lobby.seat_of(b.id) is None
    for team, seat in ((1, 0), (0, 1)):
        with pytest.raises(GameError, match="بیرون کرده"):
            await services.teams.sit(lobby.id, b, team, seat)
    await services.teams.sit(lobby.id, c, 1, 0)
    with pytest.raises(GameError, match="سازنده"):
        await services.teams.start(lobby.id, c)
    with pytest.raises(GameError, match="سازنده"):
        await services.teams.cancel(lobby.id, c)


async def test_the_opening_team_is_drawn_by_lot(services):
    a, b = await heroes(services, 2)
    firsts = set()
    for _ in range(30):
        lobby = await services.teams.create(-500, a)
        await services.teams.sit(lobby.id, b, 1, 0)
        update = await services.teams.start(lobby.id, a)
        firsts.add(update.battle.first_team)
        assert "قرعه" in update.lines[0]
        await services.teams.cancel(lobby.id, a)
    assert firsts == {0, 1}


async def test_blows_land_on_random_members_of_the_other_team():
    import random

    from eternal_realm.game.engine import team_fight
    from eternal_realm.game.engine.combat import Fighter
    from eternal_realm.game.engine.team_fight import TeamBattle

    def mk(n):
        return Fighter(name=n, emoji="x", max_hp=100, hp=100, atk=1, defense=0, magic=0, speed=1, luck=0)

    battle = TeamBattle([mk("a"), mk("b"), mk("c"), mk("d")], [0, 1, 1, 1])
    battle.actor = 0
    rng = random.Random(5)
    hit = {team_fight._pick_target(battle, rng) for _ in range(60)}
    assert hit == {1, 2, 3}
    battle.fighters[2].hp = 0  # a fallen hero is never picked
    assert {team_fight._pick_target(battle, rng) for _ in range(60)} == {1, 3}
