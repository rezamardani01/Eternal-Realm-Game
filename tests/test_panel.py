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
                 views.command_help(REGISTRY, True)):
        assert leading_symbols(text) == 1, text.split("\n")[0]
        assert len(text) < 4000
    assert "*" in views.welcome() and "**" not in views.welcome()  # titles are bold


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
    for word, expect in [("کوله‌پشتی", "تجهیزات"), ("فروشگاه", "سلاح"), ("بازار", "بازگشت"), ("صندوقچه", "خرید صندوقچه")]:
        await h.say(10, word, group=True)
        assert any(expect in t for t in h.labels()), (word, h.labels())
    await h.say(10, "کیف من", group=True)
    assert h.session.last_buttons()[0]["url"].startswith("https://ble.ir/")
    await h.say(10, "کیف من")
    assert any("قهرمان من" in t for t in h.labels())


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
    await h.tap(10, "جادویی")  # asks first
    assert "تأیید خرید" in h.session.last_text()
    await h.tap(10, "بله")
    assert "خریده شد" in h.session.last_text()
    assert any("باز کردن" in t for t in h.labels())
    await h.tap(10, "باز کردن")
    assert "باز شد" in h.session.last_text()
    stacks = {i.id: q for i, q in (await services.inventory.view(p.id)).stacks}
    assert "magic_chest" not in stacks


async def test_chest_odds_live_under_the_chest_itself(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, "wooden_chest")
    await h.panel(10, "chests")
    await h.tap(10, "صندوقچه چوبی")
    assert "٪" in h.session.last_text() and "محتویات" in h.session.last_text()
    assert not any("شانس" in t for t in h.labels())  # no separate odds button any more


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
    assert "مطمئنید" in h.session.last_text()
    assert (await services.players.require(10)).gold == before + 1_000  # nothing was spent yet
    await h.tap(10, "بله")
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
    assert "قیمت فروش" in h.session.last_text()
    await h.say(10, "1200")  # the answer to the price prompt
    await h.tap(10, "ثبت آگهی")
    assert "آگهی شما نصب شد" in h.session.last_text()

    await h.panel(11, "market")
    await h.tap(11, "کلاه چرمی")
    await h.tap(11, "خرید با")
    assert "تأیید خرید" in h.session.last_text()
    await h.tap(11, "بله، بخر")
    assert any(g.item.id == "leather_cap" for g in (await services.inventory.view(2)).gear)
    assert (await services.players.require(11)).gold == services.ctx.balance.start_gold + 5_000 - 1_200


async def test_cancelling_a_listing_returns_the_item(h, services, db):
    seller = await reg(services)
    spare = (await give(services, db, seller.id, "leather_cap"))[0]
    await h.panel(10, "piece", str(spare))
    await h.tap(10, "عرضه در بازار")
    await h.say(10, "500")
    await h.tap(10, "ثبت آگهی")
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
    assert any("انرژی شما" in t for t in h.labels())
    assert any("دوباره" in t for t in h.labels())


async def test_rankings_tabs(h, services):
    await reg(services)
    await h.say(10, "رتبه", group=True)
    assert any("این گروه" in t for t in h.labels())
    await h.tap(10, "ثروت", group=True)
    assert "🥇" in h.session.last_text()


# --- help, shortages, market tabs ---------------------------------------------------------------
def test_help_is_airy_and_every_word_in_it_is_a_real_command():
    from eternal_realm.bot.commands import REGISTRY

    text = views.command_help(REGISTRY, True)
    assert "\n\n" in text and len(text) < 4000
    assert text.count("\n\n") > 20  # a blank line between entries
    words = [name.split(" ", 1)[1].split(" 500")[0] for _, rows in views.HELP_SECTIONS for name, _ in rows]
    for word in words:
        assert REGISTRY.resolve(word) is not None, word
    for word in ("غیرفعال ماهیگیری", "فعال ماهیگیری", "تنظیمات گروه"):
        assert REGISTRY.resolve(word) is not None, word


async def test_shortage_messages_state_the_numbers(h, services, db):
    p = await reg(services)
    await h.panel(10, "shopitem", "iron_sword", "gear")
    await h.tap(10, "خرید")  # the confirmation page already shows the numbers
    text = h.session.last_text()
    assert "۵۰۰" in text and "۹۰۰" in text and "۴۰۰" in text  # have, price, missing
    assert not any("بله" in t for t in h.labels())  # nothing to confirm when you cannot pay
    # a stale confirm button still cannot spend money that is not there
    await h.panel(10, "buy", "iron_sword", "1")
    alert = next(a["text"] for a in h.session.callback_answers() if "کافی نیست" in a.get("text", ""))
    assert "۵۰۰" in alert and "۹۰۰" in alert and "۴۰۰" in alert
    await h.panel(10, "cbuyq", "magic_chest")
    assert "💎" in h.session.last_text() and "۳۰" in h.session.last_text()
    assert p


async def test_market_has_category_buttons_with_listings_below(h, services, db):
    seller = await reg(services)
    await reg(services, 11, "سارا", "fairy", "mage")
    cap = (await give(services, db, seller.id, "leather_cap"))[0]
    await give(services, db, seller.id, "iron_ore", 3)
    await services.market.list_gear(await services.players.require(10), cap, 700)
    await services.market.list_stack(await services.players.require(10), __import__("eternal_realm.game.data.items", fromlist=["x"]).get_item("iron_ore"), 3, 90)

    await h.panel(11, "market")
    labels = h.labels()
    assert any("دسته" in t for t in labels) and any("فیلتر" in t for t in labels)
    assert any("کلاه چرمی" in t for t in labels) and any("سنگ آهن" in t for t in labels)
    await h.tap(11, "دسته")
    await h.tap(11, "مواد")
    await h.tap(11, "نمایش آگهی‌ها")
    labels = h.labels()
    assert any("سنگ آهن" in t for t in labels) and not any("کلاه چرمی" in t for t in labels)
    await h.tap(11, "دسته")
    await h.tap(11, "صندوقچه")
    await h.tap(11, "نمایش آگهی‌ها")
    assert "فروشنده باشید" in h.session.last_text()


async def test_market_panel_opened_in_a_group_belongs_to_its_opener(h, services):
    await reg(services)
    await reg(services, 11, "سارا", "fairy", "mage")
    await h.say(10, "بازار", group=True)
    tab = h.button_data("فیلتر")
    h.session.reset()
    await h.click(11, tab, group=True)
    assert not h.session.sent("editMessageText")
    assert any("مال شما نیست" in a.get("text", "") for a in h.session.callback_answers())
    await h.click(10, tab, group=True)
    assert h.session.sent("editMessageText")


# --- animation and confirmation -----------------------------------------------------------------
async def test_hunt_in_a_group_is_played_as_edits_of_one_message(h, services):
    await reg(services, race="dragonborn", cls="warrior")
    await h.say(10, "شکار", group=True)
    sent = [p["text"] for p in h.session.sent("sendMessage")]
    edits = [p["text"] for p in h.session.sent("editMessageText")]
    assert "در حال شکار" in sent[0]
    assert len(edits) >= 3 and "پیدا شد" in edits[0]
    assert "نبرد با" in edits[-1]  # the last edit is the full result


async def test_opening_a_chest_shows_a_waiting_frame_first(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, "wooden_chest")
    await h.panel(10, "open", "wooden_chest")
    edits = [x["text"] for x in h.session.sent("editMessageText")]
    assert "در حال باز کردن" in edits[0] and "صبر" in edits[0]
    assert "باز شد" in edits[-1]


async def test_fishing_shows_progress_then_result(h, services):
    await reg(services)
    await h.say(10, "ماهیگیری", group=True)
    assert h.session.sent("sendMessage") and h.session.sent("editMessageText")
    assert any("انرژی شما" in t for t in h.labels())


async def test_declining_the_purchase_changes_nothing(h, services, db):
    p = await reg(services)
    await give(services, db, p.id, None, crystal=100)
    await h.panel(10, "chestshop")
    await h.tap(10, "جادویی")
    await h.tap(10, "نه")
    assert (await services.players.require(10)).crystal == 100
    assert any("خرید صندوقچه" in t or "جادویی" in t for t in h.labels())


async def test_the_word_realm_opens_the_home_panel_in_a_group(h, services):
    await reg(services)
    await h.say(10, "قلمرو", group=True)
    assert any("ماجراجویی" in t for t in h.labels()) and "فرمانده" in h.session.last_text()


async def test_back_buttons_are_called_back_not_menu(h, services):
    await reg(services)
    for name in ("profile", "inv", "shop", "market", "top", "help", "adv"):
        await h.panel(10, name)
        assert all("منو" not in t for t in h.labels()), name
        assert any("بازگشت" in t for t in h.labels()), name


async def test_help_panel_has_a_page_for_every_topic(h, services):
    from eternal_realm.bot import views

    await reg(services)
    await h.say(10, "راهنما", group=True)
    topics = views.help_pages(services.ctx.balance)
    labels = h.labels()
    assert all(any(label in t for t in labels) for label, _ in topics.values())
    for label, _ in topics.values():
        await h.say(10, "راهنما", group=True)
        await h.tap(10, label.split(" ", 1)[1], group=True)
        assert len(h.session.last_text()) > 60
        assert any("بازگشت" in t for t in h.labels())
    await h.say(10, "راهنما", group=True)
    await h.tap(10, "باس گروهی", group=True)
    assert "باس" in h.session.last_text() and "احضار" in h.session.last_text()


# --- mentions, other players' profiles, airier texts ---------------------------------------------
async def test_names_are_mentions_in_groups_but_plain_in_private(h, services):
    await reg(services)
    await h.say(10, "ماهیگیری", group=True)
    assert "[آرش](uid:10)" in h.session.sent("sendMessage")[0]["text"]
    await h.say(10, "جایزه", group=True)
    assert "[آرش](uid:10)" in h.session.last_text()
    h.session.reset()
    await h.panel(10, "act", "fishing")
    assert "(uid:" not in " ".join(h.session.texts())


async def test_profile_of_another_player_is_a_glass_panel_with_their_numbers(h, services):
    await reg(services)
    other = await reg(services, 11, "سارا", "fairy", "mage")
    stats = await services.characters.stats(other)
    await h.say(10, "پروفایل", group=True, reply_to=h.message_of(11))
    labels = h.labels()
    assert any("حمله" in t and str(stats.atk).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")) in t for t in labels)
    assert "سارا" in h.session.last_text()
    assert not any("کوله‌پشتی" in t for t in labels)  # it is their profile, not your backpack
    await h.say(10, "پروفایل", group=True)
    assert any("کوله‌پشتی" in t for t in h.labels())


async def test_transfer_text_is_split_into_calm_blocks(h, services, db):
    from eternal_realm.db.repos import wallet

    a = await reg(services)
    await reg(services, 11, "سارا", "fairy", "mage")
    async with db.transaction() as tx:
        await wallet.apply(tx, a.id, gold=2_000, reason="t", now=services.ctx.now())
    await h.say(10, "انتقال 500", group=True, reply_to=h.message_of(11))
    text = h.session.last_text()
    assert text.count("\n\n") >= 2 and "[سارا](uid:11)" in text
