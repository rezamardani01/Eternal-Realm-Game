"""House rules for every line the bot shows: at most one emoji at the start, bold headlines."""

import re

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.shared.text import EMOJI

from .harness import Harness

TWO_AT_START = re.compile(rf"^(?:{EMOJI})\s*(?:{EMOJI})")


def bad_lines(text: str) -> list[str]:
    found = []
    for line in text.split("\n"):
        stripped = line.lstrip(" *•·-—_")
        if TWO_AT_START.match(stripped):
            found.append(line)
    return found


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


async def test_no_line_or_button_starts_with_two_emojis(services, db):
    h = Harness(services)
    h.session.chat_admins.add(99)
    me = await services.players.register(10, "u10", "آرش", "dragonborn", "warrior")
    other = await services.players.register(11, "u11", "سارا", "fairy", "mage")
    async with db.transaction() as tx:
        await wallet.apply(tx, me.id, gold=50_000, crystal=500, reason="t", now=services.ctx.now())
        await tx.execute("UPDATE players SET level = 6 WHERE id = ?", (me.id,))
        await services.inventory.grant(tx, me.id, "wooden_chest", 2)
        await services.inventory.grant(tx, me.id, "iron_ore", 20)
        await services.inventory.grant(tx, me.id, "leather_cap", 1)
        await services.inventory.grant(tx, me.id, "iron_sword", 1)
    me = await services.players.require(10)
    cap = next(g.id for g in (await services.inventory.view(me.id)).gear if g.item.id == "leather_cap")
    await services.market.list_gear(me, cap, 700)
    await services.market.list_stack(me, __import__("eternal_realm.game.data.items", fromlist=["x"]).get_item("iron_ore"), 5, 100)

    steps = [("say", "/start"), ("say", "قلمرو"), ("say", "راهنما"), ("say", "پروفایل"), ("say", "جایزه"),
             ("say", "ماهیگیری"), ("say", "معدن"), ("say", "گیاه"), ("say", "جستجو"), ("say", "شکار"),
             ("say", "استراحت"), ("say", "رتبه"), ("say", "ثروتمندان"), ("say", "تنظیمات گروه"),
             ("say", "کیف من"), ("say", "فروشگاه ویژه"), ("say", "باس")]
    screens = ["home", "profile", "inv", "gear", "items", "chests", "chestshop", "shop", "shopcat:gear",
               "shopcat:pot", "market", "mine", "top:level", "premium", "prem:coins", "prem:crystals",
               "prem:bundles", "prem:chests", "prem:materials", "luckyodds", "helpsec:boss", "helpsec:all", "boss", "adv", "help", "daily", "rest", "open:wooden_chest", "odds:magic_chest"]
    problems: list[tuple[str, str]] = []

    def scan(label: str) -> None:
        for kind, payload in h.session.calls:
            if kind not in ("sendMessage", "editMessageText"):
                continue
            for line in bad_lines(payload.get("text", "")):
                problems.append((label, line))
            rows = payload.get("reply_markup", {}).get("inline_keyboard", [])
            for row in rows:
                for button in row:
                    for line in bad_lines(button["text"]):
                        problems.append((label + " [button]", line))

    for _, text in steps:
        h.session.reset()
        await services.throttle_reset() if hasattr(services, "throttle_reset") else None
        await h.say(10, text, group=True)
        scan(text)
    for entry in screens:
        name, _, arg = entry.partition(":")
        h.session.reset()
        await h.panel(10, name, arg)
        scan(entry)
    await h.say(10, "مبارزه", group=True, reply_to=h.message_of(11))
    scan("duel invite")
    await h.click(11, h.button_data("قبول"), group=True)
    scan("duel started")
    assert other
    assert not problems, problems[:15]


def test_every_message_gets_a_bold_headline():
    from eternal_realm.shared.text import headline

    assert headline("⚡ انرژی شما کافی نیست") == "⚡ **انرژی شما کافی نیست**"
    assert headline("سلام\nخط دوم") == "**سلام**\nخط دوم"
    assert headline("🎉 **از قبل بولد**\nمتن") == "🎉 **از قبل بولد**\nمتن"
