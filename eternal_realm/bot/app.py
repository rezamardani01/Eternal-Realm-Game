"""Assembling and running the bot."""

from __future__ import annotations

import logging

from baleropy import Bot, Dispatcher, Router

from ..config import Settings
from ..context import AppContext
from ..db.database import Database
from . import menu, onboarding
from .middlewares import ErrorMiddleware
from .services import Services

log = logging.getLogger("eternal_realm")


def _attach(dp: Dispatcher, *routers: Router) -> None:
    """Module-level routers are reused when a dispatcher is rebuilt (tests, restarts)."""
    for router in routers:
        router._parent = None  # noqa: SLF001 - Baleropy has no public detach
    dp.include_routers(*routers)


def build_dispatcher(services: Services) -> Dispatcher:
    dp = Dispatcher(services=services, settings=services.ctx.settings)
    errors = ErrorMiddleware()
    dp.message.middleware(errors)
    dp.callback_query.middleware(errors)
    _attach(dp, onboarding.router, menu.router)
    return dp


async def run(settings: Settings) -> None:
    db = Database(settings.db_path)
    await db.connect()
    services = Services.build(AppContext(db, settings))
    bot = Bot(settings.token)
    try:
        me = await bot.me()
        services.bot_username = me.username or ""
        log.info("Eternal Realm is up as @%s", services.bot_username)
        dp = build_dispatcher(services)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await db.close()
