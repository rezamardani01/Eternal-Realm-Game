"""Private main menu navigation."""

from __future__ import annotations

from baleropy import Router
from baleropy.types import CallbackQuery

from . import pages
from .callbacks import MenuCb
from .services import Services

router = Router(name="menu")


@router.callback_query(MenuCb.filter())
async def open_page(query: CallbackQuery, callback_data: MenuCb, services: Services) -> None:
    render = pages.PAGES.get(callback_data.page)
    if render is None or query.message is None:
        await query.answer()
        return
    player = await services.players.require(query.from_user.id)
    text, buttons = await render(services, player)
    await query.message.edit_text(text, buttons=buttons)
    await query.answer()
