import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import clans as clan_repo
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.khan_shop import day_of, offers_for
from eternal_realm.game.engine.combat import Action
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=20_000, level=1):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


async def khan_of(services, uid):
    return (await services.players.require(uid)).khan_points


async def test_minimum_level_and_the_plus_minus_buttons(h, services, db):
    leader = await hero(services, db, 1, "رهبر")
    newbie = await hero(services, db, 2, "تازه‌کار")
    clan = await services.clans.create(leader, "شیرها")
    assert clan.min_level == 1
    await h.panel(1, "clanlvl", "up")
    await h.panel(1, "clanlvl", "up")
    assert (await services.clans.get(clan.id)).min_level == 3
    assert "سطح مورد نیاز عضویت: ۳" in " ".join(h.labels())
    with pytest.raises(GameError, match="سطح ۳"):
        await services.clans.join(newbie, clan.id)
    await h.panel(1, "clanlvl", "dn")
    await h.panel(1, "clanlvl", "dn")
    await h.panel(1, "clanlvl", "dn")  # never below 1
    assert (await services.clans.get(clan.id)).min_level == 1
    await services.clans.join(newbie, clan.id)
    with pytest.raises(GameError, match="رهبر"):
        await services.clans.set_min_level(newbie, 5)


async def test_the_betrayal_fine(h, services, db):
    leader = await hero(services, db, 1, "رهبر")
    member = await hero(services, db, 2, "آرش", gold=300)
    clan = await services.clans.create(leader, "شیرها")
    await services.clans.set_fine(leader, 1_000)
    assert (await services.clans.get(clan.id)).exit_fine == 1_000
    await h.panel(2, "clanview", str(clan.id))  # the fine is on show before joining
    assert "۱٬۰۰۰" in h.session.last_text() or "۱,۰۰۰" in h.session.last_text() or "1" in h.session.last_text()
    await h.panel(2, "clanjoinq", str(clan.id))
    assert "جریمه‌ی خیانت" in h.session.last_text() and "اگر بعداً" in h.session.last_text()
    await services.clans.join(member, clan.id)
    await h.panel(2, "clanleaveq")  # too poor to leave
    assert "کم دارید" in h.session.last_text()
    with pytest.raises(GameError):
        await services.clans.leave(member)
    assert (await services.clans.of(member.id)) is not None
    async with db.transaction() as tx:
        await wallet.apply(tx, member.id, gold=2_000, reason="t", now=services.ctx.now())
    member = await services.players.require(2)
    treasury = (await services.clans.get(clan.id)).treasury
    assert await services.clans.leave(member) == "left"
    assert (await services.players.require(2)).gold == member.gold - 1_000
    assert (await services.clans.get(clan.id)).treasury == treasury + 1_000
    assert await services.clans.set_fine(leader, 10**9) == services.ctx.balance.clan_fine_max
    assert await services.clans.set_fine(leader, -5) == 0


async def test_the_clan_picture_costs_gold_every_time(services, db):
    leader = await hero(services, db, 1, "رهبر")
    other = await hero(services, db, 2, "آرش")
    clan = await services.clans.create(leader, "شیرها")
    await services.clans.join(other, clan.id)
    price = services.ctx.balance.clan_photo_gold
    gold = (await services.players.require(1)).gold
    with pytest.raises(GameError, match="رهبر"):
        await services.clans.set_photo(other, "F0")
    await services.clans.set_photo(leader, "F1")
    await services.clans.set_photo(leader, "F2")
    assert (await services.clans.get(clan.id)).photo == "F2"
    assert (await services.players.require(1)).gold == gold - 2 * price
    await services.clans.remove_photo(leader)
    assert (await services.clans.get(clan.id)).photo == ""
    assert (await services.players.require(1)).gold == gold - 2 * price  # removing is free
    with pytest.raises(GameError):
        await services.clans.remove_photo(leader)


async def test_the_picture_flow_and_the_card_with_the_picture(h, services, db):
    leader = await hero(services, db, 1, "رهبر")
    clan = await services.clans.create(leader, "شیرها")
    await h.panel(1, "clanphotoask")
    assert "عکس خاندان را بفرستید" in h.session.last_text()
    h._update_id += 1
    await h.dp.feed_raw_update(h.bot, {"update_id": h._update_id, "message": {
        "message_id": 90, "from": h._user(1), "chat": {"id": 1, "type": "private"}, "date": 0,
        "photo": [{"file_id": "SMALL", "file_unique_id": "a", "width": 1, "height": 1},
                  {"file_id": "BIG", "file_unique_id": "b", "width": 9, "height": 9}],
    }})
    sent = h.session.sent("sendPhoto")[-1]
    assert sent["photo"] == "BIG" and "پیش‌نمایش" in sent["caption"]
    yes = next(b for row in sent["reply_markup"]["inline_keyboard"] for b in row if "بله" in b["text"])
    await h.click(1, yes["callback_data"])
    assert (await services.clans.get(clan.id)).photo == "BIG"
    h.session.reset()
    await h.say(1, "خاندان", group=True)  # the clan word shows the picture, the facts and the glass buttons
    card = h.session.sent("sendPhoto")[-1]
    assert card["photo"] == "BIG" and "شیرها" in card["caption"] and "جریمه‌ی خیانت" in card["caption"]
    labels = [b["text"] for row in card["reply_markup"]["inline_keyboard"] for b in row]
    assert any("فروشگاه خاندان" in x for x in labels) and any("اعضا" in x for x in labels)


async def test_khan_points_come_from_duels_between_clans(services, db):
    a = await hero(services, db, 1, "الف‌الف")
    b = await hero(services, db, 2, "بابک")
    c = await hero(services, db, 3, "جمشید")
    ca = await services.clans.create(a, "شیرها")
    await services.clans.create(b, "پلنگ‌ها")
    await services.clans.join(c, ca.id)
    async with db.transaction() as tx:
        await clan_repo.award_khan(tx, a.id, c.id)  # same clan: nothing
        await clan_repo.award_khan(tx, a.id, b.id)
    assert (await khan_of(services, 1), await khan_of(services, 2), await khan_of(services, 3)) == (3, 1, 0)
    duel = await services.duels.challenge(-500, a, b)
    await services.duels.accept(duel.id, b)
    for _ in range(300):
        d = await services.duels.get(duel.id)
        if d.status != "active":
            break
        who = a if d.battle.current.player_id == a.id else b
        await services.duels.act(duel.id, who, Action.ATTACK)
    assert await khan_of(services, 1) + await khan_of(services, 2) == 4 + 4


async def test_the_clan_shop(h, services, db, clock):
    leader = await hero(services, db, 1, "رهبر")
    outsider = await hero(services, db, 2, "بیرونی")
    await services.clans.create(leader, "شیرها")
    with pytest.raises(GameError):
        await services.clans.shop(outsider)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET khan_points = 1000 WHERE id = ?", (leader.id,))
    offers, points = await services.clans.shop(leader)
    assert len(offers) == 6 and points == 1000 and not any(bought for _o, bought in offers)
    assert [o for o, _ in offers] == offers_for(day_of(services.ctx.now()))
    offer = offers[0][0]
    await h.panel(1, "clanshop")
    assert "فروشگاه خاندان" in h.session.last_text() and "خان‌پوینت" in h.session.last_text()
    await h.panel(1, "clanshopq", offer.id)
    assert "تأیید خرید" in h.session.last_text()
    await h.panel(1, "clanshopbuy", offer.id)
    assert (await services.players.require(1)).khan_points == 1000 - offer.price
    with pytest.raises(GameError, match="امروز"):
        await services.clans.buy(leader, offer.id)
    assert (await services.players.require(1)).khan_points == 1000 - offer.price
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET khan_points = 0 WHERE id = ?", (leader.id,))
    other = offers[1][0]
    with pytest.raises(GameError, match="کافی نیست"):
        await services.clans.buy(leader, other.id)
    clock.advance(86400)  # a new day, new goods, and yesterday's purchase is forgotten
    assert len((await services.clans.shop(leader))[0]) == 6
