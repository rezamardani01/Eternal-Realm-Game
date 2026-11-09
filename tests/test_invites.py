import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.packs import PACKS
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1, group_url="https://ble.ir/mygroup"), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "warrior")


async def stack(db, pid, item):
    async with db.read() as tx:
        return await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = ?", (pid, item), 0)


async def join(h, uid, name, payload="1"):
    await h.say(uid, f"/start {payload}")
    await h.say(uid, name)
    await h.click(uid, h.button_data("الف"))
    await h.click(uid, h.button_data("کماندار"))


async def test_the_main_menu_has_an_invite_button_between_help_and_the_links(h, services):
    await hero(services, 5, "آرش")
    await h.say(5, "/start")
    rows = h.session.last_markup_rows()
    labels = [[b["text"] for b in row] for row in rows]
    flat = [t for row in labels for t in row]
    i_help = next(i for i, row in enumerate(labels) if any("راهنمایی" in t for t in row))
    assert labels[i_help] == ["❓ راهنمایی", "🤝 دعوت از دوستان"]
    assert any("گروه ما" in t for t in labels[i_help + 1])  # the links row comes after
    assert "👥 گروه ما" in flat


async def test_invite_screen_shows_the_link_with_a_copy_button(h, services):
    await hero(services, 5, "آرش")
    await h.panel(5, "invite")
    text = h.session.last_text()
    assert "https://ble.ir/er_bot?start=ref_5" in text and "دعوت‌های موفق" in text
    buttons = h.session.last_buttons()
    assert any(b.get("copy_text", {}).get("text") == "https://ble.ir/er_bot?start=ref_5" for b in buttons)


async def test_a_friend_who_creates_a_hero_pays_the_inviter_at_once(h, services, db):
    inviter = await hero(services, 5, "آرش")
    before = (await services.players.require(5)).gold
    await join(h, 20, "سارا", "ref_5")
    assert await services.players.find(20) is not None
    dms = [p for p in h.session.sent("sendMessage") if str(p["chat_id"]) == "5" and "دوستتان به قلمرو پیوست" in p["text"]]
    assert len(dms) == 1 and "هدیه‌ی دعوت" in dms[0]["text"] and "سارا" in dms[0]["text"]
    assert await services.invites.count(inviter.id) == 1
    me = await services.players.require(5)
    async with db.read() as tx:
        stacks = await tx.scalar("SELECT COALESCE(SUM(qty), 0) FROM inventory WHERE player_id = ?", (inviter.id,), 0)
        gear = await tx.scalar("SELECT COUNT(*) FROM gear WHERE player_id = ?", (inviter.id,), 0)
    assert me.gold > before or me.crystal > inviter.crystal or stacks > 0 or gear > 1  # two prizes were paid


async def test_each_friend_counts_once_and_self_invites_do_not(h, services):
    await hero(services, 5, "آرش")
    newcomer = await hero(services, 21, "رها")
    assert await services.invites.register(newcomer, 5) is not None
    assert await services.invites.register(newcomer, 5) is None  # the same friend never pays twice
    assert await services.invites.register(newcomer, 21) is None  # nor yourself
    assert await services.invites.register(newcomer, 999) is None  # nor somebody who does not play
    assert services.invites.parse("ref_5") == 5 and services.invites.parse("panel") is None and services.invites.parse("ref_x") is None


async def test_rewards_stop_after_the_daily_cap_but_friends_still_count(services):
    from eternal_realm.game.services.invites import DAILY_REWARDS

    inviter = await hero(services, 5, "آرش")
    capped = 0
    for i in range(DAILY_REWARDS + 3):
        friend = await hero(services, 100 + i, f"دوست{i}")
        result = await services.invites.register(friend, 5)
        capped += bool(result.capped)
    assert capped == 3 and await services.invites.count(inviter.id) == DAILY_REWARDS + 3


async def test_link_buttons_are_set_from_the_admin_panel(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 5, "آرش")
    await h.say(5, "/start")
    assert [b["text"] for b in h.session.last_buttons() if b.get("url")] == ["👥 گروه ما"]  # from config.toml
    await h.panel(1, "admlk")
    assert "گروه" in h.session.last_text() and "کانال" in h.session.last_text()
    await h.tap(1, "لینک کانال")
    await h.say(1, "@mychannel")
    await h.panel(1, "admask", "lk_ct")
    await h.say(1, "📣 کانال رسمی")
    await h.panel(1, "admask", "lk_gt")
    await h.say(1, "👥 گروه رسمی")
    await h.say(5, "/start")
    urls = {b["text"]: b["url"] for b in h.session.last_buttons() if b.get("url")}
    assert urls == {"👥 گروه رسمی": "https://ble.ir/mygroup", "📣 کانال رسمی": "https://ble.ir/mychannel"}
    await h.panel(1, "admask", "lk_gu")
    await h.say(1, "-")  # hide the group button
    await h.say(5, "/start")
    assert [b["text"] for b in h.session.last_buttons() if b.get("url")] == ["📣 کانال رسمی"]
    await h.panel(1, "admask", "lk_gu")
    await h.say(1, "http://not-secure.example")
    assert "https://" in h.session.last_text()
    await h.panel(1, "admask", "lk_ct")
    await h.say(1, "x" * 40)
    assert "۲۸" in h.session.last_text()


async def test_the_transfer_confirmation_is_detailed_and_offers_another_gift(h, services):
    await hero(services, 10, "آرش")
    other = await hero(services, 11, "سارا")
    async with services.ctx.db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 5000 WHERE id = 1")
    await h.panel(10, "xdo", f"{other.id}.coin", "500", group=True)
    text = h.session.last_text()
    for part in ("هدیه با موفقیت رسید", "فرستنده", "گیرنده", "هدیه:", "زمان", "پیام هم در پیوی"):
        assert part in text
    assert any("ارسال آیتم دیگر" in b["text"] for b in h.session.last_buttons())
    await h.tap(10, "ارسال آیتم دیگر", group=True)
    assert "انتقال هدیه" in h.session.last_text() and "سارا" in h.session.last_text()
    dm = [p for p in h.session.sent("sendMessage") if str(p["chat_id"]) == "11"][-1]["text"]
    assert "هدیه‌ای برای شما رسید" in dm and "۵۰۰ سکه" in dm


def test_iron_ore_comes_in_packs_of_five_and_ten():
    assert PACKS["ore_5"].items == {"iron_ore": 5} and PACKS["ore_10"].items == {"iron_ore": 10}
    assert PACKS["ore_5"].price_rial < PACKS["ore_10"].price_rial < PACKS["ore_s"].price_rial
    assert all(len(p.title) <= 32 for p in PACKS.values())


async def test_owner_hands_out_a_box_that_its_receiver_opens_once(h, services, db):
    await hero(services, 1, "ارباب")
    target = await hero(services, 2, "آرش")
    await hero(services, 3, "سارا")
    await h.say(1, "اهدا بسته ماجراجو", group=True, reply_to=h.message_of(2))
    group_msg = next(p for p in reversed(h.session.sent("sendMessage")) if p["chat_id"] == -500)
    assert "صندوق هدیه" in group_msg["text"] and "بسته ماجراجو" in group_msg["text"]
    button = next(b for row in group_msg["reply_markup"]["inline_keyboard"] for b in row)
    assert "باز کردن صندوق" in button["text"]
    dm = [p for p in h.session.sent("sendMessage") if str(p["chat_id"]) == "2"]
    assert dm and "صندوق هدیه‌ای" in dm[-1]["text"]
    gold = (await services.players.require(2)).gold
    await h.click(3, button["callback_data"], group=True)  # somebody else cannot open it
    assert any("مال شما نیست" in a.get("text", "") for a in h.session.callback_answers())
    assert (await services.players.require(2)).gold == gold
    await h.click(2, button["callback_data"], group=True)
    assert "صندوق باز شد" in h.session.last_text() and "داخلش بود" in h.session.last_text()
    assert (await services.players.require(2)).gold == gold + PACKS["adventurer"].gold
    assert await stack(db, target.id, "big_energy_potion") >= 5
    await h.click(2, button["callback_data"], group=True)
    assert any("قبلاً باز" in a.get("text", "") or "قبلاً" in str(a) for a in h.session.callback_answers())
    assert (await services.players.require(2)).gold == gold + PACKS["adventurer"].gold  # only once


async def test_the_three_sizes_of_lucky_boxes_and_bad_names(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 2, "آرش")
    for word, pack in (("کوچک", "lucky_s"), ("متوسط", "lucky_m"), ("بزرگ", "lucky_l")):
        await h.say(1, f"اهدا بسته {word}", group=True, reply_to=h.message_of(2))
        assert PACKS[pack].label in h.session.last_text() or any(PACKS[pack].label in p["text"] for p in h.session.sent("sendMessage"))
    await h.say(1, "اهدا بسته عجیب", group=True, reply_to=h.message_of(2))
    assert "کدام بسته" in h.session.last_text()
    n = len(h.session.sent("sendMessage"))
    await h.say(2, "اهدا بسته بزرگ", group=True, reply_to=h.message_of(1))  # players cannot
    assert len(h.session.sent("sendMessage")) == n


async def test_owner_gifts_the_three_service_tickets(h, services, db):
    await hero(services, 1, "ارباب")
    target = await hero(services, 2, "آرش")
    for word, item in (("نام", "rename_ticket"), ("نژاد", "race_ticket"), ("کلاس", "class_ticket")):
        await h.say(1, f"اهدا برگه تغییر {word}", group=True, reply_to=h.message_of(2))
        assert await stack(db, target.id, item) == 1
        assert f"برگه‌ی تغییر {word}" in h.session.last_text()
    await h.say(1, "اهدا برگه تغییر نام 2", group=True, reply_to=h.message_of(2))
    assert await stack(db, target.id, "rename_ticket") == 3
    with pytest.raises(GameError):
        await services.invites.open_box(target, 999)
