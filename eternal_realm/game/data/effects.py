"""Blessings and curses: temporary changes to a hero's strength. Curses trade one thing for another."""

from __future__ import annotations

from dataclasses import dataclass, field

from .stats import Stats


@dataclass(frozen=True)
class Effect:
    id: str
    emoji: str
    name: str
    blessing: bool
    story: str
    #: stat -> multiplier added to 1 (0.10 = +10%)
    mult: dict[str, float] = field(default_factory=dict)
    #: stat -> flat change
    flat: dict[str, int] = field(default_factory=dict)
    minutes: int = 60

    def lines(self) -> list[str]:
        from .stats import STAT_LABELS

        out = []
        for stat, m in self.mult.items():
            out.append(f"{STAT_LABELS[stat]} {'+' if m > 0 else '-'}{round(abs(m) * 100)}٪".translate(_FA))
        for stat, v in self.flat.items():
            out.append(f"{STAT_LABELS[stat]} {'+' if v > 0 else '-'}{abs(v)}".translate(_FA))
        return out

    def apply(self, stats: Stats) -> Stats:
        values = stats.as_dict()
        for stat, m in self.mult.items():
            values[stat] = round(values[stat] * (1 + m))
        for stat, v in self.flat.items():
            values[stat] += v
        return Stats(**{k: max(0, v) for k, v in values.items()})


_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

EFFECTS: tuple[Effect, ...] = (
    Effect("sun", "☀️", "برکت خورشید", True, "گرمای خورشید در رگ‌هایتان می‌دود.", {"atk": 0.10, "hp": 0.10}),
    Effect("wind", "🍃", "برکت باد", True, "باد دور پاهایتان می‌چرخد و راه را باز می‌کند.", {"speed": 0.25}, {"luck": 5}),
    Effect("iron", "🔰", "برکت آهنین", True, "پوستتان سخت‌تر از سنگ شده است.", {"defense": 0.20}),
    Effect("blood", "🩸", "نفرین خون", False, "خشم در جانتان می‌جوشد، اما دفاعتان می‌شکند.", {"atk": 0.20, "defense": -0.15}),
    Effect("shadow", "🌑", "نفرین سایه", False, "سایه‌ها جادویتان را قوی می‌کنند، ولی شانس را می‌دزدند.", {"magic": 0.20}, {"luck": -5}),
    Effect("slow", "🐌", "نفرین کندی", False, "پاهایتان سنگین شده و ضربه‌ها سست.", {"speed": -0.25, "atk": -0.05}),
)

_BY_ID = {e.id: e for e in EFFECTS}


def get_effect(effect_id: str) -> Effect:
    return _BY_ID[effect_id]
