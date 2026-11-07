"""Buying: premium shop buttons, Bale wallet invoices, pre-checkout and delivery."""

from __future__ import annotations

import contextlib
import logging

from baleropy import Bot, F, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from ..shared.errors import GameError
from . import views
from .callbacks import BuyCb
from .services import Services

log = logging.getLogger("eternal_realm.payments")
router = Router(name="payments")


def _is_private(message: Message) -> bool:
    return str(getattr(message.chat.type, "value", message.chat.type)) == "private"


@router.callback_query(BuyCb.filter())
async def on_buy(query: CallbackQuery, callback_data: BuyCb, services: Services, bot: Bot) -> None:
    message = query.message
    if message is None or not _is_private(message):
        raise GameError("خزانه‌ی ویژه فقط در پیام خصوصی ربات باز می‌شود؛ آنجا بیایید و خرید کنید.")
    player = await services.players.require(query.from_user.id)

    order = await services.payments.create_order(player, callback_data.id)
    pack = order.pack
    await bot.send_invoice(
        chat_id=query.from_user.id,
        title=pack.title[:32],
        description=views.pack_description(pack)[:255],
        payload=order.payload,
        provider_token=services.ctx.settings.provider_token,
        prices=[LabeledPrice(label=pack.title[:32], amount=order.amount)],
    )
    await query.answer("فاکتور پرداخت برایتان فرستاده شد 👇")


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, services: Services) -> None:
    try:
        error = await services.payments.check_precheckout(
            query.from_user.id, query.invoice_payload, query.total_amount
        )
    except Exception:
        log.exception("pre-checkout failed")
        error = "طوفانی در راه است؛ چند لحظه دیگر دوباره تلاش کنید."
    await query.answer(ok=error is None, error_message=error)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, services: Services, bot: Bot) -> None:
    payment = message.successful_payment
    user = message.from_user
    if payment is None or user is None:
        return
    charge = payment.provider_payment_charge_id or payment.telegram_payment_charge_id
    delivery = await services.payments.complete(
        user.id, payment.invoice_payload, payment.total_amount, charge
    )
    if delivery.duplicate:
        await message.answer("ℹ️ این پرداخت پیش‌تر ثبت شده و کالایتان را گرفته‌اید؛ نگران نباشید، پولی دوباره کم نشد.")
        return
    await message.answer(views.delivery(delivery.order))
    with contextlib.suppress(BaleAPIError):
        buyer = await services.players.get(delivery.player_id)
        totals = await services.admin.stats()
        report = views.sale_report(delivery.order, buyer, user, charge, services.ctx.now(), totals)
        await bot.send_message(services.ctx.settings.owner_id, report)
