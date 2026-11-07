"""The glass-button experience: everything is reached by tapping, panels edit themselves."""

import re

import pytest

from eternal_realm.bot import views
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet

from .harness import Harness

# an emoji-ish symbol (outside Persian/Latin letters, digits and common punctuation)
SYMBOL = re.compile(r"[←-⯿☀-➿\U0001F000-\U0001FAFF]")


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def reg(services, uid=10, name="آرش", race="elf", cls="archer"):
    return await services.players.register(uid, f"u{uid}", name, race, cls)


async def give(services, db, pid, item_id, qty=1, gold=0, crystal=0):
    async with db.transaction() as tx:
        ids = await services.inventory.grant(tx, pid, item_id, qty) if item_id else []
        await wallet.apply(tx, pid, gold=gold, crystal=crystal, reason="t", now=services.ctx.now())
    return ids


def leading_symbols(text: str) -> int:
    """How many symbols sit before the first letter of the message."""
    count = 0
    for char in text:
        if char.isalpha():
            break
        if SYMBOL.match(char):
            count += 1
    return count


# --- the rules of the house ---------------------------------------------------------------------
async def test_every_screen_starts_with_exactly_one_emoji(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, "wooden_chest", 1, gold=5_000, crystal=50)
    gear_id = (await services.inventory.view(p.id)).gear[0].id
    screens = [("home", ""), ("profile", ""), ("inv", ""), ("gear", ""), ("piece", str(gear_id)), ("items", ""),
               ("chests", ""), ("chestshop", ""), ("shop", ""), ("shopcat", "gear"), ("shopcat", "pot"),
               ("market", ""), ("mine", ""), ("top", "level"), ("premium", ""), ("adv", ""), ("help", ""),
               ("upq", str(gear_id)), ("sellq", str(gear_id))]
    problems = []
    for name, arg in screens:
        h.session.reset()
        try:
            await h.panel(10, name, arg)
        except Exception as exc:  # a screen that cannot render is a bug as well
            problems.append((name, repr(exc)))
            continue
        if not h.session.texts():
            problems.append((name, 'rendered nothing'))
        for text in h.session.texts():
            if leading_symbols(text) != 1:
                problems.append((name, text.split("\n")[0]))
            assert len(text) < 4000, name
    assert not problems, problems


def test_static_texts_follow_the_rules():
    from eternal_realm.bot.commands import REGISTRY
    from eternal_realm.game.data.races import RACES

    for text in (views.welcome(), views.pick_race(), views.pick_class(RACES["elf"]), views.help_text(),
                 views.command_help(REGISTRY, True), views.premium_shop(True)):
        assert leading_symbols(text) == 1, text.split("\n")[0]
        assert len(text) < 4000
    assert "**" in views.welcome()  # titles are bold


def test_race_and_class_lists_are_short():
    from eternal_realm.game.data.races import RACES

    assert len(views.pick_race()) < 420
    assert len(views.pick_class(RACES["elf"])) < 380


async def test_stats_are_one_per_line_in_text_and_buttons_in_the_panel(h, services):
    p = await reg(services)
    stats = await services.characters.stats(p)
    chars = services.characters
    lines = views.profile_lines(p, stats, chars.xp_needed(p), chars.max_energy(p)).split("\n")
    for label in ("جادو", "سرعت", "شانس"):
        assert sum(label in line for line in lines) == 1  # never two stats on one line

    await h.panel(10, "profile")
    rows = h.session.last_markup_rows()
    flat = [b["text"] for row in rows for b in row]
    assert any("حمله" in t for t in flat) and any("دفاع" in t for t in flat) and any("انرژی" in t for t in flat)
    assert all(len(row) <= 2 for row in rows)
    await h.tap(10, "حمله")  # tapping a stat explains it in an alert
    assert any("قدرت ضربه" in a.get("text", "") for a in h.session.callback_answers())


# --- ownership -----------------------------------------------------------------------------------
async def test_a_panel_only_answers_to_its_owner(h, services):
    await reg(services)
    await reg(services, 11, "سارا", "fairy", "mage")
    await h.say(10, "کوله‌پشتی", group=True)
    data = h.button_data("تجهیزات")
    await h.click(11, data, group=True)
    assert any("مال شما نیست" in a.get("text", "") for a in h.session.callback_answers())
    assert not h.session.sent("editMessageText")


# --- start and menus ----------------------------------------------------------------------------
async def test_start_shows_the_home_panel_with_glass_buttons(h, services):
    await reg(services)
    await h.say(10, "/start")
    labels = h.labels()
    assert any("کوله‌پشتی" in t for t in labels) and any("فروشگاه" in t for t in labels)
    assert any("ماجراجویی" in t for t in labels)


async def test_group_words_open_panels_and_personal_panel_goes_private(h, services):
    await reg(services)
    for word, expect in [("کوله‌پشتی", "تجهیزات"), ("فروشگاه", "سلاح"), ("بازار", "منو"), ("صندوقچه", "خرید صندوقچه")]:
        await h.say(10, word, group=True)
        assert any(expect in t for t in h.labels()), (word, h.labels())
    await h.say(10, "کیف من", group=True)
    assert h.session.last_buttons()[0]["url"].startswith("https://ble.ir/")
    await h.say(10, "کیف من")
    assert any("شخصیت من" in t for t in h.labels())


# --- equipment ----------------------------------------------------------------------------------
async def test_equip_and_unequip_by_tapping(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, "dagger")
    await h.say(10, "/start")
    await h.tap(10, "کوله‌پشتی")
    await h.tap(10, "تجهیزات")
    assert any("✅" in t for t in h.labels())  # the starter weapon is marked as worn
    await h.tap(10, "خنجر")
    assert any("پوشیدن" in t for t in h.labels())
    await h.tap(10, "پوشیدن")
    assert any("درآوردن" in t for t in h.labels())
    assert any(
        g.item.id == "dagger" and g.slot for g in (await services.inventory.view(p.id)).gear
    )
    await h.tap(10, "درآوردن")
    assert any("پوشیدن" in t for t in h.labels())


async def test_gear_that_is_too_heavy_explains_itself(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, "iron_sword")
    await h.panel(10, "gear")
    await h.tap(10, "شمشیر آهنی")
    await h.tap(10, "پوشیدن")
    assert any("سطح" in a.get("text", "") for a in h.session.callback_answers())


# --- consumables and chests ---------------------------------------------------------------------
async def test_use_a_potion_from_the_item_screen(h, services, db):
    p = await reg(services)
    async with db.transaction() as tx:
        await services.players.spend_energy(tx, p.id, 70)
    await h.panel(10, "items")
    await h.tap(10, "معجون انرژی")
    await h.tap(10, "مصرف")
    assert (await services.players.require(10)).energy == 70


async def test_a_bought_chest_comes_with_an_open_button_right_below(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, None, gold=0, crystal=100)
    await h.panel(10, "chestshop")
    await h.tap(10, "جادویی")  # buy the magic chest
    assert "خریده شد" in h.session.last_text()
    assert any("باز کردن" in t for t in h.labels())
    await h.tap(10, "باز کردن")
    assert "باز شد" in h.session.last_text()
    stacks = {i.id: q for i, q in (await services.inventory.view(p.id)).stacks}
    assert "magic_chest" not in stacks


async def test_chest_odds_by_button(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, "wooden_chest")
    await h.panel(10, "chests")
    await h.tap(10, "صندوقچه چوبی")
    await h.tap(10, "شانس")
    assert "٪" in h.session.last_text()


# --- shop ----------------------------------------------------------------------------------------
async def test_buy_from_the_shop_by_tapping(h, services, db):
    p = await reg(services)
    await h.panel(10, "shop")
    await h.tap(10, "معجون‌ها")
    await h.tap(10, "معجون انرژی بزرگ")
    before = (await services.players.require(10)).gold
    assert "بها" in h.session.last_text()
    await give(services, db, p.id, None, gold=1_000)
    await h.tap(10, "×۱")
    after = await services.players.require(10)
    assert after.gold == before + 1_000 - 400
    stacks = {i.id: q for i, q in (await services.inventory.view(p.id)).stacks}
    assert stacks["big_energy_potion"] == 1


async def test_upgrade_by_tapping(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, "iron_ore", 5, gold=5_000)
    await h.panel(10, "gear")
    await h.tap(10, "کمان کوتاه")
    await h.tap(10, "ارتقا")
    assert "شانس موفقیت" in h.session.last_text()
    await h.tap(10, "ارتقا به")
    assert (await services.inventory.view(p.id)).gear[0].upgrade == 1


# --- market --------------------------------------------------------------------------------------
async def test_listing_and_buying_through_the_panel(h, services, db):
    seller = await reg(services)
    await reg(services, 11, "سارا", "fairy", "mage")
    await give(services, db, 2, None, gold=5_000)
    spare = (await give(services, db, seller.id, "leather_cap"))[0]

    await h.panel(10, "piece", str(spare))
    await h.tap(10, "عرضه در بازار")
    assert "بهای فروش" in h.session.last_text()
    await h.say(10, "1200")  # the answer to the price prompt
    assert "آگهی شما نصب شد" in h.session.last_text()

    await h.panel(11, "market")
    await h.tap(11, "کلاه چرمی")
    await h.tap(11, "خرید با")
    assert any(g.item.id == "leather_cap" for g in (await services.inventory.view(2)).gear)
    assert (await services.players.require(11)).gold == services.ctx.balance.start_gold + 5_000 - 1_200


async def test_cancelling_a_listing_returns_the_item(h, services, db):
    seller = await reg(services)
    spare = (await give(services, db, seller.id, "leather_cap"))[0]
    await h.panel(10, "piece", str(spare))
    await h.tap(10, "عرضه در بازار")
    await h.say(10, "500")
    await h.panel(10, "mine")
    await h.tap(10, "کلاه چرمی")
    await h.tap(10, "لغو آگهی")
    assert any(g.id == spare for g in (await services.inventory.view(seller.id)).gear)


async def test_bad_price_keeps_asking_and_a_tap_cancels(h, services, db):
    seller = await reg(services)
    spare = (await give(services, db, seller.id, "leather_cap"))[0]
    await h.panel(10, "piece", str(spare))
    await h.tap(10, "عرضه در بازار")
    await h.say(10, "خیلی")
    assert "عدد" in h.session.last_text()
    await h.tap(10, "انصراف")
    await h.say(10, "500")  # no longer in the prompt: ignored as chatter
    assert not await services.market.mine(seller)


# --- adventure and rankings ----------------------------------------------------------------------
async def test_adventure_buttons(h, services):
    await reg(services)
    await h.panel(10, "adv")
    await h.tap(10, "ماهیگیری")
    assert "انرژی" in h.session.last_text()
    assert any("دوباره" in t for t in h.labels())


async def test_rankings_tabs(h, services):
    await reg(services)
    await h.say(10, "رتبه", group=True)
    assert any("این گروه" in t for t in h.labels())
    await h.tap(10, "ثروت", group=True)
    assert "🥇" in h.session.last_text()
