"""Input validation for player-supplied text."""

from __future__ import annotations

import re

from .errors import GameError
from .text import normalize

NAME_MIN, NAME_MAX = 2, 16
_NAME_RE = re.compile(r"^[A-Za-z0-9_؀-ۿ]+( [A-Za-z0-9_؀-ۿ]+)*$")
_FORBIDDEN = ("ادمین", "admin", "owner", "مالک", "ربات", "سازنده")


def clean_name(raw: str) -> str:
    """Validate a character name and return it normalised, or raise :class:`GameError`."""
    name = normalize(raw)
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise GameError(f"نام باید بین {NAME_MIN} تا {NAME_MAX} حرف باشد.")
    if not _NAME_RE.match(name):
        raise GameError("نام فقط می‌تواند شامل حروف فارسی/انگلیسی، عدد و زیرخط باشد.")
    lowered = name.lower()
    if any(word in lowered for word in _FORBIDDEN):
        raise GameError("این نام مجاز نیست، یک نام دیگر انتخاب کن.")
    return name
