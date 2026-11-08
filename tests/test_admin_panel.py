import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet

from .harness import Harness

CHAT = -500


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1, admin_ids=(5,)), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid, name, level=5):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    return p


async def stack(db, pid, item):
    async with db.read() as tx:
        return await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = ?", (pid, item), 0)


async def test_only_admins_open_the_panel_and_it_shows_the_numbers(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 2, "آرش")
    await h.say(2, "پنل مدیریت")
    assert not h.session.sent("sendMessage")  # silent for players
    await h.say(1, "پنل مدیریت")
    text = h.session.last_text()
    assert "پنل مدیریت قلمرو" in text and "بازیکنان" in text and "سکه در گردش" in text
    labels = " ".join(h.labels())
    for name in ("بازیکنان", "گروه‌ها", "خاندان‌ها", "فروش", "پیام همگانی", "عضویت اجباری", "گزارش مدیریت", "دستورات مالک"):
        assert name in labels
    await h.tap(1, "دستورات مالک")
    assert "اهدا مسیر قهرمانی" in h.session.last_text()


async def test_a_player_cannot_use_the_panel_screens_directly(h, services):
    await hero(services, 2, "آرش")
    await h.panel(2, "adm")
    assert any("فقط برای مدیران" in a.get("text", "") or "مدیران" in str(a) for a in h.session.callback_answers()) or "مدیران" in h.session.last_text()


async def test_search_and_manage_a_player_with_prompts(h, services, db):
    await hero(services, 1, "ارباب")
    target = await hero(services, 2, "آرش")
    await h.panel(1, "admp")
    await h.tap(1, "جستجو")
    assert "نام یا بخشی از نام" in h.session.last_text()
    await h.say(1, "آرش")
    assert "نتیجه‌ی جستجو" in h.session.last_text()
    await h.tap(1, "آرش")
    assert "آرش" in h.session.last_text() and "شناسه‌ی بله" in h.session.last_text()

    gold = (await services.players.require(2)).gold
    await h.tap(1, "سکه")
    await h.say(1, "3000")
    assert (await services.players.require(2)).gold == gold + 3000 and "اضافه شد" in h.session.last_text()
    await h.panel(1, "admpc", str(target.id))
    await h.tap(1, "کریستال")
    await h.say(1, "200")
    assert (await services.players.require(2)).crystal == target.crystal + 200
    await h.panel(1, "admpc", str(target.id))
    await h.tap(1, "آیتم")
    await h.say(1, "سنگ آهن 399")
    assert await stack(db, target.id, "iron_ore") == 399
    await h.panel(1, "admpc", str(target.id))
    await h.tap(1, "سطح")
    await h.say(1, "40")
    assert (await services.players.require(2)).level == 40
    await h.panel(1, "admpc", str(target.id))
    await h.tap(1, "VIP")
    await h.say(1, "30")
    assert (await services.players.require(2)).vip_until > services.ctx.now()
    await h.panel(1, "admpc", str(target.id))
    await h.tap(1, "عنوان")
    await h.say(1, "قهرمان بزرگ")
    assert (await services.players.require(2)).honor == "قهرمان بزرگ"
    await h.panel(1, "admpc", str(target.id))
    await h.tap(1, "عنوان")
    await h.say(1, "ابله!")  # a bad amount for another prompt must not matter here
    await h.panel(1, "admpc", str(target.id))
    await h.tap(1, "سکه")
    await h.say(1, "abc")
    assert "عدد درست" in h.session.last_text()
    assert (await services.players.require(2)).gold == gold + 3000


async def test_ticket_pet_energy_and_ban_buttons(h, services, db):
    await hero(services, 1, "ارباب")
    target = await hero(services, 2, "آرش")
    await h.panel(1, "admtk", str(target.id))
    assert "بلیط طلایی داده شد" in h.session.last_text()
    await h.panel(1, "admtk", str(target.id))
    assert "پس گرفته شد" in h.session.last_text()
    await h.panel(1, "admpet", str(target.id), "cat")
    assert "داده شد" in h.session.last_text()
    assert await services.pets.owned(target.id) == {"cat": True}
    await h.panel(1, "admen", str(target.id))
    await h.panel(1, "admcd", str(target.id))
    await h.panel(1, "admban", str(target.id))
    assert "تأیید مسدود کردن" in h.session.last_text()
    assert not (await services.players.require(2)).banned  # nothing happens before «yes»
    await h.tap(1, "بله")
    assert (await services.players.require(2)).banned
    await h.panel(1, "admpl", "0", "ban")
    assert "آرش" in " ".join(h.labels())
    await h.panel(1, "admban", str(target.id))
    await h.tap(1, "بله")
    assert not (await services.players.require(2)).banned
    await h.panel(1, "admban", "1")  # the owner himself
    await h.tap(1, "بله")
    assert not (await services.players.require(1)).banned


async def test_group_card_toggle_message_and_event(h, services, db):
    await hero(services, 1, "ارباب")
    await services.groups.touch(CHAT, "گروه تست")
    await h.panel(1, "admg")
    assert "گروه تست" in " ".join(h.labels())
    await h.panel(1, "admgc", str(CHAT))
    await h.tap(1, "غیرفعال کردن")
    assert "غیرفعال شد" in h.session.last_text() and not (await services.groups.get(CHAT)).enabled
    await h.tap(1, "فعال کردن")
    assert (await services.groups.get(CHAT)).enabled
    await h.tap(1, "پیام به گروه")
    await h.say(1, "سلام به قلمرو")
    assert any(p["chat_id"] == CHAT and p["text"] == "سلام به قلمرو" for p in h.session.sent("sendMessage"))
    await h.panel(1, "admge", str(CHAT))
    assert "ساخت رویداد" in h.session.last_text()
    await h.panel(1, "admge", str(CHAT), "meteor")
    assert any(v.kind == "meteor" for v in await services.events.active(CHAT))


async def test_broadcast_needs_a_preview_and_a_yes(h, services):
    await hero(services, 1, "ارباب")
    await services.groups.touch(CHAT, "گروه تست")
    await h.panel(1, "admbc")
    await h.tap(1, "نوشتن پیام")
    await h.say(1, "خبر مهم برای همه")
    assert "پیش‌نمایش" in h.session.last_text()
    n = len([p for p in h.session.sent("sendMessage") if p["chat_id"] == CHAT])
    await h.tap(1, "ارسال به همه")
    assert len([p for p in h.session.sent("sendMessage") if p["chat_id"] == CHAT]) == n + 1
    assert "فرستاده شد" in h.session.last_text()
    await h.panel(1, "admbcok")
    assert any("پیامی برای ارسال نیست" in a.get("text", "") or "پیامی" in str(a) for a in h.session.callback_answers()) or "پیامی" in h.session.last_text()


async def test_forced_membership_can_be_managed_from_the_panel(h, services):
    await hero(services, 1, "ارباب")
    await h.panel(1, "admm")
    assert "خاموش" in h.session.last_text()
    await h.tap(1, "روشن کردن")
    assert not (await services.membership.settings())[0]  # no channel yet: refused, stays off
    await h.panel(1, "admm")
    await h.tap(1, "افزودن کانال")
    await h.say(1, "@mychannel کانال ما")
    assert [c.chat for c in (await services.membership.settings())[1]] == ["@mychannel"]
    await h.panel(1, "admm")
    await h.tap(1, "روشن کردن")
    assert (await services.membership.settings())[0]
    await h.tap(1, "حذف")
    enabled, channels = await services.membership.settings()
    assert channels == [] and not enabled  # removing the last channel switches the gate off
    await h.panel(1, "admm")
    await h.tap(1, "افزودن کانال")
    await h.say(1, "not a channel")
    assert "شناسه" in h.session.last_text()


async def test_lists_orders_clans_and_audit_screens_render(h, services, db):
    await hero(services, 1, "ارباب")
    await hero(services, 2, "آرش")
    async with db.transaction() as tx:
        await wallet.apply(tx, 2, gold=1, reason="t", now=services.ctx.now())
    for screen in ("admpl", "admcl", "admo", "adma", "admc"):
        await h.panel(1, screen)
        assert h.session.last_text()
    await h.panel(1, "admpl", "0", "new")
    assert "آرش" in " ".join(h.labels())
    await h.panel(1, "admtk", "2")
    await h.panel(1, "adma")
    assert "grant_ticket" in h.session.last_text()


async def test_an_admin_in_the_list_can_use_the_panel_too(h, services):
    await hero(services, 5, "مدیر")
    await h.say(5, "پنل مدیریت")
    assert "پنل مدیریت قلمرو" in h.session.last_text()
