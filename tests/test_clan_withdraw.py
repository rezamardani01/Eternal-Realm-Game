import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import clans as clan_repo
from eternal_realm.db.repos import wallet
from eternal_realm.game.services.clans import WITHDRAW_TTL
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


BASE = 500  # the gold every new hero starts with


async def clan_with_treasury(services, db, treasury=3_000):
    owner = await hero(services, db, 1, "رهبر", gold=50_000)
    member = await hero(services, db, 2, "آرش", gold=0)
    assert member.gold == BASE
    clan = await services.clans.create(owner, "شیرهای شمال")
    await services.clans.join(member, clan.id)
    await services.clans.donate(owner, treasury)
    return owner, member, clan


async def gold_of(services, uid):
    return (await services.players.require(uid)).gold


async def treasury_of(services, player):
    return (await services.clans.of(player.id)).treasury


async def test_approved_request_pays_the_member_and_empties_the_treasury(services, db):
    owner, member, _ = await clan_with_treasury(services, db)
    asked = await services.clans.request_withdrawal(member, 1_200)
    assert asked.status == "pending" and not asked.instant and asked.leader_user_id == 1
    assert await gold_of(services, 2) == BASE  # nothing moves before the owner answers
    assert await treasury_of(services, owner) == 3_000

    done = await services.clans.decide_withdrawal(owner, asked.id, True)
    assert done.status == "approved"
    assert await gold_of(services, 2) == BASE + 1_200
    assert await treasury_of(services, owner) == 1_800


async def test_rejected_request_moves_nothing(services, db):
    owner, member, _ = await clan_with_treasury(services, db)
    asked = await services.clans.request_withdrawal(member, 1_000)
    assert (await services.clans.decide_withdrawal(owner, asked.id, False)).status == "rejected"
    assert await gold_of(services, 2) == BASE and await treasury_of(services, owner) == 3_000
    await services.clans.request_withdrawal(member, 500)  # after the answer the member may ask again


async def test_an_answer_counts_once(services, db):
    owner, member, _ = await clan_with_treasury(services, db)
    asked = await services.clans.request_withdrawal(member, 1_000)
    await services.clans.decide_withdrawal(owner, asked.id, True)
    for approve in (True, False):
        with pytest.raises(GameError, match="قبلاً جواب"):
            await services.clans.decide_withdrawal(owner, asked.id, approve)
    assert await gold_of(services, 2) == BASE + 1_000 and await treasury_of(services, owner) == 2_000


async def test_only_the_owner_answers(services, db):
    owner, member, _ = await clan_with_treasury(services, db)
    asked = await services.clans.request_withdrawal(member, 1_000)
    with pytest.raises(GameError, match="فقط مالک"):
        await services.clans.decide_withdrawal(member, asked.id, True)
    stranger = await hero(services, db, 7, "غریبه", gold=50_000)
    await services.clans.create(stranger, "دیگران")
    with pytest.raises(GameError, match="فقط مالک"):
        await services.clans.decide_withdrawal(stranger, asked.id, True)
    assert await gold_of(services, 2) == BASE


async def test_amount_checks_and_one_open_request(services, db):
    _, member, _ = await clan_with_treasury(services, db, treasury=1_000)
    for bad in (0, -5):
        with pytest.raises(GameError):
            await services.clans.request_withdrawal(member, bad)
    with pytest.raises(GameError, match="خزانه"):
        await services.clans.request_withdrawal(member, 1_001)
    first = await services.clans.request_withdrawal(member, 400)
    with pytest.raises(GameError, match="بی‌پاسخ"):
        await services.clans.request_withdrawal(member, 100)
    assert (await services.clans.my_withdrawal(member)).id == first.id
    await services.clans.cancel_withdrawal(member, first.id)
    assert await services.clans.my_withdrawal(member) is None
    await services.clans.request_withdrawal(member, 100)


async def test_the_treasury_spent_meanwhile_blocks_the_approval(services, db):
    owner, member, _ = await clan_with_treasury(services, db, treasury=1_000)
    asked = await services.clans.request_withdrawal(member, 800)
    async with db.transaction() as tx:
        await tx.execute("UPDATE clans SET treasury = 100")
    with pytest.raises(GameError, match="کافی نیست"):
        await services.clans.decide_withdrawal(owner, asked.id, True)
    assert await gold_of(services, 2) == BASE
    assert (await services.clans.withdrawal(asked.id)).status == "pending"  # still open: the owner may reject it


async def test_a_member_who_left_is_paid_nothing(services, db):
    owner, member, _ = await clan_with_treasury(services, db)
    asked = await services.clans.request_withdrawal(member, 1_000)
    await services.clans.leave(member)
    assert await services.clans.pending_withdrawals(owner) == []
    done = await services.clans.decide_withdrawal(owner, asked.id, True)
    assert done.left and await gold_of(services, 2) == BASE


async def test_an_old_request_lapses(services, db, clock):
    owner, member, _ = await clan_with_treasury(services, db)
    asked = await services.clans.request_withdrawal(member, 1_000)
    clock.advance(WITHDRAW_TTL + 1)
    assert await services.clans.pending_withdrawals(owner) == []
    assert await services.clans.my_withdrawal(member) is None
    with pytest.raises(GameError, match="قدیمی"):
        await services.clans.decide_withdrawal(owner, asked.id, True)


async def test_the_owner_takes_from_the_treasury_at_once(services, db):
    owner, _, _ = await clan_with_treasury(services, db)
    before = await gold_of(services, 1)
    made = await services.clans.request_withdrawal(owner, 500)
    assert made.instant and made.status == "approved"
    assert await gold_of(services, 1) == before + 500 and await treasury_of(services, owner) == 2_500


async def test_the_pending_list_is_the_owners_only(services, db):
    owner, member, _ = await clan_with_treasury(services, db)
    await services.clans.request_withdrawal(member, 300)
    assert [w.amount for w in await services.clans.pending_withdrawals(owner)] == [300]
    assert await services.clans.pending_withdrawals(member) == []


async def test_disbanding_removes_the_requests(services, db):
    _, member, clan = await clan_with_treasury(services, db)
    await services.clans.request_withdrawal(member, 300)
    async with db.transaction() as tx:
        await clan_repo.delete(tx, clan.id)
        assert await tx.scalar("SELECT COUNT(*) FROM clan_withdrawals", (), 0) == 0


async def test_flow_in_the_bot_chat(h, services, db):
    await clan_with_treasury(services, db)
    await h.say(2, "خاندان")
    await h.click(2, h.button_data("کمک به خزانه"))
    await h.click(2, h.button_data("برداشت از خزانه"))
    h.session.reset()
    await h.say(2, "abc")
    assert "فقط یک عدد" in h.session.last_text()
    await h.say(2, "۱۵۰۰")
    assert any("درخواست برداشت فرستاده شد" in t for t in h.session.texts())
    asks = [m for m in h.session.sent() if m.get("chat_id") == 1 and "درخواست برداشت از خزانه" in m["text"]]
    assert asks, "the owner was not told"

    data = h.button_data("تأیید")
    h.session.reset()
    await h.click(1, data)
    approved = [m for m in h.session.sent() if m.get("chat_id") == 2]
    assert approved and "تأیید شد" in approved[-1]["text"]
    assert await gold_of(services, 2) == BASE + 1_500


async def test_the_owner_rejecting_tells_the_member(h, services, db):
    owner, member, _ = await clan_with_treasury(services, db)
    asked = await services.clans.request_withdrawal(member, 700)
    await h.panel(1, "clanwdno", str(asked.id))
    told = [m for m in h.session.sent() if m.get("chat_id") == 2]
    assert told and "رد شد" in told[-1]["text"]
    assert await gold_of(services, 2) == BASE and await treasury_of(services, owner) == 3_000
