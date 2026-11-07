"""Errors that carry a message meant to be shown to the player."""

from __future__ import annotations


class GameError(Exception):
    """A rule of the game was broken. ``str(error)`` is a Persian message for the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotRegistered(GameError):
    def __init__(self) -> None:
        super().__init__("اول باید در ربات استارت بزنی و شخصیتت را بسازی.")
