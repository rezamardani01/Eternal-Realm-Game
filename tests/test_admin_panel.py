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
    for name in ("بازیکنان", "گروه‌ها", "خاندان‌ها", "فروش", "همگانی", "هدیه‌ی همگانی", "عضویت اجباری", "حالت تعمیر", "پشتیبان", "گزارش مدیریت", "دستورات مالک"):
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
    await h.tap(1, "ارسال همگانی به گروه‌ها")
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


async def test_forward_broadcast_goes_to_every_active_group(h, services):
    await hero(services, 1, "ارباب")
    await services.groups.touch(CHAT, "گروه ۱")
    await services.groups.touch(-600, "گروه ۲")
    await h.panel(1, "admbc")
    assert "فوروارد همگانی" in " ".join(h.labels())
    await h.tap(1, "فوروارد همگانی")
    await h.say(1, "این پیام را برای همه فوروارد کن")
    assert "فوروارد همگانی" in h.session.last_text() and "۲ گروه" in h.session.last_text()
    assert not h.session.sent("forwardMessage")  # nothing before the choice
    await h.tap(1, "فوروارد")
    forwards = h.session.sent("forwardMessage")
    assert sorted(str(f["chat_id"]) for f in forwards) == ["-500", "-600"]
    assert "فوروارد همگانی انجام شد" in h.session.last_text()
    await h.panel(1, "admfwok", "copy")  # nothing left to send
    assert len(h.session.sent("forwardMessage")) == 2


async def test_copy_broadcast_has_no_forward_label(h, services):
    await hero(services, 1, "ارباب")
    await services.groups.touch(CHAT, "گروه ۱")
    await h.panel(1, "admask", "fwd")
    await h.say(1, "پیام برای کپی")
    await h.tap(1, "کپی")
    assert h.session.sent("copyMessage") and not h.session.sent("forwardMessage")


async def test_private_message_to_all_players(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 2, "آرش")
    await hero(services, 3, "سارا")
    await h.panel(1, "admask", "dm")
    await h.say(1, "خبر خوش برای همه")
    assert "پیش‌نمایش" in h.session.last_text() and "۳ بازیکن" in h.session.last_text()
    await h.tap(1, "ارسال به همه")
    import asyncio
    for _ in range(50):
        await asyncio.sleep(0.05)
        if any("پیام به بازیکنان تمام شد" in p.get("text", "") for p in h.session.sent("sendMessage")):
            break
    got = {str(p["chat_id"]) for p in h.session.sent("sendMessage") if "خبر خوش برای همه" in p.get("text", "")}
    assert got == {"1", "2", "3"}


async def test_gift_for_everybody_needs_a_yes_and_skips_the_banned(h, services, db):
    await hero(services, 1, "ارباب")
    a = await hero(services, 2, "آرش")
    b = await hero(services, 3, "سارا")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET banned = 1 WHERE id = ?", (b.id,))
    gold = (await services.players.require(2)).gold
    await h.panel(1, "admask", "gift_gold")
    await h.say(1, "500")
    assert "تأیید هدیه" in h.session.last_text()
    assert (await services.players.require(2)).gold == gold  # nothing before «yes»
    await h.tap(1, "بله")
    assert (await services.players.require(2)).gold == gold + 500
    assert (await services.players.require(3)).gold == b.gold  # banned
    await h.panel(1, "admask", "gift_vip")
    await h.say(1, "7")
    await h.tap(1, "بله")
    assert (await services.players.require(2)).vip_until > services.ctx.now()
    await h.panel(1, "admask", "gift_gold")
    await h.say(1, "99999999")
    assert "حداکثر" in h.session.last_text()


async def test_maintenance_mode_locks_players_but_not_managers(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 2, "آرش")
    await h.panel(1, "admmn")
    assert "خاموش" in h.session.last_text()
    await h.tap(1, "روشن کردن")
    assert "روشن" in h.session.last_text()
    await h.tap(1, "تغییر متن")
    await h.say(1, "یک ساعت دیگر برمی‌گردیم")
    assert (await services.admin.maintenance()) == (True, "یک ساعت دیگر برمی‌گردیم")
    await h.say(2, "/start")
    assert "قلمرو در حال تعمیر است" in h.session.last_text() and "یک ساعت دیگر" in h.session.last_text()
    await h.say(1, "پنل مدیریت")  # the owner still works
    assert "پنل مدیریت قلمرو" in h.session.last_text()
    await h.panel(1, "admmnt")
    await h.say(2, "/start")
    assert "تعمیر" not in h.session.last_text()


async def test_backup_pm_rename_and_leave_group(h, services, db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    await hero(services, 1, "ارباب")
    target = await hero(services, 2, "آرش")
    await h.panel(1, "admbk")
    assert "نسخه‌ی پشتیبان ساخته شد" in h.session.last_text()
    assert list((tmp_path / "backups").glob("game-*.db"))
    await h.tap(1, "دریافت فایل")
    assert h.session.sent("sendDocument")
    await h.panel(1, "admask", "pmsg", str(target.id))
    await h.say(1, "سلام از مدیریت")
    assert any(str(p["chat_id"]) == "2" and "سلام از مدیریت" in p["text"] for p in h.session.sent("sendMessage"))
    await h.panel(1, "admask", "rename", str(target.id))
    await h.say(1, "آرش بزرگ")
    assert (await services.players.require(2)).name == "آرش بزرگ"
    await services.groups.touch(CHAT, "گروه تست")
    await h.panel(1, "admgl", str(CHAT))
    assert "ترک گروه" in h.session.last_text() and not h.session.sent("leaveChat")
    await h.tap(1, "بله")
    assert h.session.sent("leaveChat") and not (await services.groups.get(CHAT)).enabled


async def test_event_in_all_groups(h, services):
    await hero(services, 1, "ارباب")
    await services.groups.touch(CHAT, "گروه ۱")
    await services.groups.touch(-600, "گروه ۲")
    await h.panel(1, "admbe")
    await h.tap(1, "شهاب")
    assert "۲ گروه" in h.session.last_text()
    for chat in (CHAT, -600):
        assert any(v.kind == "meteor" for v in await services.events.active(chat))
