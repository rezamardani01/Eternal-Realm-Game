"""Small text helpers: Persian digits, normalisation and progress bars."""

from __future__ import annotations

import re

_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_FROM_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_CHAR_FIX = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "‌": " ", "‏": "", "‎": ""})
_SPACES = re.compile(r"\s+")


def fa(value: int | float | str) -> str:
    """``12500`` -> ``۱۲٬۵۰۰``."""
    if isinstance(value, float):
        value = round(value)
    text = f"{value:,}" if isinstance(value, int) else str(value)
    return text.replace(",", "٬").translate(_TO_FA)


def normalize(text: str) -> str:
    """Canonical form used for matching commands and names: Persian letters and ASCII digits."""
    return _SPACES.sub(" ", text.translate(_CHAR_FIX).translate(_FROM_FA)).strip()


def bold(value: object) -> str:
    """Bale Markdown bold. Put a space before it and after it (as the Bale docs require)."""
    return f"**{value}**"


_BASE = "[↩↪⌀-⏿☀-➿⭐⭕\U0001f000-\U0001faff]"
#: one emoji, including variation selectors and joined sequences such as 👨‍👩‍👧
EMOJI = f"{_BASE}️?(?:‍{_BASE}️?)*"
_LEAD = re.compile(rf"^((?:{EMOJI})+)\s+(.+)$", re.S)


def emphasize(line: str) -> str:
    """Bold a line, keeping a leading emoji outside the markers. Lines already bold stay as they are."""
    if "**" in line or not line.strip():
        return line
    match = _LEAD.match(line.strip())
    if match:
        return f"{match.group(1)} **{match.group(2).strip()}**"
    return f"**{line.strip()}**"


def headline(text: str) -> str:
    """Make the first line of a message a bold title (unless the text already has bold)."""
    if "**" in text:
        return text
    first, sep, rest = text.partition("\n")
    return emphasize(first) + sep + rest


def to_int(text: str) -> int | None:
    """Parse ``'۱٬۲۰۰'`` / ``'1,200'`` / ``'1200'`` into an int (``None`` if it is not a number)."""
    cleaned = normalize(text).replace(",", "").replace("٬", "").replace("،", "")
    return int(cleaned) if cleaned.isdigit() else None


def bar(current: int, maximum: int, width: int = 10) -> str:
    maximum = max(maximum, 1)
    filled = max(0, min(width, round(width * current / maximum)))
    return "▰" * filled + "▱" * (width - filled)


def duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{fa(seconds)} ثانیه"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{fa(minutes)} دقیقه" + (f" و {fa(sec)} ثانیه" if sec and minutes < 5 else "")
    hours, minutes = divmod(minutes, 60)
    return f"{fa(hours)} ساعت" + (f" و {fa(minutes)} دقیقه" if minutes else "")
