import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "warrior")


async def test_owner_gifts_by_reply_with_details_and_a_private_message(h, services):
    await hero(services, 1, "ارباب")
    target = await hero(services, 2, "آرش")
    gold = (await services.players.require(2)).gold
    await h.say(1, "اهدا سکه 100", group=True, reply_to=h.message_of(2))
    group_reply = [c for c in h.session.sent("sendMessage") if str(c["chat_id"]) == "-500"][-1]["text"]
    assert "هدیه از مالک قلمرو" in group_reply and "۱۰۰ سکه" in group_reply and "[آرش](uid:2)" in group_reply
    assert (await services.players.require(2)).gold == gold + 100
    dm = [c for c in h.session.sent("sendMessage") if str(c["chat_id"]) == "2"]
    assert dm and "مالک قلمرو" in dm[-1]["text"] and "۱۰۰ سکه" in dm[-1]["text"]

    await h.say(1, "اهدا کریستال 7", group=True, reply_to=h.message_of(2))
    assert (await services.players.require(2)).crystal == target.crystal + 7
    await h.say(1, "اهدا اشتراک 30", group=True, reply_to=h.message_of(2))
    assert (await services.players.require(2)).vip_until == services.ctx.now() + 30 * 86400
    await h.say(1, "اهدا اشتراک 30", group=True, reply_to=h.message_of(2))  # adds on top
    assert (await services.players.require(2)).vip_until == services.ctx.now() + 60 * 86400
    await h.say(1, "اهدا بلیط طلایی", group=True, reply_to=h.message_of(2))
    assert (await services.season.state(target)).premium
    await h.say(1, "اهدا بلیط طلایی", group=True, reply_to=h.message_of(2))
    assert "از قبل" in h.session.last_text()
    await h.say(1, "اهدا حیوان روباه", group=True, reply_to=h.message_of(2))
    assert await services.pets.owned(target.id) == {"fox": True}


async def test_only_the_owner_can_gift_and_a_reply_is_required(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 2, "آرش")
    await hero(services, 3, "سارا")
    gold = (await services.players.require(3)).gold
    n = len(h.session.calls)
    await h.say(2, "اهدا سکه 5000", group=True, reply_to=h.message_of(3))
    assert (await services.players.require(3)).gold == gold  # silently ignored
    assert not [c for c in h.session.calls[n:] if c[0] == "sendMessage"]
    await h.say(1, "اهدا سکه 100", group=True)
    assert "ریپلای" in h.session.last_text()
    await h.say(1, "اهدا سکه abc", group=True, reply_to=h.message_of(3))
    assert "مقدار را درست بنویسید" in h.session.last_text()
    await h.say(1, "اهدا حیوان اژدها", group=True, reply_to=h.message_of(3))
    assert "نام حیوان" in h.session.last_text()


async def test_admin_service_can_also_take_things_back(services):
    p = await hero(services, 5, "نگار")
    admin = services.admin
    assert await admin.grant_ticket(1, p.id, True) and not await admin.grant_ticket(1, p.id, True)
    assert await admin.grant_ticket(1, p.id, False) and not (await services.season.state(p)).premium
    until = await admin.set_vip(1, p.id, 10)
    assert until == services.ctx.now() + 10 * 86400
    assert await admin.set_vip(1, p.id, -3650) == 0
    assert await admin.grant_pet(1, p.id, "cat") and await admin.grant_pet(1, p.id, "fox")
    assert await admin.grant_pet(1, p.id, "cat", False)
    assert await services.pets.owned(p.id) == {"fox": True}  # the remaining pet becomes active
    with pytest.raises(GameError):
        await admin.grant_pet(1, p.id, "dragon")
    with pytest.raises(GameError):
        await admin.set_vip(1, p.id, 10**6)
