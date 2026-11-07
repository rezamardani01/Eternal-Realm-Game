"""Buying: premium shop buttons, Bale wallet invoices, pre-checkout and delivery."""

from __future__ import annotations

import contextlib
import logging

from baleropy import Bot, F, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from ..shared.errors import GameError
from ..shared.text import fa
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
        raise GameError("برای خرید، وارد پیام خصوصی ربات شو.")
    player = await services.players.require(query.from_user.id)

    if callback_data.kind == "crystal":
        currency, total = await services.chests.buy(player, callback_data.id, 1)
        icon = "🪙" if currency == "gold" else "💎"
        await message.answer(f"✅ صندوقچه خریده شد ({fa(total)} {icon}).\nبرای باز کردن: «باز کردن» + نام صندوقچه")
        await query.answer("✅ خریداری شد")
        return

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
    await query.answer("فاکتور پرداخت فرستاده شد 👇")


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, services: Services) -> None:
    try:
        error = await services.payments.check_precheckout(
            query.from_user.id, query.invoice_payload, query.total_amount
        )
    except Exception:
        log.exception("pre-checkout failed")
        error = "خطای موقت؛ لطفاً دوباره تلاش کن."
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
        await message.answer("ℹ️ این پرداخت قبلاً ثبت و تحویل داده شده بود.")
        return
    await message.answer(views.delivery(delivery.order))
    with contextlib.suppress(BaleAPIError):
        await bot.send_message(
            services.ctx.settings.owner_id,
            f"💰 فروش جدید: {delivery.order.pack.label} — {fa(delivery.order.amount // 10)} تومان "
            f"(کاربر {user.id}، سفارش {delivery.order.id})",
        )
