"""Bet duels in glass buttons: «مبارزه شرطی» → pick what to bet → pick how much → wait for someone to accept."""

from __future__ import annotations

import contextlib

from baleropy import Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery

from ..game.data.items import get_item
from ..game.services.bets import FEE_PERCENT, LIMITS, OPEN_SECONDS, stake_label
from ..shared.errors import GameError
from ..shared.text import bold, fa
from . import views
from .callbacks import BetCb
from .duels import render
from .panel import Ctx, Screen, _int, _nav, _page, screen
from .services import Services

router = Router(name="bets")

KIND_ICONS = {"gold": "🪙 سکه", "crystal": "💎 کریستال"}
STEPS = {"gold": (10, 100, 1000), "crystal": (1, 5, 25), "item": (1, 5, 25)}
DEFAULT_AMOUNT = {"gold": 100, "crystal": 5, "item": 1}


def _split(raw: str) -> tuple[str, str]:
    """«gold» / «crystal» / «item.iron_ore» -> (kind, item id)"""
    kind, _, item_id = raw.partition(".")
    return kind, item_id


@screen("bet")
async def bet_home(c: Ctx) -> Screen:
    if not c.is_group:
        raise GameError("دوئل شرطی در گروه‌ها انجام می‌شود؛ در گروه بنویسید «مبارزه شرطی».")
    mine = await c.services.bets.open_for(c.player.id)
    if mine is not None:
        text = f"🎰 {bold('شرط باز دارید')}\n\nیک شرط با {mine.label} هنوز تمام نشده؛ اول آن تمام شود یا لغوش کنید."
        rows = [[c.btn("❌ لغو شرط", "betcancel", mine.id, style="danger")] if mine.status == "open" else c.btn("🔙", "home")]
        return Screen(text, rows)
    me = await c.refresh()
    text = (
        f"🎰 {bold('دوئل شرطی')}\n\n"
        "سر چه چیزی شرط می‌بندید؟ هر دو طرف باید همان مقدار را داشته باشند و برنده همه‌چیز را می‌برد.\n\n"
        f"🪙 سکه‌ی شما: {fa(me.gold)}\n"
        f"💎 کریستال شما: {fa(me.crystal)}\n\n"
        "👇 یکی را انتخاب کنید"
    )
    rows = [
        [c.btn("🪙 سکه", "betamt", "gold", DEFAULT_AMOUNT["gold"]), c.btn("💎 کریستال", "betamt", "crystal", DEFAULT_AMOUNT["crystal"])],
        [c.btn("⛓️ منابع", "betitems", 0)],
        [c.btn("❌ انصراف", "home")],
    ]
    return Screen(text, rows)


@screen("betitems")
async def bet_items(c: Ctx) -> Screen:
    stacks = await c.services.bets.stackable_resources(c.player.id)
    if not stacks:
        return Screen(f"⛓️ {bold('منابع')}\n\nمنبعی برای شرط بستن ندارید.", [c.back("bet")])
    page = max(0, _int(c.a or "0", "صفحه"))
    chunk, prev, nxt = _page(stacks, page)
    rows = [[c.btn(f"{get_item(i).label} ×{fa(q)}", "betamt", f"item.{i}", 1)] for i, q in chunk]
    if nav := _nav(c, "betitems", page, prev, nxt):
        rows.append(nav)
    rows.append(c.back("bet"))
    return Screen(f"⛓️ {bold('منابع')}\n\nکدام منبع را شرط می‌بندید؟ 👇", rows)


@screen("betamt")
async def bet_amount(c: Ctx) -> Screen:
    kind, item_id = _split(c.a)
    if kind not in LIMITS:
        raise GameError("نوع شرط درست نیست.")
    have = await c.services.bets.holdings(c.player.id, kind, item_id)
    low, high = LIMITS[kind]
    cap = min(have, high)
    if cap < low:
        name = get_item(item_id).label if kind == "item" else KIND_ICONS[kind]
        raise GameError(f"برای شرط‌بندی باید دست‌کم {fa(low)} {name} داشته باشید.")
    amount = max(low, min(_int(c.b or "1"), cap))

    def step(delta: int):  # noqa: ANN202
        new = max(low, min(cap, amount + delta))
        return c.btn(f"{'+' if delta > 0 else '-'}{fa(abs(delta))}", "betamt", c.a, new)

    small, mid, big = STEPS[kind]
    rows = [[step(-mid), step(-small), step(small), step(mid)], [step(-big), step(big)]]
    rows.append([c.btn(f"✅ ثبت شرط ({fa(amount)})", "betgo", c.a, amount, style="success")])
    rows.append([c.btn("🔙 بازگشت", "betitems" if kind == "item" else "bet"), c.btn("❌ انصراف", "home")])
    label = stake_label(kind, item_id, amount)
    text = (
        f"🎰 {bold('مقدار شرط')}\n\n"
        f"💰 شرط: {bold(label)}\n"
        f"👛 موجودی شما: {fa(have)}\n\n"
        + (f"🏦 از جایزه‌ی برنده {fa(FEE_PERCENT)}٪ کارمزد کم می‌شود.\n\n" if kind != "item" else "")
        + "با دکمه‌ها مقدار را کم و زیاد کنید، بعد دکمه‌ی سبز را بزنید 👇"
    )
    return Screen(text, rows)


@screen("betgo")
async def bet_go(c: Ctx) -> Screen:
    kind, item_id = _split(c.a)
    bet = await c.services.bets.create(c.player, c.chat_id, kind, item_id, _int(c.b or "1"))
    if c.message is not None:
        await c.services.bets.attach_message(bet.id, c.message.message_id)
    await c.refresh()
    return Screen(views.bet_waiting(bet, c.player, OPEN_SECONDS), _waiting_buttons(bet), toast="🎰 شرط ثبت شد")


@screen("betcancel")
async def bet_cancel(c: Ctx) -> Screen:
    await c.services.bets.cancel(_int(c.a), c.player)
    return Screen(f"↩️ {bold('شرط لغو شد')}\n\nشرط شما برگشت و چیزی از دست نرفت.", [])


def _waiting_buttons(bet):  # noqa: ANN001, ANN202
    from baleropy import Button

    accept = [[Button.inline("⚔️ قبول شرط و ورود به دوئل", BetCb(action="accept", id=bet.id), style="success")]]
    return accept + [[Button.inline("❌ لغو شرط (سازنده)", BetCb(action="cancel", id=bet.id), style="danger")]]


@router.callback_query(BetCb.filter())
async def on_bet_button(query: CallbackQuery, callback_data: BetCb, services: Services) -> None:
    message = query.message
    if message is None:
        await query.answer()
        return
    player = await services.players.require(query.from_user.id)
    if callback_data.action == "accept":
        bet, duel, update = await services.bets.accept(callback_data.id, player)
        await services.duels.attach_message(duel.id, message.message_id)
        text, buttons = render(update, services.ctx.balance.duel_turn_seconds)
        header = f"🎰 {bold('دوئل شرطی شروع شد')} · شرط: {bold(bet.label)}\n\n"
        await message.edit_text(header + text, buttons=buttons)
        await query.answer("⚔️ شرط قبول شد!")
    elif callback_data.action == "cancel":
        await services.bets.cancel(callback_data.id, player)
        await message.edit_text(f"↩️ {bold('شرط لغو شد')}\n\nسازنده‌ی شرط آن را پس گرفت و چیزی از دست نرفت.")
        await query.answer("↩️ لغو شد")
    else:
        await query.answer()


async def announce_expired(bot, services: Services) -> None:  # noqa: ANN001
    """Janitor step: bets nobody accepted are refunded and their message says so."""
    for bet in await services.bets.expire_stale():
        if bet.message_id is None:
            continue
        with contextlib.suppress(BaleAPIError):
            await bot.edit_message_text(
                bet.chat_id, bet.message_id,
                f"⌛ {bold('شرط بی‌پاسخ ماند')}\n\nکسی شرط {bet.label} را قبول نکرد و به سازنده برگشت.",
            )

