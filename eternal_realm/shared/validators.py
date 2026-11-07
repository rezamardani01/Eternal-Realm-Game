"""Input validation for player-supplied text."""

from __future__ import annotations

import re

from .errors import GameError
from .text import normalize

NAME_MIN, NAME_MAX = 2, 16
_NAME_RE = re.compile(r"^[A-Za-z0-9؀-ۿ]+( [A-Za-z0-9؀-ۿ]+)*$")
_FORBIDDEN = ("ادمین", "admin", "owner", "مالک", "ربات", "سازنده")


def clean_name(raw: str) -> str:
    """Validate a character name and return it normalised, or raise :class:`GameError`."""
    name = normalize(raw)
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise GameError(f"نام قهرمان باید بین {NAME_MIN} تا {NAME_MAX} حرف باشد؛ نه آن‌قدر کوتاه که گم شود و نه آن‌قدر بلند که در باد پخش شود. دوباره بنویسید.")
    if not _NAME_RE.match(name):
        raise GameError("در نام قهرمان فقط حرف فارسی یا انگلیسی، و عدد می‌توانید بنویسید. نشانه‌های دیگر را کنار بگذارید و دوباره امتحان کنید.")
    lowered = name.lower()
    if any(word in lowered for word in _FORBIDDEN):
        raise GameError("این نام در قلمرو ممنوع است. یک نام دیگر برای قهرمان خود انتخاب کنید.")
    return name
