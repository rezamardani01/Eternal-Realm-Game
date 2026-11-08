import re

import pytest

from eternal_realm.bot import panel
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game import item_info
from eternal_realm.game.data.items import ITEMS, get_item
from eternal_realm.shared.text import EMOJI

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


def test_every_item_says_what_it_is_for_and_where_it_comes_from():
    for item in ITEMS.values():
        uses, sources = item_info.uses(item.id), item_info.sources(item.id)
        assert uses and sources, item.id
        text = "\n".join(panel._describe(item))
        assert "کاربرد" in text and "از کجا" in text and len(text) < 3000
        for line in (*uses, *sources):  # house rule: at most one emoji per line, and only at its start
            assert len(re.findall(EMOJI, line)) <= 1, (item.id, line)


def test_the_texts_are_accurate_for_known_items():
    fang = "\n".join(item_info.sources("monster_fang"))
    assert "گرگ وحشی" in fang and "اورک غران" in fang and "اسکلت جنگجو" in fang and "بسته‌ی شانسی" in fang
    assert "خنجر سایه" in "\n".join(item_info.uses("monster_fang"))  # it is a forge material
    ore = "\n".join(item_info.uses("iron_ore"))
    assert "ارتقای تجهیزات" in ore
    dagger_sources = "\n".join(item_info.sources("shadow_dagger"))
    assert "کوره" in dagger_sources and "صندوقچه" in dagger_sources and "باس" in dagger_sources
    assert "فروشگاه" in "\n".join(item_info.sources("wooden_sword")) and "۱۵۰" in "\n".join(item_info.sources("dagger"))
    assert "انرژی" in "\n".join(item_info.uses("energy_potion"))
    assert "تغییر نام" in "\n".join(item_info.uses("rename_ticket"))
    assert "پایه‌ی ساخت" in "\n".join(item_info.uses("dagger"))  # the plain dagger is what the forge turns into the shadow one
    assert "ارتقا" in "\n".join(item_info.uses("strength_ring"))


async def test_item_screens_show_the_uses_everywhere(h, services, db):
    p = await services.players.register(7, "u", "آرش", "elf", "archer")
    async with db.transaction() as tx:
        await services.inventory.grant(tx, p.id, "monster_fang", 2)
        gear_id = (await services.inventory.grant(tx, p.id, "dagger", 1))[0]
        await tx.execute("UPDATE players SET gold = 99999 WHERE id = ?", (p.id,))
    await h.panel(7, "item", "monster_fang")  # in the backpack
    assert "کاربرد" in h.session.last_text() and "از کجا" in h.session.last_text() and "اورک غران" in h.session.last_text()
    await h.panel(7, "shopitem", "iron_sword", "gear")  # in the shop
    assert "کاربرد" in h.session.last_text() and "فروشگاه" in h.session.last_text()
    await h.panel(7, "piece", str(gear_id))  # a gear piece in the backpack
    assert "کاربرد" in h.session.last_text() and "کوره" in h.session.last_text()
    assert get_item("dagger").name in h.session.last_text()
