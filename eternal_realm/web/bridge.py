"""Every panel screen of the bot, as data: the mini app draws it and sends the taps back.

The screens themselves are untouched: the same function that fills a glass panel in the chat is called here with the
same player, and its text and buttons are returned as JSON. Whatever the bot can do with buttons, the mini app can do.
"""

from __future__ import annotations

from typing import Any

from ..bot.callbacks import BuyCb, PanelCb
from ..bot.panel import SCREENS, Ctx
from ..bot.services import Services
from ..game.models import Player

#: screens that only make sense inside a chat message (a group lobby, a picture upload) and stay in the bot
BOT_ONLY = frozenset({"clanphoto", "clanphotoask", "clanphotook", "clanphotono", "bsummon", "boss"})
#: screens that end in a typed answer in the bot; the mini app asks for the value in its own form
PROMPTS = {"ListingFlow:waiting": "listing", "CityFlow:name": "city_name"}


class FormState:
    """Stands in for the chat's conversation state: remembers what a screen asked the player to type."""

    def __init__(self) -> None:
        self.state: str | None = None
        self.data: dict[str, Any] = {}

    async def set_state(self, state: object = None) -> None:
        self.state = getattr(state, "state", None) or (str(state) if state is not None else None)

    async def update_data(self, **values: Any) -> None:
        self.data.update(values)

    async def get_data(self) -> dict[str, Any]:
        return dict(self.data)

    async def clear(self) -> None:
        self.state, self.data = None, {}


def _button(button: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"text": button.text}
    style = getattr(button, "style", None)
    if style:
        out["style"] = str(getattr(style, "value", style))
    data = getattr(button, "callback_data", None)
    if getattr(button, "url", None):
        out["url"] = button.url
    elif getattr(button, "copy_text", None) is not None:
        out["copy"] = button.copy_text.text
    elif data and data.startswith(PanelCb.__prefix__ + PanelCb.__sep__):
        cb = PanelCb.unpack(data)
        out.update(s=cb.s, a=cb.a or "", b=cb.b or "")
        if cb.s in BOT_ONLY:
            out["bot_only"] = True
    elif data and data.startswith(BuyCb.__prefix__ + BuyCb.__sep__):
        cb = BuyCb.unpack(data)
        out["buy"] = {"kind": cb.kind, "id": cb.id}
    else:
        out["bot_only"] = True
    return out


async def run(services: Services, player: Player, name: str, a: str = "", b: str = "") -> dict[str, Any]:
    """Call one screen for a player and describe what it shows."""
    handler = SCREENS.get(name)
    if handler is None or name in BOT_ONLY:
        raise KeyError(name)
    state = FormState()
    ctx = Ctx(services, player, player.platform_user_id, a, b, False, player.platform_user_id, state, None)  # type: ignore[arg-type]
    shown = await handler(ctx)
    out: dict[str, Any] = {
        "screen": name, "a": a, "b": b,
        "text": shown.text,
        "rows": [[_button(btn) for btn in row] for row in shown.rows or [] if row],
        "toast": shown.toast, "alert": bool(shown.alert),
    }
    kind = PROMPTS.get(state.state or "")
    if kind:
        out["prompt"] = {**{k: str(v) for k, v in state.data.items()}, "form": kind}
    return out
