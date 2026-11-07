"""Typed callback payloads for inline buttons (Bale limits them to 64 bytes)."""

from __future__ import annotations

from baleropy.filters import CallbackData


class RaceCb(CallbackData, prefix="race"):
    id: str


class ClassCb(CallbackData, prefix="cls"):
    id: str


class MenuCb(CallbackData, prefix="m"):
    page: str


class DuelCb(CallbackData, prefix="d"):
    action: str
    id: int


class UpgradeCb(CallbackData, prefix="up"):
    id: int
    level: int
