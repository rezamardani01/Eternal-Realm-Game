"""Tap every button we can reach, in private and in a group, and demand that nothing crashes.

The error middleware turns crashes into a polite message, so the only way to notice them is the log.
"""

import logging

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


async def prepared_player(services, db, uid, name):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 8 WHERE id = ?", (p.id,))
        await wallet.apply(tx, p.id, gold=80_000, crystal=300, reason="t", now=services.ctx.now())
        for item_id, qty in [("wooden_chest", 3), ("magic_chest", 1), ("iron_ore", 30), ("energy_potion", 3),
                             ("herb", 5), ("leather_cap", 2), ("iron_sword", 1), ("chain_mail", 1)]:
            await services.inventory.grant(tx, p.id, item_id, qty)
    return await services.players.require(uid)


async def explore(h: Harness, uid: int, *, group: bool, budget: int = 450) -> int:
    """Breadth-first tour of the panel: press each distinct button once."""
    seen: set[str] = set()
    queue: list[str] = []

    def collect() -> None:
        for button in h.session.last_buttons():
            data = button.get("callback_data")
            if data and data not in seen and data.startswith(("p:", "b:", "race", "cls")):
                seen.add(data)
                queue.append(data)

    collect()
    pressed = 0
    while queue and pressed < budget:
        data = queue.pop(0)
        await h.click(uid, data, group=group)
        pressed += 1
        collect()
    return pressed


async def test_walking_the_whole_panel_never_crashes(services, db, caplog):
    caplog.set_level(logging.ERROR, logger="eternal_realm")
    h = Harness(services)
    me = await prepared_player(services, db, 10, "آرش")
    await prepared_player(services, db, 11, "سارا")
    gear = [g for g in (await services.inventory.view(me.id)).gear if g.item.id == "leather_cap"]
    await services.market.list_gear(me, gear[0].id, 900)

    await h.say(10, "/start")
    pressed_private = await explore(h, 10, group=False)
    await h.say(10, "قلمرو", group=True)
    pressed_group = await explore(h, 10, group=True)
    await h.say(11, "بازار", group=True)
    await explore(h, 11, group=True, budget=120)

    crashes = [r for r in caplog.records if r.levelno >= logging.ERROR and r.name.startswith("eternal_realm")]
    assert not crashes, [(r.getMessage(), "\n".join((r.exc_text or "").splitlines()[-14:])) for r in crashes[:2]]
    assert pressed_private > 60 and pressed_group > 40  # the tour really covered a lot


async def test_every_group_command_runs_without_a_crash(services, db, caplog):
    caplog.set_level(logging.ERROR, logger="eternal_realm")
    h = Harness(services)
    await prepared_player(services, db, 10, "آرش")
    await prepared_player(services, db, 11, "سارا")
    h.session.chat_admins.add(10)
    words = ["قلمرو", "پروفایل", "راهنما", "جایزه", "ماهیگیری", "معدن", "گیاه", "جستجو", "شکار", "استراحت",
             "کوله‌پشتی", "تجهیزات", "صندوقچه", "فروشگاه", "بازار", "فروشگاه ویژه", "ماجراجویی", "رتبه",
             "برترین‌ها", "ثروتمندان", "قهرمانان", "کیف پول", "کیف من", "باس", "احضار باس", "تنظیمات گروه",
             "انتقال 100", "مبارزه", "غیرفعال معدن", "فعال معدن"]
    for word in words:
        await h.say(10, word, group=True, reply_to=h.message_of(11) if word in ("پروفایل", "انتقال 100", "مبارزه") else None)
    crashes = [r for r in caplog.records if r.levelno >= logging.ERROR and r.name.startswith("eternal_realm")]
    assert not crashes, [(r.getMessage(), "\n".join((r.exc_text or "").splitlines()[-14:])) for r in crashes[:2]]
