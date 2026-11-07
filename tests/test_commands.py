import pytest

from eternal_realm.bot.commands.registry import CommandRegistry
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext

from .harness import Harness


async def noop(ctx):  # pragma: no cover
    return None


def make_registry():
    r = CommandRegistry()
    r.command("fish", ["ماهیگیری", "ماهی", "برو ماهی بگیر", "fish"], "x")(noop)
    r.command("duel", ["مبارزه", "duel"], "x", takes_args=True)(noop)
    return r


@pytest.mark.parametrize(
    "text,name,args",
    [
        ("ماهی", "fish", []),
        ("  ماهيگيري ", "fish", []),  # arabic yeh/kaf are normalised
        ("ماهیگیری", "fish", []),
        ("برو ماهی بگیر", "fish", []),
        ("/fish", "fish", []),
        ("/fish@er_bot", "fish", []),
        ("fish", None, None),
        ("مبارزه 50", "duel", ["50"]),
        ("ماهی\u200cگیری", None, None),
        ("سلام ماهی", None, None),
    ],
)
def test_resolution(text, name, args):
    match = make_registry().resolve(text)
    if name is None:
        assert match is None
    else:
        assert match.command.name == name and match.args == args


def test_alias_overrides_and_conflicts():
    r = make_registry()
    r.configure({"fish": ("صید",)})
    assert r.resolve("ماهی") is None and r.resolve("صید").command.name == "fish"
    r2 = CommandRegistry()
    r2.command("a", ["x1"], "d")(noop)
    with pytest.raises(ValueError):
        r2.command("b", ["x1"], "d")(noop)


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def test_profile_and_help_in_group(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(10, "پروفایل", group=True)
    assert "آرش" in h.session.last_text()
    await h.say(10, "راهنما", group=True)
    assert "پروفایل" in h.session.last_text()
    assert await services.groups.get(-500) is not None


async def test_profile_of_replied_player(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await services.players.register(11, "b", "سارا", "fairy", "mage")
    await h.say(10, "پروفایل", group=True, reply_to=h.message_of(11))
    assert "سارا" in h.session.last_text()


async def test_unregistered_user_is_sent_to_start(h):
    await h.say(10, "پروفایل", group=True)
    assert "استارت" in h.session.last_text()
    assert h.session.last_buttons()[0]["url"].startswith("https://ble.ir/")


async def test_unregistered_reply_target(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(10, "پروفایل", group=True, reply_to=h.message_of(99))
    assert "شخصیت نساخته" in h.session.last_text()


async def test_banned_player_blocked(h, services):
    p = await services.players.register(10, "a", "آرش", "elf", "archer")
    async with services.ctx.db.transaction() as tx:
        await tx.execute("UPDATE players SET banned = 1 WHERE id = ?", (p.id,))
    await h.say(10, "پروفایل", group=True)
    assert "مسدود" in h.session.last_text()


async def test_daily_via_command(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(10, "جایزه", group=True)
    assert "جایزه روزانه" in h.session.last_text()
    await h.say(10, "جایزه", group=True)
    assert "گرفته‌ای" in h.session.last_text()


async def test_plain_chatter_is_ignored(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(10, "سلام بچه‌ها چطورید", group=True)
    assert h.session.calls == []


async def test_spam_is_throttled(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    services.throttle.user_gap = 100
    await h.say(10, "پروفایل", group=True)
    await h.say(10, "پروفایل", group=True)
    assert len(h.session.sent()) == 1


def test_chatter_starting_with_a_keyword_does_not_trigger():
    r = make_registry()
    assert r.resolve("ماهی خیلی خوبه") is None
    assert r.resolve("مبارزه با اژدها").command.name == "duel"  # commands that take args still do
