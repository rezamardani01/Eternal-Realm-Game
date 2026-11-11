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
    assert any("باس" in t for t in h.labels())  # the help is a glass panel of topics
    await h.tap(10, "همه‌ی دستورها", group=True)
    assert "پروفایل" in h.session.last_text()
    assert await services.groups.get(-500) is not None


async def test_profile_with_a_reply_does_nothing(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await services.players.register(11, "b", "سارا", "fairy", "mage")
    await h.say(10, "پروفایل", group=True, reply_to=h.message_of(11))
    assert not h.session.texts()


async def test_unregistered_user_is_sent_to_start(h):
    await h.say(10, "پروفایل", group=True)
    assert "قهرمانی نساخته" in h.session.last_text()
    assert h.session.last_buttons()[0]["url"].startswith("https://ble.ir/")


async def test_banned_player_blocked(h, services):
    p = await services.players.register(10, "a", "آرش", "elf", "archer")
    async with services.ctx.db.transaction() as tx:
        await tx.execute("UPDATE players SET banned = 1 WHERE id = ?", (p.id,))
    await h.say(10, "پروفایل", group=True)
    assert "بسته‌اند" in h.session.last_text()


async def test_daily_via_command(h, services):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    await h.say(10, "جایزه")
    assert "گنجینه‌ی روزانه" in h.session.last_text()
    await h.say(10, "جایزه")
    assert "برداشته‌اید" in h.session.last_text()


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


async def test_streak_pays_a_chest_every_week(services, clock):
    await services.players.register(10, "a", "آرش", "elf", "archer")
    p = await services.players.require(10)
    for day in range(1, 8):
        reward = await services.players.claim_daily(p.id)
        assert reward.streak == day
        clock.advance(86_400 + 60)
    assert reward.chest == "wooden_chest" and reward.next_chest_in == 7
    async with services.ctx.db.read() as tx:
        assert await tx.scalar("SELECT qty FROM inventory WHERE player_id = ? AND item_id = 'wooden_chest'", (p.id,), 0) == 1
    clock.advance(3 * 86_400)  # missing days breaks the streak
    assert (await services.players.claim_daily(p.id)).streak == 1


def test_people_write_commands_with_marks_and_polite_words_and_they_still_work():
    from eternal_realm.bot.commands import REGISTRY

    for text in ("پروفایل", "پروفایل!", "پروفایل؟", "پروفایل 😎", "پروفایل...", "پروفایل من", "پروفایل من رو نشون بده", "ربات پروفایل"):
        assert REGISTRY.resolve(text).command.name == "profile", text
    assert REGISTRY.resolve("شکار ✅").command.name == "hunt"
    assert REGISTRY.resolve("انتقال 500!").args == ["500"]
    assert REGISTRY.resolve("غیرفعال پروفایل").command.name == "group_off"
    for text in ("من", "ربات", "پروفایل رضا", "شکار گرگ", "سلام"):
        assert REGISTRY.resolve(text) is None, text  # ordinary chatter is never taken for a command


async def test_a_stranger_is_told_once_in_a_group_not_on_every_word(h, services):
    import importlib

    commands_router = importlib.import_module("eternal_realm.bot.commands.router")
    commands_router._told.clear()
    await h.say(10, "پروفایل", group=True)
    assert "قهرمانی نساخته" in h.session.last_text() and h.session.last_buttons()[0]["url"].startswith("https://ble.ir/")
    before = len(h.session.texts())
    await h.say(10, "شکار", group=True)
    await h.say(10, "ماهیگیری", group=True)
    assert len(h.session.texts()) == before  # quiet: the group is not a notice board
    await h.say(10, "پروفایل")  # in the private chat the answer always comes
    assert len(h.session.texts()) == before + 1
