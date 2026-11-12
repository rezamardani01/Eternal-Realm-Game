import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext

from .harness import Harness

OWNER = 1


@pytest.fixture
def services(db, clock, rng):
    settings = Settings(token="t", owner_id=OWNER, admin_ids=frozenset({2}))
    return Services.build(AppContext(db, settings, clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def test_strangers_get_no_response_at_all(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    for text in ["/admin", "/stats", "/givegold آرش 100", "/ban آرش", "/broadcast hi", "/backup"]:
        await h.say(10, text)
    assert h.session.calls == []
    assert (await services.players.require(10)).gold == services.ctx.balance.start_gold


async def test_admin_commands_are_private_only(h, services):
    await h.say(OWNER, "/stats", group=True)
    assert h.session.calls == []


async def test_owner_and_listed_admins_can_use_the_panel(h):
    await h.say(OWNER, "/admin")
    assert "پنل مدیریت" in h.session.last_text()
    await h.say(2, "/stats")
    assert "آمار" in h.session.last_text()


async def test_give_currency_and_item_are_logged(h, services, db):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(OWNER, "/givegold آرش 250")
    await h.say(OWNER, "/givecrystal آرش 7")
    await h.say(OWNER, "/giveitem آرش | سنگ آهن | 2")
    p = await services.players.require(10)
    assert p.gold == services.ctx.balance.start_gold + 250 and p.crystal == 7
    assert (await services.inventory.view(p.id)).stack_qty("iron_ore") == 2
    async with db.read() as tx:
        actions = [r["action"] for r in await tx.fetchall("SELECT action FROM admin_log ORDER BY id")]
    assert actions == ["give_currency", "give_currency", "give_item"]


async def test_bad_input_gives_helpful_errors(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(OWNER, "/givegold کسی که نیست 5")
    assert "پیدا نشد" in h.session.last_text()
    await h.say(OWNER, "/givegold آرش")
    assert "فرمت" in h.session.last_text()
    await h.say(OWNER, "/giveitem آرش | چیزی که نیست | 1")
    assert "پیدا نشد" in h.session.last_text()
    await h.say(OWNER, "/setlevel آرش 5000")
    assert "سطح باید" in h.session.last_text()


async def test_ban_blocks_and_unban_restores(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(OWNER, "/ban آرش")
    await h.say(10, "پروفایل", group=True)
    assert "بسته‌اند" in h.session.last_text()
    await h.say(OWNER, "/unban آرش")
    await h.say(10, "پروفایل", group=True)
    assert "سطح" in h.session.last_text()


async def test_setlevel_and_stats_and_broadcast(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(10, "راهنما", group=True)  # makes the group known
    await h.say(OWNER, "/setlevel آرش 12")
    assert (await services.players.require(10)).level == 12
    await h.say(OWNER, "/stats")
    assert "بازیکنان" in h.session.last_text()
    h.session.reset()
    await h.say(OWNER, "/broadcast سلام به همه")
    sent = h.session.sent("sendMessage")
    assert any(m["chat_id"] == -500 and "سلام به همه" in m["text"] for m in sent)


async def test_backup_command_creates_a_file(h, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    await h.say(OWNER, "/backup")
    assert "نسخه پشتیبان" in h.session.last_text()
    assert list((tmp_path / "backups").glob("game-*.db"))
