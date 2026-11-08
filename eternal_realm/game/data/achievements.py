"""Achievements: families of goals with three steps each. Every step pays once and says plainly what to do.

A family counts something the player does (a *deed*, counted since this feature arrived) or something they have (their
level, pets, cards...). ``how`` is the sentence shown to the player; ``{n}`` is replaced by the step's target.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    target: int
    gold: int = 0
    crystal: int = 0
    items: tuple[tuple[str, int], ...] = ()
    #: an honorary title shown on the profile (kept only when the player has none yet)
    title: str = ""


@dataclass(frozen=True)
class Family:
    id: str
    emoji: str
    name: str
    how: str
    #: a deed counted in ``deed_counts`` (``deed:hunt``) or a live value (``level``, ``pets``, ``cards``, ``invites``, ...)
    metric: str
    steps: tuple[Step, Step, Step]


FAMILIES: tuple[Family, ...] = (
    Family("hunt", "🐺", "شکارچی", "{n} بار «شکار» را انجام بده", "deed:hunt", (
        Step(10, gold=300), Step(100, gold=2_000, crystal=3), Step(500, gold=8_000, crystal=15, title="شکارچی بزرگ"))),
    Family("adventure", "🌍", "ماجراجو", "{n} بار ماجراجویی کن (ماهیگیری، معدن، گیاه و...)", "deed:activity", (
        Step(25, gold=250), Step(250, gold=2_500, crystal=3), Step(1_500, gold=10_000, crystal=20, title="سفرکرده"))),
    Family("duel", "⚔️", "دوئل‌باز", "{n} دوئل را ببر", "deed:duel_win", (
        Step(5, gold=300), Step(50, gold=3_000, crystal=4), Step(250, gold=12_000, crystal=25, title="شمشیر بی‌شکست"))),
    Family("boss", "🐉", "همراه باس", "در {n} نبرد با باس شرکت کن", "deed:boss", (
        Step(3, gold=400), Step(25, gold=3_500, crystal=4), Step(100, gold=12_000, crystal=25, title="هم‌رزم"))),
    Family("bossbane", "🏆", "باس‌کش", "{n} باس را با گروهت بکش", "deed:boss_win", (
        Step(1, gold=500, items=(("magic_chest", 1),)), Step(10, gold=4_000, crystal=6),
        Step(50, gold=15_000, crystal=30, items=(("royal_chest", 1),), title="اژدهاکش"))),
    Family("story", "📜", "داستان‌سرا", "{n} داستان را تا پایان بخوان", "deed:quest", (
        Step(3, gold=300), Step(20, gold=2_500, crystal=3), Step(100, gold=9_000, crystal=15, title="راوی"))),
    Family("dungeon", "🕳️", "فاتح سیاه‌چال", "{n} سیاه‌چال را فتح کن", "deed:dungeon_win", (
        Step(1, gold=400), Step(10, gold=3_000, crystal=4), Step(50, gold=11_000, crystal=22, title="شاه سیاه‌چال"))),
    Family("missions", "📅", "کارگزار", "{n} مأموریت روزانه را تمام کن", "deed:mission", (
        Step(10, gold=300), Step(50, gold=2_500, crystal=3), Step(200, gold=9_000, crystal=15, title="کارگزار قلمرو"))),
    Family("cardpack", "🃏", "کارت‌باز", "{n} بسته‌ی کارت باز کن", "deed:card_pack", (
        Step(3, gold=300), Step(20, gold=2_500, crystal=3), Step(100, gold=9_000, crystal=15))),
    Family("daily", "🎁", "وفادار", "{n} بار «جایزه»ی روزانه را بردار", "deed:daily", (
        Step(7, gold=400), Step(30, gold=3_000, crystal=4), Step(100, gold=10_000, crystal=20, title="وفادار قلمرو"))),
    Family("streak", "🔥", "پشتکار", "{n} روز پشت‌سرهم «جایزه»ی روزانه را بردار", "streak", (
        Step(7, gold=500), Step(14, gold=1_500, crystal=3), Step(30, gold=5_000, crystal=12, title="پشتکار"))),
    Family("level", "⭐", "قهرمان", "به سطح {n} برس", "level", (
        Step(10, gold=500), Step(30, gold=4_000, crystal=5), Step(60, gold=15_000, crystal=30, title="کهن‌قهرمان"))),
    Family("pets", "🐱", "دوستدار حیوان", "{n} حیوان خانگی داشته باش", "pets", (
        Step(1, gold=300), Step(4, gold=2_500, crystal=3), Step(8, gold=9_000, crystal=15, title="رام‌کننده"))),
    Family("cards", "🗂️", "کلکسیونر", "{n} کارت متفاوت جمع کن", "cards", (
        Step(8, gold=400), Step(20, gold=3_000, crystal=4), Step(31, gold=12_000, crystal=25, title="گنجور"))),
    Family("invites", "🤝", "سفیر قلمرو", "{n} دوست را با لینک دعوت به بازی بیاور", "invites", (
        Step(1, gold=300, crystal=1), Step(5, gold=2_000, crystal=5), Step(25, gold=10_000, crystal=25, title="سفیر قلمرو"))),
)
_BY_ID = {f.id: f for f in FAMILIES}


def get_family(family_id: str) -> Family:
    return _BY_ID[family_id]


def reward_text(step: Step) -> str:
    """A plain sentence (no emoji) for a step's reward."""
    from ...shared.text import fa
    from .items import get_item

    parts = []
    if step.gold:
        parts.append(f"{fa(step.gold)} سکه")
    if step.crystal:
        parts.append(f"{fa(step.crystal)} کریستال")
    parts += [f"{get_item(i).name} ×{fa(q)}" for i, q in step.items]
    if step.title:
        parts.append(f"عنوان «{step.title}»")
    return "، ".join(parts)
