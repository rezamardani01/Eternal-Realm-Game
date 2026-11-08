"""Personal offers: the screens, the loop that delivers them and the player's on/off switch."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot
from baleropy.exceptions import BaleAPIError

from ..game.data.offers import DAILY_CAP
from ..shared.text import bold, fa, headline
from . import keyboards
from .panel import Ctx, Screen, screen
from .services import Services

log = logging.getLogger("eternal_realm.offers")


def offer_message(offer) -> str:  # noqa: ANN001 - Offer
    return headline(f"✉️ {bold(offer.rule.title)}\n\nفرمانده عزیز!\n\n{offer.text}")


async def deliver(bot: Bot, services: Services) -> int:
    sent = 0
    for user_id, offer in await services.offers.due():
        buttons = [
            [keyboards.panel_button(offer.rule.button, offer.rule.screen, user_id)],
            [keyboards.panel_button("🔕 دیگر پیشنهاد نفرست", "offeroff", user_id)],
        ]
        with contextlib.suppress(BaleAPIError):  # the player never opened a chat with the bot: nothing to do
            await bot.send_message(user_id, offer_message(offer), buttons=buttons)
            sent += 1
    return sent


async def processor(bot: Bot, services: Services, interval: float = 900.0) -> None:
    while True:
        try:
            await deliver(bot, services)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("offer delivery failed")
        await asyncio.sleep(interval)


@screen("offerreturn")
async def offer_return(c: Ctx) -> Screen:
    gold = await c.services.offers.claim_return_gift(c.player)
    return Screen(
        f"🎁 {bold('هدیه‌ی بازگشت رسید!')}\n\n{fa(gold)} سکه به کیفتان اضافه شد. خوش برگشتید، فرمانده!",
        [[c.btn("🏰 قلمرو من", "home")]],
        toast=f"🎁 {fa(gold)} سکه گرفتید",
    )


@screen("offerwelcome")
async def offer_welcome(c: Ctx) -> Screen:
    from .mission_panel import missions

    fresh = await c.services.missions.grant_welcome(c.player)
    shown = await missions(c)
    shown.toast = "🎯 مأموریت ویژه‌ی بازگشت به لیست شما اضافه شد" if fresh else "🎯 مأموریت ویژه‌ی امروز را دارید"
    return shown


@screen("offeroff")
async def offer_off(c: Ctx) -> Screen:
    await c.services.offers.set_enabled(c.player, False)
    return Screen(
        f"🔕 {bold('پیشنهادها خاموش شد')}\n\nدیگر پیام شخصی نمی‌فرستیم. هر وقت خواستید از «پیشنهادها» روشنشان کنید.",
        [],
    )


@screen("offers")
async def offers(c: Ctx) -> Screen:
    on = await c.services.offers.enabled(c.player)
    text = (
        f"✉️ {bold('پیشنهادهای شخصی')}\n\n"
        "ربات با توجه به وضعیت شما گاهی یک پیشنهاد مفید می‌فرستد؛ مثلاً جایزه‌ی آماده یا کارت‌های کم‌مانده.\n\n"
        f"حداکثر {fa(DAILY_CAP)} پیشنهاد در روز، فقط در پیام خصوصی.\n\n"
        f"وضعیت فعلی: {'روشن ✅' if on else 'خاموش ⛔'}"
    )
    label = "🔕 خاموش کردن" if on else "🔔 روشن کردن"
    return Screen(text, [[c.btn(label, "offertoggle", "0" if on else "1")], c.back("home")])


@screen("offertoggle")
async def offer_toggle(c: Ctx) -> Screen:
    await c.services.offers.set_enabled(c.player, c.a == "1")
    shown = await offers(c)
    shown.toast = "✉️ پیشنهادها روشن شد" if c.a == "1" else "🔕 پیشنهادها خاموش شد"
    return shown
