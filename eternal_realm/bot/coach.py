"""The «تحلیل نبرد» button: a short review of a finished fight, with tips for the hero's own build."""

from __future__ import annotations

from ..game.data.growth import slots_open
from ..game.engine import coaching
from ..game.engine.combat import Battle
from ..game.models import Player
from ..shared.text import bold
from .services import Services

LINE = "─" * 12


async def build_tips(services: Services, player: Player) -> list[str]:
    """Tips that come from what the hero has built (or has not): spare points, empty gear slots, no gear at all."""
    out = []
    if await services.growth.free_points(player) > 0:
        out.append("🎯 امتیاز ویژگی خرج‌نشده دارید؛ از «تجهیزات و مهارت‌ها ← ویژگی‌ها» خرجش کنید.")
    loadout = await services.arms.loadout(player.id)
    open_slots = slots_open(player.level)
    if len(loadout.worn) < open_slots:
        if await services.arms.owned(player.id):
            out.append("🧰 جایگاه خالی تجهیزات دارید؛ قطعه‌های کیفتان را بپوشید.")
        else:
            out.append("🛒 هنوز تجهیزاتی ندارید؛ از «تجهیزات قهرمان ← خرید تجهیزات» با سکه بخرید.")
    return out


async def review_text(services: Services, player: Player, battle: Battle, index: int) -> str:
    """The full review of the hero at ``index`` of a finished fight."""
    lines = [f"🔍 {bold('تحلیل نبرد')}", LINE, *coaching.summary(battle, index), "", f"💡 {bold('نکته‌ها')}"]
    lines += coaching.tips(battle, index)
    if battle.winner != index:
        lines += await build_tips(services, player)
    return "\n".join(lines)


def short_review(battle: Battle, index: int) -> list[str]:
    """The lines a solo fight's result carries by itself: the tips only (no database needed)."""
    return coaching.tips(battle, index)
