"""Errors that carry a message meant to be shown to the player."""

from __future__ import annotations


class GameError(Exception):
    """A rule of the game was broken. ``str(error)`` is a Persian message for the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AwayError(GameError):
    """The hero is on an expedition; ``left`` is the seconds still to go when it is the player's own hero (0 otherwise)."""

    def __init__(self, message: str, left: int = 0) -> None:
        super().__init__(message)
        self.left = left


class NotRegistered(GameError):
    def __init__(self) -> None:
        super().__init__("ای ماجراجوی ناشناس! هنوز نامی از شما در دفتر قلمرو نیست. به پیام خصوصی ربات بروید، /start را بزنید و قهرمان خود را بسازید؛ بعد برگردید و ماجراجویی را شروع کنید.")
