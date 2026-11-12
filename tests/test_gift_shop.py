import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.packs import PACKS
from eternal_realm.shared.errors import GameError

from .harness import Harness

OWNER = 999


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=OWNER, provider_token="WALLET-TEST"), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "archer")


def reply_texts(h, chat):
    return [p["text"] for n, p in h.session.calls if n == "sendMessage" and p.get("chat_id") == chat]


async def test_the_gift_word_needs_somebody_to_gift(h, services):
    await hero(services, 1, "فرستنده")
    await hero(services, 2, "گیرنده")
    await h.say(1, "گیفت", group=True)
    assert "ریپلای" in h.session.last_text()
    await h.say(1, "گیفت", group=True, reply_to=h.message_of(1))
    assert "برای دیگران است" in h.session.last_text()
    await h.say(1, "گیفت", group=True, reply_to=h.message_of(2))
    assert "گیفت از خزانه قلمرو" in h.session.last_text()
    labels = " ".join(h.labels())
    assert "بسته‌های سکه" in labels and "گردونه شانس" in labels and "منابع دهکده" in labels


async def test_the_whole_gift_flow_from_the_group_to_the_invoice_to_the_message(h, services):
    sender = await hero(services, 1, "فرستنده")
    target = await hero(services, 2, "گیرنده")
    gold = target.gold
    await h.say(1, "گیفت", group=True, reply_to=h.message_of(2))
    await h.tap(1, "بسته‌های سکه", group=True)
    await h.tap(1, "×۵٬۰۰۰", group=True)
    await h.tap(1, "×۲", group=True)
    assert "تأیید هدیه" in h.session.last_text()
    await h.click(2, h.button_data("بله، فاکتور"), group=True)  # somebody else cannot press it
    assert not h.session.sent("sendInvoice")
    await h.tap(1, "بله، فاکتور", group=True)
    invoice = h.session.sent("sendInvoice")[-1]
    assert invoice["chat_id"] == 1 and invoice["prices"][0]["amount"] == PACKS["coins_s"].price_rial * 2
    assert "فاکتور هدیه فرستاده شد" in h.session.last_text()
    await h.precheckout(1, invoice["payload"], invoice["prices"][0]["amount"])
    assert h.session.sent("answerPreCheckoutQuery")[-1]["ok"] is True
    await h.paid(1, invoice["payload"], invoice["prices"][0]["amount"], "gift-1")
    assert (await services.players.require(2)).gold == gold + 2 * PACKS["coins_s"].gold  # it went to the recipient...
    assert (await services.players.require(1)).gold == sender.gold  # ...not to the payer
    assert any("هدیه‌ی ویژه رسید" in t and "فرستنده" in t for t in reply_texts(h, 2))
    assert any("گیرنده" in t and "فعال شد" in t for t in reply_texts(h, 1))
    assert any("هدیه برای: گیرنده" in t for t in reply_texts(h, OWNER))
    await h.paid(1, invoice["payload"], invoice["prices"][0]["amount"], "gift-1")  # the same payment again
    assert (await services.players.require(2)).gold == gold + 2 * PACKS["coins_s"].gold


async def test_gifts_that_would_be_useless_are_refused_before_any_money_moves(services, db):
    a, b = await hero(services, 1, "فرستنده"), await hero(services, 2, "گیرنده")
    with pytest.raises(GameError, match="شهری"):
        await services.payments.create_gift_order(a, b.id, "city_res_m", 1)
    with pytest.raises(GameError, match="برای دیگران"):
        await services.payments.create_gift_order(a, a.id, "coins_s", 1)
    with pytest.raises(GameError, match="تعداد"):
        await services.payments.create_gift_order(a, b.id, "coins_s", 11)
    with pytest.raises(GameError, match="چنین بسته"):
        await services.payments.create_gift_order(a, b.id, "nope", 1)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 500 WHERE id = ?", (b.id,))
    with pytest.raises(GameError, match="بالاترین سطح"):
        await services.payments.create_gift_order(a, b.id, "xp_s", 1)
    async with db.transaction() as tx:
        await services.pets.grant(tx, b.id, "fox")
    with pytest.raises(GameError, match="حیوان"):
        await services.payments.create_gift_order(a, b.id, "pet_fox", 1)


async def test_a_gifted_wheel_pack_and_a_city_pack_arrive(services, db):
    from eternal_realm.game.data import city as d

    a, b = await hero(services, 1, "فرستنده"), await hero(services, 2, "گیرنده")
    order = await services.payments.create_gift_order(a, b.id, "wheel_5", 2)
    delivery = await services.payments.complete(1, order.payload, order.amount, "g-wheel")
    assert delivery.recipient_id == b.id and await services.wheel.spins(b.id) == 10 and await services.wheel.spins(a.id) == 0
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 10 WHERE id = ?", (b.id,))
        await wallet.apply(tx, b.id, gold=50_000, reason="t", now=services.ctx.now())
    await services.city.found(await services.players.require(2), "گیرنده‌آباد", d.FLAGS[0][0])
    before = (await services.city.mine(await services.players.require(2))).res["wood"]
    order = await services.payments.create_gift_order(a, b.id, "city_res_s", 1)
    await services.payments.complete(1, order.payload, order.amount, "g-city")
    after = (await services.city.mine(await services.players.require(2))).res["wood"]
    assert after >= before + 5_000 - 1


async def test_the_realm_search_shows_whatever_is_at_hand_whatever_its_strength(services, db):
    from eternal_realm.game.data import city as d

    async def city_of(uid, name, level=10):
        p = await services.players.register(uid, f"u{uid}", f"قهرمان{uid}", "elf", "archer")
        async with db.transaction() as tx:
            await wallet.apply(tx, p.id, gold=50_000, reason="t", now=services.ctx.now())
            await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        c = await services.city.found(await services.players.require(uid), name, d.FLAGS[0][0])
        async with db.transaction() as tx:
            await tx.execute("UPDATE cities SET shield_until = 0 WHERE id = ?", (c.id,))
        return p, c

    weak_p, weak = await city_of(1, "ضعیف‌آباد")
    strong_p, strong = await city_of(2, "قدرت‌آباد")
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO city_troops (city_id, kind, qty) VALUES (?, 'sword', 5)", (weak.id,))
        await tx.execute("INSERT INTO city_troops (city_id, kind, qty) VALUES (?, 'sword', 900)", (strong.id,))
        await tx.execute("UPDATE city_buildings SET level = 1 WHERE city_id = ? AND kind = 'wall'", (strong.id,))
        await tx.execute("INSERT INTO city_buildings (city_id, kind, level) VALUES (?, 'wall', 8)", (strong.id,))
    found = await services.city.search(weak_p)  # the weak hero is shown the giant: no matching by power
    assert found.city.id == strong.id
