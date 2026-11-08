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


async def test_settings_are_validated_and_saved(services):
    assert await services.membership.settings() == (False, [])
    with pytest.raises(GameError, match="دست‌کم"):
        await services.membership.save(True, [])
    with pytest.raises(GameError, match="شناسه"):
        await services.membership.save(True, [{"chat": "not a channel"}])
    with pytest.raises(GameError, match="https"):
        await services.membership.save(True, [{"chat": "@mychannel", "link": "http://x.y"}])
    with pytest.raises(GameError, match="دو بار"):
        await services.membership.save(True, [{"chat": "@abc"}, {"chat": "@abc"}])
    with pytest.raises(GameError, match="حداکثر"):
        await services.membership.save(True, [{"chat": f"@chan{i}"} for i in range(9)])
    await services.membership.save(True, [{"chat": "@mychannel", "title": "کانال ما", "link": "https://ble.ir/join/x"}])
    enabled, channels = await services.membership.settings()
    assert enabled and channels[0].chat == "@mychannel" and channels[0].url == "https://ble.ir/join/x"


async def test_disabled_gate_lets_everybody_in(h, services):
    await h.say(5, "/start")
    assert "عضویت در کانال لازم است" not in h.session.last_text()


async def test_start_is_blocked_until_the_user_joins_then_works(h, services):
    await services.membership.save(True, [{"chat": "@mychannel", "title": "کانال ما"}])
    h.session.non_members.add(5)
    await h.say(5, "/start")
    text = h.session.last_text()
    assert "عضویت در کانال لازم است" in text and "کانال ما" in text
    rows = h.session.last_markup_rows()
    assert any(b.get("url") == "https://ble.ir/mychannel" for row in rows for b in row)
    assert [b["text"] for row in rows for b in row][-1] == "✅ عضو شدم"
    assert not await services.players.find(5)

    await h.click(5, "mem:check")  # still not joined
    assert any("هنوز عضو نشده" in a.get("text", "") for a in h.session.callback_answers())

    h.session.non_members.discard(5)  # the user joins the channel
    await h.click(5, "mem:check")
    assert "عضویت تأیید شد" in h.session.sent("editMessageText")[-1]["text"]
    await h.say(5, "/start")
    assert "عضویت در کانال لازم است" not in h.session.last_text()


async def test_only_the_private_chat_is_gated_groups_are_left_alone(h, services):
    await hero(services, 7, "آرش")
    await services.membership.save(True, [{"chat": "@mychannel"}])
    h.session.non_members.add(7)
    await h.click(7, "p:home:::7")  # a button in the private chat
    assert any("اول باید در کانال عضو شوید" in a.get("text", "") for a in h.session.callback_answers())
    n = len(h.session.sent("sendMessage"))
    await h.say(7, "ماهیگیری", group=True)  # game words in a group: never checked, never nagged
    assert "عضویت در کانال لازم است" not in h.session.last_text()
    assert len(h.session.sent("sendMessage")) >= n
    await h.click(7, "p:home:::7", group=True)  # nor the buttons in a group
    assert not any("اول باید در کانال عضو شوید" in a.get("text", "") for a in h.session.callback_answers()[1:])
    await h.say(7, "/start")  # but the private chat is
    assert "عضویت در کانال لازم است" in h.session.last_text()


async def test_owner_and_members_pass_and_errors_fail_open(h, services):
    await hero(services, 1, "ارباب")
    await hero(services, 8, "سارا")
    await services.membership.save(True, [{"chat": "@mychannel"}])
    h.session.non_members.add(1)  # even "not a member", the owner is never blocked
    await h.say(1, "/start")
    assert "عضویت در کانال لازم است" not in h.session.last_text()
    await h.say(8, "/start")  # a real member
    assert "عضویت در کانال لازم است" not in h.session.last_text()

    class Broken:
        async def get_chat_member(self, *a):
            raise RuntimeError("bale is down")

    assert await services.membership.missing(Broken(), 99) == []  # fail open: never lock players out


async def test_when_bale_refuses_the_check_nobody_passes_and_the_owner_is_told(h, services):
    await services.membership.save(True, [{"chat": "@mychannel", "title": "کانال ما"}])
    h.session.check_error = "Forbidden: bot is not a member of the channel chat"
    await h.say(5, "/start")  # the bot cannot verify anything: the gate must not silently open
    assert "عضویت در کانال لازم است" in h.session.last_text()
    assert "@mychannel" in services.membership.problems
    warnings = [p for p in h.session.sent("sendMessage") if p["chat_id"] == 1 and "عضویت اجباری کار نمی‌کند" in p["text"]]
    assert len(warnings) == 1
    await h.say(6, "/start")
    assert len([p for p in h.session.sent("sendMessage") if p["chat_id"] == 1 and "کار نمی‌کند" in p["text"]]) == 1  # once an hour
    h.session.check_error = None  # the manager made the bot an admin
    services.membership.forget(5)
    h.session.non_members.discard(5)
    await h.say(5, "/start")
    assert "عضویت در کانال لازم است" not in h.session.last_text()
    assert not services.membership.problems


async def test_the_panel_refuses_to_switch_the_gate_on_while_the_bot_is_not_an_admin(h, services):
    await hero(services, 1, "ارباب")
    await services.membership.save(False, [{"chat": "@mychannel"}])
    h.session.bot_is_admin = False
    await h.panel(1, "admm")
    assert "ربات ادمین نیست" in h.session.last_text()
    await h.tap(1, "روشن کردن")
    assert not (await services.membership.settings())[0]
    assert any("ادمین کنید" in a.get("text", "") for a in h.session.callback_answers()) or "ادمین" in h.session.last_text()
    h.session.bot_is_admin = True
    await h.panel(1, "admm")
    await h.tap(1, "روشن کردن")
    assert (await services.membership.settings())[0]
