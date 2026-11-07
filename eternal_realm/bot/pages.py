"""Private-chat pages: each returns ``(text, buttons)`` and is reachable from the main menu."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..game.models import Player
from . import keyboards, views
from .services import Services

Page = tuple[str, keyboards.Rows]
PageFn = Callable[[Services, Player], Awaitable[Page]]

PAGES: dict[str, PageFn] = {}


def page(name: str) -> Callable[[PageFn], PageFn]:
    def register(fn: PageFn) -> PageFn:
        PAGES[name] = fn
        return fn

    return register


@page("home")
async def home(services: Services, player: Player) -> Page:
    text = await profile_text(services, player)
    return text, keyboards.main_menu()


@page("profile")
async def profile_page(services: Services, player: Player) -> Page:
    return await profile_text(services, player), keyboards.back_to_menu()


@page("help")
async def help_page(services: Services, player: Player) -> Page:
    return views.help_text(), keyboards.back_to_menu()


@page("inventory")
async def inventory_page(services: Services, player: Player) -> Page:
    view = await services.inventory.view(player.id)
    return views.inventory(player.name, view), keyboards.back_to_menu()


@page("equipment")
async def equipment_page(services: Services, player: Player) -> Page:
    view = await services.inventory.view(player.id)
    stats = await services.characters.stats(player)
    return views.equipment(player.name, view, stats), keyboards.back_to_menu()


@page("shop")
async def shop_page(services: Services, player: Player) -> Page:
    return views.shop_listing(), keyboards.back_to_menu()


async def profile_text(services: Services, player: Player) -> str:
    stats = await services.characters.stats(player)
    return views.profile(
        player, stats, services.characters.xp_needed(player), services.characters.max_energy(player)
    )
