"""Local preview of the mini app's API: no Bale, no bot token, a throw-away database with a demo realm.

    python scripts/miniapp_preview.py        # API on http://127.0.0.1:8085 ; then `npm run dev` in miniapp/

The real bot is never started here (it would fight the live bot for updates), and the real database is never touched:
the preview keeps its own file under data/. The page identifies itself with a plain user id, which the API accepts only
because ``miniapp_dev`` is on in this script.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eternal_realm.bot import app as _bot_app  # noqa: E402,F401 - registers every panel screen
from eternal_realm.bot.services import Services  # noqa: E402
from eternal_realm.config import Settings  # noqa: E402
from eternal_realm.context import AppContext  # noqa: E402
from eternal_realm.db.database import Database  # noqa: E402
from eternal_realm.db.repos import wallet  # noqa: E402
from eternal_realm.game.data.items import get_item  # noqa: E402
from eternal_realm.web import server  # noqa: E402

DEMO_USER = 1001
DB_PATH = Path("data/miniapp_preview.db")


async def seed(services: Services) -> None:
    """A hero with something in every corner of the game, a clan around them and a busy market."""
    if await services.players.find(DEMO_USER) is not None:
        return
    db, now = services.ctx.db, services.ctx.now()
    me = await services.players.register(DEMO_USER, "preview", "آرش کمانگیر", "elf", "archer")
    mates = [
        await services.players.register(2000 + i, f"mate{i}", name, race, cls)
        for i, (name, race, cls) in enumerate((("سارا", "fairy", "mage"), ("بهرام", "dragonborn", "warrior"), ("رها", "elf", "archer"), ("کاوه", "dwarf", "warrior")))
    ]
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 24, xp = 2400, energy = 120, wheel_spins = 5 WHERE id = ?", (me.id,))
        await wallet.apply(tx, me.id, gold=48_500, crystal=135, reason="preview", now=now)
        for item, qty in (("iron_ore", 42), ("herb", 18), ("moon_herb", 6), ("crystal_shard", 4), ("dragon_scale", 2), ("gold_ore", 7),
                          ("wooden_chest", 3), ("magic_chest", 1), ("energy_potion", 5), ("big_energy_potion", 2), ("monster_fang", 9), ("stone", 30)):
            await services.inventory.grant(tx, me.id, item, qty)
        for item in ("steel_sword", "tower_shield", "steel_helm", "chain_mail", "swift_boots", "strength_ring", "life_amulet", "hunter_bow", "leather_cap", "dagger"):
            await services.inventory.grant(tx, me.id, item, 1)
        for i, mate in enumerate(mates):
            await tx.execute("UPDATE players SET level = ? WHERE id = ?", (12 + 5 * i, mate.id))
            await wallet.apply(tx, mate.id, gold=20_000, reason="preview", now=now)
            await services.inventory.grant(tx, mate.id, "iron_ore", 30)
            await services.inventory.grant(tx, mate.id, "leather_cap", 1)
            await services.inventory.grant(tx, mate.id, "iron_sword", 1)
    me = await services.players.require(DEMO_USER)
    view = await services.inventory.view(me.id)
    worn: set[str] = set()
    for piece in view.gear:
        if piece.item.slot and piece.item.slot not in worn and piece.item.id not in ("hunter_bow", "leather_cap", "dagger"):
            try:
                await services.inventory.equip(me, piece.id)
                worn.add(piece.item.slot)
            except Exception:  # noqa: BLE001 - the preview should come up even if a piece does not fit
                pass
    clan = await services.clans.create(await services.players.require(DEMO_USER), "شیرهای شمال")
    for mate in mates:
        await services.clans.join(await services.players.require(mate.platform_user_id), clan.id)
    await services.clans.donate(await services.players.require(DEMO_USER), 6_000)
    for mate in mates[:3]:
        seller = await services.players.require(mate.platform_user_id)
        await services.market.list_stack(seller, get_item("iron_ore"), 10, 950)
        gear = (await services.inventory.view(seller.id)).gear
        cap = next(g for g in gear if g.item.id == "leather_cap")
        await services.market.list_gear(seller, cap.id, 130)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    DB_PATH.parent.mkdir(exist_ok=True)
    db = Database(DB_PATH)
    await db.connect()
    settings = Settings(token="preview-token", owner_id=DEMO_USER, db_path=DB_PATH, miniapp_dev=True, miniapp_enabled=True)
    services = Services.build(AppContext(db, settings))
    services.bot_username = "eternal_realm_bot"
    await seed(services)
    runner = await server.start(services, None)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
