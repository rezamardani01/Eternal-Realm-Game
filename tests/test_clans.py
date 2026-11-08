import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.services.clans import capacity_for, level_for
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=5_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def test_levels_and_capacity():
    assert [level_for(n) for n in (0, 999, 1000, 3999, 4000, 9000)] == [1, 1, 2, 2, 3, 4]
    assert capacity_for(1) == 8 and capacity_for(2) == 12 and capacity_for(99) == 40


async def test_create_join_roles_kick(services, db):
    leader, a, b, c = [await hero(services, db, i, n) for i, n in ((1, "رهبر"), (2, "آرش"), (3, "سارا"), (4, "رها"))]
    before = leader.gold
    clan = await services.clans.create(leader, "شیرهای شمال")
    assert (await services.players.require(1)).gold == before - 1000 and clan.my_role == "leader"
    with pytest.raises(GameError, match="از قبل"):
        await services.clans.create(a, "شیرهای شمال")
    with pytest.raises(GameError, match="عضو"):
        await services.clans.create(leader, "دیگر خاندان")
    for p in (a, b, c):
        await services.clans.join(p, clan.id)

    assert await services.clans.set_role(leader, a.id, "deputy") == "معاون"
    # a deputy cannot make another deputy, but can make an elder
    with pytest.raises(GameError, match="پایین‌تر"):
        await services.clans.set_role(a, b.id, "deputy")
    await services.clans.set_role(a, b.id, "elder")
    # nobody kicks someone of equal or higher rank
    with pytest.raises(GameError, match="هم‌مقام"):
        await services.clans.kick(a, leader.id)
    with pytest.raises(GameError, match="کار رهبر و معاون"):
        await services.clans.kick(c, b.id)
    assert await services.clans.kick(a, c.id) == "رها"
    assert await services.clans.of(c.id) is None

    # leader cannot just leave; leadership can be transferred
    with pytest.raises(GameError, match="رهبر"):
        await services.clans.leave(leader)
    await services.clans.transfer(leader, a.id)
    view = await services.clans.of(a.id)
    assert view.my_role == "leader" and view.leader == "آرش"
    assert (await services.clans.of(leader.id)).my_role == "deputy"
    assert await services.clans.leave(leader) == "left"


async def test_closed_door_capacity_and_treasury(services, db):
    leader = await hero(services, db, 1, "رهبر", gold=10_000)
    clan = await services.clans.create(leader, "ققنوس ها")
    await services.clans.set_open(leader, False)
    guest = await hero(services, db, 2, "مهمان")
    with pytest.raises(GameError, match="بسته"):
        await services.clans.join(guest, clan.id)
    await services.clans.join(guest, clan.id, invited=True)

    view = await services.clans.donate(leader, 1_000)
    assert view.treasury == 1_000 and view.level == 2 and view.capacity == 12
    with pytest.raises(GameError):
        await services.clans.donate(guest, 10**9)
    assert (await services.clans.of(guest.id)).treasury == 1_000

    for i in range(10, 20):
        await services.clans.join(await hero(services, db, i, f"عضو{i}"), clan.id, invited=True)
    with pytest.raises(GameError, match="پر است"):
        await services.clans.join(await hero(services, db, 99, "دیرآمده"), clan.id, invited=True)


async def test_glass_flow_in_group(h, services, db):
    await hero(services, db, 1, "رهبر")
    a = await hero(services, db, 2, "آرش")
    await h.say(1, "خاندان", group=True)
    assert "ساخت خاندان" in h.session.sent()[-1]["text"]
    await h.say(1, "ساخت خاندان شیرها", group=True)
    assert "ساخته شد" in h.session.sent()[-1]["text"]
    await services.clans.join(a, (await services.clans.of(1)).id)

    await h.say(1, "خاندان", group=True)
    await h.click(1, h.button_data("اعضا"), group=True)
    assert "آرش" in "".join(h.labels())
    await h.click(1, h.button_data("آرش"), group=True)
    assert any("مقام معاون" in label for label in h.labels())
    await h.click(1, h.button_data("مقام معاون"), group=True)
    assert (await services.clans.of(2)).my_role == "deputy"
    await h.click(1, h.button_data("اخراج"), group=True)
    await h.click(1, h.button_data("بله"), group=True)
    assert await services.clans.of(2) is None

    # somebody else's panel buttons are refused
    data = h.button_data("بازگشت")
    await h.click(2, data, group=True)
    assert h.session.callback_answers()[-1].get("show_alert")


async def test_invite_by_reply_only_for_the_invited(h, services, db):
    leader, a = await hero(services, db, 1, "رهبر"), await hero(services, db, 2, "آرش")
    await services.clans.create(leader, "ستاره ها")
    await h.say(1, "دعوت خاندان", group=True, reply_to=h.message_of(2))
    sent = h.session.sent()[-1]
    assert "دعوت‌نامه" in sent["text"]
    data = sent["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    await h.click(3, data, group=True)
    assert await services.clans.of(a.id) is None
    await h.click(2, data, group=True)
    assert (await services.clans.of(a.id)).name == "ستاره ها"


async def test_duel_result_has_glass_buttons(h, services, db):
    await hero(services, db, 1, "آرش")
    await hero(services, db, 2, "سارا")
    await h.say(1, "مبارزه", group=True, reply_to=h.message_of(2))
    await h.click(2, h.button_data("قبول"), group=True)
    for _ in range(80):
        if any("پایان نبرد" in c[1].get("text", "") for c in h.session.calls if c[0] == "editMessageText"):
            break
        for uid in (1, 2):
            try:
                await h.click(uid, h.button_data("حمله"), group=True)
            except AssertionError:
                break
    labels = h.labels()
    assert any("برنده" in label or "مساوی" in label for label in labels)
    assert any("مبارزه‌ی دوباره" in label for label in labels)
