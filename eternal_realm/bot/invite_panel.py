"""«دعوت از دوستان» and the gift boxes the owner hands out («اهدا بسته ...»)."""

from __future__ import annotations

import contextlib

from baleropy import Button
from baleropy.exceptions import BaleAPIError

from ..game.services.invites import DAILY_REWARDS, PRIZES_PER_INVITE
from ..shared.errors import GameError
from ..shared.text import bold, fa, headline
from . import keyboards
from .panel import Ctx, Screen, _int, screen


@screen("invite")
async def invite(c: Ctx) -> Screen:
    username = c.services.bot_username
    if not username:
        raise GameError("لینک دعوت هنوز آماده نیست؛ کمی بعد دوباره امتحان کنید.")
    link = c.services.invites.link(username, c.player.platform_user_id)
    count = await c.services.invites.count(c.player.id)
    text = (
        f"🤝 {bold('دعوت از دوستان')}\n\n"
        "دوستانتان را به قلمرو دعوت کنید. هر دوستی که با لینک شما وارد شود و قهرمانش را بسازد، "
        "همان لحظه برایتان هدیه می‌رسد.\n\n"
        f"🎁 هدیه‌ی هر دعوت: {fa(PRIZES_PER_INVITE)} جایزه‌ی شانسی (سکه، معجون، صندوقچه، سنگ آهن و...)\n"
        f"📅 هر روز تا {fa(DAILY_REWARDS)} دعوت جایزه می‌دهد\n"
        f"👥 دعوت‌های موفق شما: {bold(fa(count))}\n\n"
        f"🔗 {bold('لینک دعوت شما')}\n{link}\n\n"
        "👇 لینک را کپی کنید و برای دوستانتان بفرستید"
    )
    rows = [[Button.copy_text("📋 کپی لینک", link, style="success")], [Button.url("📤 باز کردن لینک", link)], c.back("home")]
    return Screen(text, rows)


@screen("gbopen")
async def open_gift_box(c: Ctx) -> Screen:
    opened = await c.services.invites.open_box(c.player, _int(c.a))
    await c.refresh()
    text = (
        f"🎉 {bold('صندوق باز شد!')}\n\n"
        f"📦 {opened.pack_title}\n\n"
        f"🎁 {bold('داخلش بود')}\n{opened.haul}\n\n"
        "از طرف مالک قلمرو جاودان 💛"
    )
    return Screen(text, [[c.btn("🏰 قلمرو من", "home")]], toast="🎁 صندوق باز شد")


def box_button(owner: int, box_id: int):  # noqa: ANN201
    return [keyboards.panel_button("📦 باز کردن صندوق", "gbopen", owner, str(box_id))]


async def notify_box(bot, target, box_id: int, title: str) -> None:  # noqa: ANN001
    """The private note that goes with a gift box (the group reply carries the same button)."""
    text = headline(f"📦 {bold('صندوق هدیه‌ای از مالک قلمرو رسید!')}\n\n🎁 {title}\n\n👇 برای دیدن محتوایش بازش کنید")
    with contextlib.suppress(BaleAPIError):
        await bot.send_message(target.platform_user_id, text, buttons=[box_button(target.platform_user_id, box_id)])
