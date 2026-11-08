"""The six character statistics and arithmetic on them."""

from __future__ import annotations

from dataclasses import dataclass, fields


_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

#: stat id -> label with its icon (used for button and line texts)
STAT_LABELS = {
    "hp": "❤️ جان",
    "atk": "⚔️ حمله",
    "defense": "🛡️ دفاع",
    "magic": "✨ جادو",
    "speed": "💨 سرعت",
    "luck": "🍀 شانس",
}

#: what each stat does, shown when a player taps it
STAT_HELP = {
    "hp": "جان: هر چه بیشتر باشد، بیشتر در نبرد دوام می‌آورید.",
    "atk": "حمله: قدرت ضربه‌های شمشیر و تیر شما.",
    "defense": "دفاع: هر چه بیشتر باشد، از ضربه‌های دشمن کمتر آسیب می‌بینید.",
    "magic": "جادو: قدرت حمله‌های جادویی.",
    "speed": "سرعت: نبرد را زودتر شروع می‌کنید و بیشتر جاخالی می‌دهید.",
    "luck": "شانس: ضربه‌ی کاری و پیدا کردن گنج‌های کمیاب را بیشتر می‌کند.",
    "energy": "انرژی: هر فعالیت مقداری انرژی می‌خواهد. با گذر زمان، استراحت یا معجون پر می‌شود.",
    "xp": "تجربه: با پر شدنش یک سطح بالاتر می‌روید.",
}


@dataclass(frozen=True)
class Stats:
    hp: int = 0
    atk: int = 0
    defense: int = 0
    magic: int = 0
    speed: int = 0
    luck: int = 0

    def __add__(self, other: Stats) -> Stats:
        return Stats(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    def scaled(self, factor: float) -> Stats:
        return Stats(*(round(getattr(self, f.name) * factor) for f in fields(self)))

    def as_dict(self) -> dict[str, int]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def short(self) -> str:
        """Compact bonus line such as ``⚔️+8 💨+2``."""
        icons = (
            ("hp", "❤️"), ("atk", "⚔️"), ("defense", "🛡️"),
            ("magic", "✨"), ("speed", "💨"), ("luck", "🍀"),
        )
        parts = [f"{icon}{getattr(self, name):+d}" for name, icon in icons if getattr(self, name)]
        return " ".join(parts) or "—"

    def bonus_lines(self) -> list[str]:
        """One line per non-zero stat, e.g. ``⚔️ حمله +۸``."""
        out = []
        for name, label in STAT_LABELS.items():
            value = getattr(self, name)
            if value:
                sign = "+" if value > 0 else "-"
                out.append(f"{label} {sign}{str(abs(value)).translate(_FA)}")
        return out

    def lines(self) -> list[str]:
        labels = (
            ("hp", "❤️ سلامتی"),
            ("atk", "⚔️ حمله"),
            ("defense", "🛡️ دفاع"),
            ("magic", "✨ جادو"),
            ("speed", "💨 سرعت"),
            ("luck", "🍀 شانس"),
        )
        return [f"{label}: {getattr(self, name)}" for name, label in labels if getattr(self, name)]


BASE_STATS = Stats(hp=100, atk=10, defense=8, magic=6, speed=10, luck=5)
