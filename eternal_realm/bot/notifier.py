"""The loop that delivers a hero's queued messages (achievements, ended boosts, sold listings...) in the private chat."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy.exceptions import BaleAPIError

from . import keyboards
from .services import Services

log = logging.getLogger("eternal_realm.notifier")

BUTTON_LABELS = {"achf": "🎁 دریافت پاداش", "premium": "💎 خزانه قلمرو", "citytroops": "⚔️ ارتش", "city": "🏰 فرمانروایی"}


async def deliver(bot, services: Services) -> int:  # noqa: ANN001
    """Send everything that is due once; returns how many messages went out."""
    await services.alerts.sweep()
    sent = 0
    for alert in await services.alerts.pending():
        buttons = None
        if alert.screen:
            label = BUTTON_LABELS.get(alert.screen, "📲 باز کردن")
            buttons = [[keyboards.panel_button(label, alert.screen, alert.uid, alert.arg)]]
        with contextlib.suppress(BaleAPIError):
            await bot.send_message(alert.uid, alert.text, buttons=buttons) if buttons else await bot.send_message(alert.uid, alert.text)
            sent += 1
    return sent


async def processor(bot, services: Services, interval: float = 15.0) -> None:  # noqa: ANN001
    while True:
        try:
            await deliver(bot, services)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("notifier failed")
        await asyncio.sleep(interval)
