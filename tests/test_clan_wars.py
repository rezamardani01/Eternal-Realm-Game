import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.services.clan_wars import score_of, star_text, stars_for
from eternal_realm.shared.errors import GameError

from .harness import Harness

HOUR = 3600


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=10_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def two_clans(services, db, treasury=3_000):
    """Two clans of two: (leader 1, member 2) against (leader 3, member 4)."""
    a1, a2, b1, b2 = [await hero(services, db, i, n) for i, n in ((1, "آرش"), (2, "سارا"), (3, "بهرام"), (4, "رها"))]
    north = await services.clans.create(a1, "شیرهای شمال")
    south = await services.clans.create(b1, "گرگ‌های جنوب")
    await services.clans.join(a2, north.id)
    await services.clans.join(b2, south.id)
    if treasury:
        await services.clans.donate(await services.players.require(1), treasury)
        await services.clans.donate(await services.players.require(3), treasury)
    return [await services.players.require(i) for i in (1, 2, 3, 4)], north.id, south.id


async def treasury_of(db, clan_id):
    async with db.read() as tx:
        return await tx.scalar("SELECT treasury FROM clans WHERE id = ?", (clan_id,), 0)


def test_stars_and_score():
    assert [stars_for(True, 0.9), stars_for(True, 0.6), stars_for(True, 0.4), stars_for(True, 0.05)] == [3, 3, 2, 1]
    assert stars_for(False, 1.0) == 0
    assert star_text(2) == "⭐⭐☆"
    attacks = [
        {"clan_id": 1, "target_id": 7, "stars": 1}, {"clan_id": 1, "target_id": 7, "stars": 3},
        {"clan_id": 1, "target_id": 8, "stars": 2}, {"clan_id": 2, "target_id": 5, "stars": 3},
    ]
    assert score_of(attacks, 1) == 5 and score_of(attacks, 2) == 3


async def test_declare_locks_the_stake_and_decline_returns_it(services, db):
    (a1, a2, b1, b2), north, south = await two_clans(services, db)
    with pytest.raises(GameError, match="مالک و قائم‌مقام"):
        await services.clan_wars.declare(a2, south, 500)
    with pytest.raises(GameError, match="گرو"):
        await services.clan_wars.declare(a1, south, 123)
    war = await services.clan_wars.declare(a1, south, 500)
    assert war.status == "pending" and not war.incoming and war.stake == 500
    assert await treasury_of(db, north) == 2_500 and await treasury_of(db, south) == 3_000
    # both clans are busy now
    with pytest.raises(GameError, match="درگیر"):
        await services.clan_wars.declare(a1, south, 0)
    with pytest.raises(GameError):
        await services.clan_wars.declare(b1, north, 0)
    assert (await services.clan_wars.hub(b1)).war.incoming

    assert await services.clan_wars.answer(b1, war.id, False) is None
    assert await treasury_of(db, north) == 3_000
    assert (await services.clan_wars.hub(a1)).war is None
    with pytest.raises(GameError, match="معتبر نیست"):
        await services.clan_wars.answer(b1, war.id, True)


async def test_withdraw_and_expiry_refund(services, db, clock):
    (a1, _, b1, _), north, south = await two_clans(services, db)
    war = await services.clan_wars.declare(a1, south, 2_000)
    with pytest.raises(GameError):
        await services.clan_wars.withdraw(b1, war.id)
    await services.clan_wars.withdraw(a1, war.id)
    assert await treasury_of(db, north) == 3_000

    war = await services.clan_wars.declare(a1, south, 2_000)
    assert await treasury_of(db, north) == 1_000
    clock.advance(13 * HOUR)
    await services.clan_wars.sweep()
    await services.clan_wars.sweep()
    assert await treasury_of(db, north) == 3_000
    assert (await services.clan_wars.hub(a1)).war is None


async def test_accept_needs_a_matching_treasury(services, db):
    (a1, _, b1, _), north, south = await two_clans(services, db, treasury=0)
    await services.clans.donate(a1, 2_000)
    war = await services.clan_wars.declare(a1, south, 2_000)
    with pytest.raises(GameError, match="خزانه"):
        await services.clan_wars.answer(b1, war.id, True)
    await services.clans.donate(await services.players.require(3), 2_000)
    view = await services.clan_wars.answer(b1, war.id, True)
    assert view.status == "active" and view.fighter and view.attacks_left == 2
    assert await treasury_of(db, north) == 0 and await treasury_of(db, south) == 0


async def test_attacks_limits_and_early_settlement(services, db, clock):
    (a1, a2, b1, b2), north, south = await two_clans(services, db)
    war = await services.clan_wars.declare(a1, south, 500)
    await services.clan_wars.answer(b1, war.id, True)
    with pytest.raises(GameError, match="وسط جنگ"):
        await services.clans.disband(a1)

    first = await services.clan_wars.attack(a1, b1.id)
    assert 0 <= first.stars <= 3 and first.gained == first.stars and not first.finished
    assert first.war.mine.stars == first.stars and first.war.attacks_left == 1
    with pytest.raises(GameError, match="یک بار"):
        await services.clan_wars.attack(a1, b1.id)
    with pytest.raises(GameError, match="سپاه دشمن"):
        await services.clan_wars.attack(a1, a2.id)
    await services.clan_wars.attack(a1, b2.id)
    with pytest.raises(GameError, match="حمله"):
        await services.clan_wars.attack(a1, b1.id)

    # a newcomer watches this war
    clock.advance(60)
    late = await hero(services, db, 9, "دیرآمده")
    await services.clans.join(late, north)
    with pytest.raises(GameError, match="پس از آغاز"):
        await services.clan_wars.attack(late, b1.id)

    last = None
    for attacker, foes in ((a2, (b1, b2)), (b1, (a1, a2)), (b2, (a1, a2))):
        for foe in foes:
            try:
                last = await services.clan_wars.attack(await services.players.require(attacker.platform_user_id), foe.id)
            except GameError as e:  # a keep the clan already took completely
                assert "کامل فتح" in str(e)
    hub = await services.clan_wars.hub(a1)
    if last is not None and last.finished:
        assert hub.war is None and hub.last is not None and sum(hub.record) == 1
        total = await treasury_of(db, north) + await treasury_of(db, south)
        assert total == 6_000  # the pot went to the winner (or back to both on a draw)
        if hub.last.result == "won":
            assert await treasury_of(db, north) == 3_500
        async with db.read() as tx:
            paid = await tx.scalar("SELECT COUNT(*) FROM transactions WHERE ref LIKE 'cwar:%'", (), 0)
        assert paid >= 4
        # a truce follows
        with pytest.raises(GameError, match="نمی‌شود اعلام جنگ"):
            await services.clan_wars.declare(a1, south, 0)


async def test_time_up_settles_once(services, db, clock):
    (a1, a2, b1, b2), north, south = await two_clans(services, db)
    war = await services.clan_wars.declare(a1, south, 500)
    await services.clan_wars.answer(b1, war.id, True)
    r = await services.clan_wars.attack(a1, b1.id)
    clock.advance(25 * HOUR)
    await services.clan_wars.sweep()
    await services.clan_wars.sweep()
    hub = await services.clan_wars.hub(a1)
    assert hub.war is None and hub.last.status == "done"
    assert hub.last.result == ("won" if r.stars else "draw")
    assert await treasury_of(db, north) == (3_500 if r.stars else 3_000)
    assert await treasury_of(db, south) == (2_500 if r.stars else 3_000)
    async with db.read() as tx:
        paid = await tx.scalar("SELECT COUNT(*) FROM transactions WHERE ref = ?", (f"cwar:{war.id}:{a1.id}",), 0)
    assert paid == 1
    assert [w.id for w in await services.clan_wars.history(a1)] == [war.id]
    _, champions = await services.clan_wars.champions(a1)
    assert champions and champions[0].ours and champions[0].stars == r.stars
    # the clan can be closed again once the war is over
    await services.clans.disband(b1)


async def test_panel_flow(services, db, h):
    (a1, a2, b1, b2), north, south = await two_clans(services, db)
    await h.say(1, "جنگ خاندان")
    assert "جنگ خاندان‌ها" in h.session.last_text() and any("اعلام جنگ" in x for x in h.labels())
    await h.tap(1, "اعلام جنگ")
    assert any("جنوب" in x for x in h.labels())
    await h.tap(1, "جنوب")
    await h.tap(1, "۵۰۰")
    await h.tap(1, "بله")
    assert "منتظر پاسخ" in h.session.last_text()

    await h.panel(2, "cwar")
    assert not any("پس گرفتن" in x for x in h.labels())
    await h.panel(3, "cwar")
    assert "به جنگ خوانده" in h.session.last_text()
    await h.tap(3, "می‌جنگیم")
    assert "میدان جنگ" in h.session.last_text()

    await h.tap(3, "حمله به دژها")
    await h.tap(3, "آرش")
    await h.tap(3, "یورش")
    text = h.session.last_text()
    assert "دژ آرش" in text and "ستاره‌ها" in text
    assert any("تجربه" in x for x in h.labels())
    await h.panel(3, "cwarboard")
    assert "بهرام" in h.session.last_text()
    await h.panel(3, "cwarnote", "star")
    await h.panel(4, "cwartargets", "0")
    assert any("آرش" in x for x in h.labels())
    await h.panel(1, "cwarlog")
    assert "هنوز جنگی" in h.session.last_text()


async def test_panel_without_a_clan(services, db, h):
    await hero(services, db, 1, "تنها")
    await h.say(1, "جنگ خاندان")
    assert "مخصوص اعضای خاندان" in "\n".join(h.session.texts())


async def test_refused_action_keeps_the_buttons(services, db, h):
    """A «working» frame removes the buttons, so it may only be shown once the action went through."""
    await hero(services, db, 1, "تنها", gold=0)
    await h.say(1, "خاندان")
    for name in ("craftdo", "cpack", "dgo", "citygo"):
        before = len(h.session.texts())
        await h.panel(1, name, "nothing")
        frames = [t for t in h.session.texts()[before:] if "..." in t or "…" in t]
        assert not frames, (name, frames)


async def test_home_shows_bars_and_stale_buttons_do_not_crash(services, db, h):
    await hero(services, db, 1, "آرش", gold=25_000)
    await h.say(1, "/start")
    assert "▰" in h.session.last_text() or "▱" in h.session.last_text()
    await h.panel(1, "clanshopq", "no_such_offer")
    await h.panel(1, "note", "item", "no_such_item")
