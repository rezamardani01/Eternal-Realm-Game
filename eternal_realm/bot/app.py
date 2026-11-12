"""Assembling and running the bot."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot, Dispatcher, Router
from baleropy.exceptions import BaleUnauthorized

from ..config import ConfigError, Settings
from ..context import AppContext
from ..db.database import Database
from . import boss, clan_panel, clanwar_panel, group_dungeon, membership, duels, events, maintenance, onboarding, panel, payments, quest_panel  # noqa: F401
from .lockdown import MaintenanceMiddleware
from . import academy_panel, solo_panel, habit_panel, raid_ui, notifier, gift_panel, city_panel, wheel_panel, exchange_panel, team_battle, achievement_panel, admin_panel, bet_panel, invite_panel, ascend_panel, altar_panel, card_panel, contest_panel, craft_panel, dungeon_panel, mission_panel, offers, path_panel, pet_panel, transfer_panel, vip_panel  # noqa: F401
from .commands import REGISTRY
from .commands import router as commands_router
from .membership import MembershipMiddleware
from .middlewares import ErrorMiddleware, UserLockMiddleware
from .services import Services

log = logging.getLogger("eternal_realm")


def _attach(dp: Dispatcher, *routers: Router) -> None:
    """Module-level routers are reused when a dispatcher is rebuilt (tests, restarts)."""
    for router in routers:
        router._parent = None  # noqa: SLF001 - Baleropy has no public detach
    dp.include_routers(*routers)


def build_dispatcher(services: Services) -> Dispatcher:
    dp = Dispatcher(services=services, settings=services.ctx.settings)
    locks, errors, gate = UserLockMiddleware(), ErrorMiddleware(), MembershipMiddleware()
    lockdown = MaintenanceMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.middleware(locks)  # outermost: one update per player at a time
        observer.middleware(errors)
        observer.middleware(lockdown)  # maintenance mode: managers only
        observer.middleware(gate)  # nobody plays before joining the required channels
    REGISTRY.configure(services.ctx.settings.command_overrides)
    # order matters: FSM-bound onboarding first, free-text commands last
    _attach(
        dp, onboarding.router, panel.listing_router, admin_panel.router, bet_panel.router, panel.router, payments.router, city_panel.router, duels.router, team_battle.router, boss.router,
        membership.router, group_dungeon.router,
        events.router, clan_panel.router, commands_router,
    )
    return dp


async def run(settings: Settings) -> None:
    db = Database(settings.db_path)
    await db.connect()
    services = Services.build(AppContext(db, settings))
    bot = Bot(settings.token)
    try:
        try:
            me = await bot.me()
        except BaleUnauthorized as error:
            raise ConfigError("توکن ربات نامعتبر است؛ توکن را در config.toml بررسی کنید.") from error
        services.bot_username = me.username or ""
        log.info("Eternal Realm is up as @%s", services.bot_username)
        dp = build_dispatcher(services)
        background = [
            asyncio.create_task(duels.janitor(bot, services), name="janitor"),
            asyncio.create_task(maintenance.backup_loop(db), name="backup"),
            asyncio.create_task(boss.processor(bot, services), name="boss-processor"),
            asyncio.create_task(events.processor(bot, services), name="event-processor"),
            asyncio.create_task(offers.processor(bot, services), name="offer-processor"),
            asyncio.create_task(path_panel.processor(bot, services), name="path-notifier"),
            asyncio.create_task(city_panel.processor(bot, services), name="city-alerts"),
            asyncio.create_task(notifier.processor(bot, services), name="notifier"),
            asyncio.create_task(raid_ui.processor(bot, services), name="raid-processor"),
        ]
        try:
            await dp.start_polling(bot, skip_updates=True)
        finally:
            for task in background:
                task.cancel()
            for task in background:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    finally:
        with contextlib.suppress(Exception):
            await bot.close()
        await db.close()
