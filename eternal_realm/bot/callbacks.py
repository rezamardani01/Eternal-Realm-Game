"""Typed callback payloads for inline buttons (Bale limits them to 64 bytes)."""

from __future__ import annotations

from baleropy.filters import CallbackData


class RaceCb(CallbackData, prefix="race"):
    id: str


class ClassCb(CallbackData, prefix="cls"):
    id: str


class PanelCb(CallbackData, prefix="p"):
    """One tap in the personal panel: ``s`` screen, ``a``/``b`` arguments, ``o`` owner's Bale id."""

    s: str
    a: str | None = None
    b: str | None = None
    o: int


class BossCb(CallbackData, prefix="b"):
    action: str
    id: int


class DuelCb(CallbackData, prefix="d"):
    action: str
    id: int


class TeamCb(CallbackData, prefix="tb"):
    """A tap in a team battle: ``arg`` is ``team * 10 + seat`` for seats."""

    action: str
    id: int
    arg: int = 0


class BetCb(CallbackData, prefix="bt"):
    action: str
    id: int


class EventCb(CallbackData, prefix="e"):
    action: str
    id: int
    arg: int = 0


class ClanCb(CallbackData, prefix="c"):
    action: str
    id: int
    arg: int = 0


class DgCb(CallbackData, prefix="g"):
    action: str
    id: int


class BuyCb(CallbackData, prefix="buy"):
    kind: str
    id: str
