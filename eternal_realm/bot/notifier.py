"""The loop that delivers a hero's queued messages (achievements, ended boosts, sold listings...) in the private chat."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy.exceptions import BaleAPIError

from . import keyboards
from .services import Services

log = logging.getLogger("eternal_realm.notifier")

BUTTON_LABELS = {
    "sfight": "⚔️ ادامه‌ی نبرد", "ach": "🏅 دستاوردها", "wheel": "🎡 گردونه شانس", "missions": "📅 مأموریت‌ها", "daily": "🎁 جایزه روزانه",
    "arenago": "🥊 میدان بات‌ها", "stage": "📖 داستان", "adv": "🗺️ ماجراجویی", "sbossv": "🐉 باس امروز", "citybuild": "🏗️ ساختمان‌ها",
    "clanwar": "🏅 لیگ خاندان‌ها", "cwar": "⚔️ جنگ خاندان‌ها", "cwarclaim": "🎁 دریافت جایزه‌ی جنگ", "achf": "🎁 دریافت پاداش", "premium": "💎 خزانه قلمرو", "citytroops": "⚔️ ارتش", "city": "🏰 فرمانروایی", "expd": "📜 گزارش اعزام", "world": "🌍 جهان زنده", "popup": "👀 ببینم چیست", "friends": "👥 دوستان", "rseason": "🏆 فصل رتبه‌بندی"}


_last = {"popups": 0}


async def deliver(bot, services: Services) -> int:  # noqa: ANN001
    """Send everything that is due once; returns how many messages went out."""
    await services.world.tick()
    await services.alerts.sweep()
    await services.clan_wars.sweep()
    await services.alerts.tips(services.advisor)
    await services.alerts.waiting()
    await services.ladder.close_due()
    await services.market.weekly_sellers()
    if services.ctx.now() - _last["popups"] >= 600:
        _last["popups"] = services.ctx.now()
        await services.popups.spawn_due()
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
