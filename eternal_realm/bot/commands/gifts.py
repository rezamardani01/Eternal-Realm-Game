"""The realm owner's gifts: reply to a player's message and write «اهدا ...».

    اهدا بلیط طلایی      اهدا اشتراک 30      اهدا سکه 100      اهدا کریستال 100      اهدا حیوان روباه

The reply shows what was given and the receiver gets a private message with the details.
"""

from __future__ import annotations

import contextlib

from baleropy.exceptions import BaleAPIError

from ...game.data.pets import PETS
from ...shared.errors import GameError
from ...shared.text import bold, duration, fa, to_int
from .context import CommandContext
from .registry import command

_OPTIONS = {"needs_player": False, "private": False, "always_on": True, "takes_args": True, "points": 0,
            "category": "🛠️ مدیریت"}


def _owner(ctx: CommandContext) -> bool:
    return ctx.user.id == ctx.services.ctx.settings.owner_id


async def _target(ctx: CommandContext):  # noqa: ANN202
    target = await ctx.replied_player()
    if target is None:
        raise GameError("روی پیام همان بازیکن ریپلای کنید و دستور اهدا را بنویسید.")
    return target


async def _announce(ctx: CommandContext, target, what: str, detail: str = "") -> None:  # noqa: ANN001
    await ctx.reply(
        f"🎁 {bold('هدیه از مالک قلمرو')}\n\n"
        f"فرمانده {ctx.who(target)} ، مالک قلمرو چیزی به شما اهدا کرد:\n\n"
        f"{what}" + (f"\n\n{detail}" if detail else "")
    )
    dm = (
        f"🎁 {bold('هدیه‌ای از مالک قلمرو رسید!')}\n\n"
        f"هدیه: {what}\n" + (f"{detail}\n" if detail else "") + "\nاز طرف مالک قلمرو جاودان 💛"
    )
    with contextlib.suppress(BaleAPIError):
        await ctx.bot.send_message(target.platform_user_id, dm)


def _amount(ctx: CommandContext, low: int = 1, high: int = 10_000_000) -> int:
    value = to_int(ctx.args[0]) if ctx.args else None
    if value is None or not low <= value <= high:
        raise GameError(f"مقدار را درست بنویسید؛ عددی بین {fa(low)} تا {fa(high)}. مثال: «اهدا سکه 100»")
    return value


@command("gift_ticket", ["اهدا بلیط طلایی", "اهدا بلیط"], "(مالک) اهدای بلیط طلایی این فصل", **_OPTIONS)
async def gift_ticket(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    target = await _target(ctx)
    changed = await ctx.services.admin.grant_ticket(ctx.user.id, target.id, True)
    if not changed:
        raise GameError(f"{target.name} بلیط طلایی این فصل را از قبل دارد.")
    await _announce(ctx, target, "🎟️ بلیط طلایی مسیر قهرمانی (این فصل)",
                    "جایزه‌های طلایی همه‌ی مرحله‌ها باز شد؛ از «قهرمان من ← مسیر قهرمانی» بگیریدشان.")


@command("gift_vip", ["اهدا اشتراک", "اهدا vip"], "(مالک) اهدای اشتراک VIP: اهدا اشتراک 30", **_OPTIONS)
async def gift_vip(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    days = _amount(ctx, 1, 3650)
    target = await _target(ctx)
    until = await ctx.services.admin.set_vip(ctx.user.id, target.id, days)
    left = until - ctx.services.ctx.now()
    await _announce(ctx, target, f"💠 {fa(days)} روز اشتراک VIP", f"اشتراک شما {duration(left)} دیگر فعال است.")


@command("gift_gold", ["اهدا سکه"], "(مالک) اهدای سکه: اهدا سکه 100", **_OPTIONS)
async def gift_gold(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    amount = _amount(ctx)
    target = await _target(ctx)
    await ctx.services.admin.give_currency_id(ctx.user.id, target.id, gold=amount)
    await _announce(ctx, target, f"🪙 {fa(amount)} سکه")


@command("gift_crystal", ["اهدا کریستال"], "(مالک) اهدای کریستال: اهدا کریستال 100", **_OPTIONS)
async def gift_crystal(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    amount = _amount(ctx, 1, 100_000)
    target = await _target(ctx)
    await ctx.services.admin.give_currency_id(ctx.user.id, target.id, crystal=amount)
    await _announce(ctx, target, f"💎 {fa(amount)} کریستال")


@command("gift_pet", ["اهدا حیوان", "اهدا پت"], "(مالک) اهدای حیوان خانگی: اهدا حیوان روباه", **_OPTIONS)
async def gift_pet(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    wanted = " ".join(ctx.args).strip()
    pet = next((p for p in PETS if wanted and (wanted in p.name or p.id == wanted.lower())), None)
    if pet is None:
        raise GameError("نام حیوان را بنویسید. این‌ها هست: " + "، ".join(p.name for p in PETS))
    target = await _target(ctx)
    if not await ctx.services.admin.grant_pet(ctx.user.id, target.id, pet.id, True):
        raise GameError(f"{target.name} این حیوان خانگی را از قبل دارد.")
    await _announce(ctx, target, f"{pet.emoji} حیوان خانگی {pet.name}", "از «حیوان خانگی» همراه خودش کنید.")
