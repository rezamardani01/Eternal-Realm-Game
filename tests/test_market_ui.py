import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.items import get_item

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def reg(services, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "archer")


async def stock(services, db, pid, **items):
    async with db.transaction() as tx:
        for item_id, qty in items.items():
            await services.inventory.grant(tx, pid, item_id, qty)


def listing_labels(h):
    return [t for t in h.labels() if "🪙" in t and "—" in t]


async def seed_market(services, db):
    seller = await reg(services, 10, "آرش")
    await stock(services, db, seller.id, leather_cap=1, steel_sword=1, dagger=1, iron_ore=10)
    seller = await services.players.require(10)
    pieces = {g.item.id: g.id for g in (await services.inventory.view(seller.id)).gear}
    await services.market.list_gear(seller, pieces["leather_cap"], 900)
    await services.market.list_gear(seller, pieces["steel_sword"], 5_000)
    await services.market.list_gear(seller, pieces["dagger"], 300)
    await services.market.list_stack(seller, get_item("iron_ore"), 10, 700)
    return seller


async def test_sorting_cheapest_most_expensive_and_rarest(h, services, db):
    await seed_market(services, db)
    await reg(services, 11, "سارا")

    await h.panel(11, "market")
    assert len(listing_labels(h)) == 4

    await h.tap(11, "فیلتر")
    await h.tap(11, "ارزان‌ترین")
    assert any("✅ ارزان‌ترین" in t for t in h.labels())  # the tick moved
    await h.tap(11, "نمایش آگهی‌ها")
    prices = [t.split("—")[-1] for t in listing_labels(h)]
    assert "خنجر" in listing_labels(h)[0] and "۳۰۰" in prices[0]

    await h.tap(11, "فیلتر")
    await h.tap(11, "گران‌ترین")
    await h.tap(11, "نمایش آگهی‌ها")
    assert "شمشیر فولادی" in listing_labels(h)[0]

    await h.tap(11, "فیلتر")
    await h.tap(11, "کمیاب‌ترین")
    await h.tap(11, "نمایش آگهی‌ها")
    assert "شمشیر فولادی" in listing_labels(h)[0]  # rarity 3 beats the common items


async def test_category_and_sort_work_together_and_survive_paging(h, services, db):
    await seed_market(services, db)
    await reg(services, 11, "سارا")
    await h.panel(11, "market")
    assert len(h.labels()) < 14  # only two filter buttons, not a wall of keys
    await h.tap(11, "دسته")
    await h.tap(11, "سلاح و زره")
    await h.tap(11, "نمایش آگهی‌ها")
    await h.tap(11, "فیلتر")
    await h.tap(11, "ارزان‌ترین")
    await h.tap(11, "نمایش آگهی‌ها")
    labels = listing_labels(h)
    assert len(labels) == 3 and "سنگ آهن" not in " ".join(labels)
    assert any("دسته: سلاح و زره" in t for t in h.labels())
    assert any("فیلتر: ارزان‌ترین" in t for t in h.labels())


async def test_everyone_sees_the_same_market_from_any_group(h, services, db):
    await seed_market(services, db)
    await reg(services, 11, "سارا")
    await reg(services, 12, "رها")
    await h.say(11, "بازار", group=True, chat=-111)
    first = listing_labels(h)
    await h.say(12, "بازار", group=True, chat=-222)
    assert listing_labels(h) == first and len(first) == 4


async def test_sell_flow_pick_item_then_choose_quantity_then_type_the_price(h, services, db):
    seller = await reg(services, 10, "آرش")
    await stock(services, db, seller.id, iron_ore=12)
    await reg(services, 11, "سارا")
    await h.panel(10, "market")
    await h.tap(10, "فروش کالای من")
    assert any("سنگ آهن" in t for t in h.labels())
    await h.tap(10, "سنگ آهن")
    assert any("×۵" in t for t in h.labels()) and any("همه" in t for t in h.labels())
    await h.tap(10, "×۵")
    assert "قیمت فروش" in h.session.last_text()
    await h.say(10, "450")
    await h.tap(10, "ثبت آگهی")
    assert "آگهی شما نصب شد" in h.session.last_text()

    listing = (await services.market.mine(await services.players.require(10)))[0]
    assert listing.qty == 5 and listing.price == 450
    stacks = {i.id: q for i, q in (await services.inventory.view(seller.id)).stacks}
    assert stacks["iron_ore"] == 7  # the rest stays in the backpack

    await h.panel(11, "market")
    assert any("سنگ آهن" in t for t in h.labels())


async def test_selling_in_a_group_works_and_chatter_still_reaches_commands(h, services, db):
    seller = await reg(services, 10, "آرش")
    await stock(services, db, seller.id, leather_cap=1)
    await h.say(10, "بازار", group=True)
    await h.tap(10, "فروش کالای من", group=True)
    await h.tap(10, "کلاه چرمی", group=True)
    assert "قیمت فروش" in h.session.last_text()
    await h.say(10, "پروفایل", group=True)  # a game word while the prompt is open still works
    assert "آرش" in h.session.last_text()
    await h.say(10, "نمی‌دانم", group=True)  # chatter is ignored, the prompt stays
    await h.say(10, "800", group=True)
    await h.tap(10, "ثبت آگهی", group=True)
    assert "آگهی شما نصب شد" in h.session.last_text()
    assert (await services.market.mine(seller))[0].price == 800


async def test_buying_listed_gear_then_selling_it_to_the_npc_does_not_crash(h, services, db):
    seller = await reg(services, 10, "آرش")
    buyer = await reg(services, 11, "سارا")
    await stock(services, db, seller.id, leather_cap=1)
    seller = await services.players.require(10)
    cap = (await services.inventory.view(seller.id)).gear[-1].id
    listing = await services.market.list_gear(seller, cap, 100)
    await services.market.buy(await services.players.require(11), listing.id)
    sold, total = await services.shop.sell_gear(await services.players.require(11), cap)
    assert sold.item.id == "leather_cap" and total > 0
    assert buyer


async def test_empty_market_shows_one_wide_notice_button_between_the_rows(h, services, db):
    await reg(services, 11, "سارا")
    await h.panel(11, "market")
    labels = h.labels()
    notice = next(i for i, t in enumerate(labels) if "هیچ آیتمی برای خرید وجود ندارد" in t)
    assert "دسته" in labels[notice - 2] and "فیلتر" in labels[notice - 1]
    assert "فروش کالای من" in labels[notice + 1]


async def test_home_menu_uses_the_new_names(h, services, db):
    await reg(services, 11, "سارا")
    await h.say(11, "قلمرو", group=True)
    labels = " ".join(h.labels())
    for name in ("قهرمان من", "فروشگاه آیتم", "بازارچه", "تالار بزرگان", "کلکسیون کارت", "حیوان خانگی",
                 "کوره آهنگری", "خزانه قلمرو", "راهنمایی"):
        assert name in labels
    assert "🐱 حیوان خانگی" in h.labels()
