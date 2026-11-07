"""Group administrators decide which parts of the game are active in their group."""

from __future__ import annotations

from ...shared.errors import GameError
from .context import CommandContext
from .registry import REGISTRY, Command, command


async def _require_admin(ctx: CommandContext) -> None:
    if ctx.services.ctx.settings.is_admin(ctx.user.id):
        return
    member = await ctx.bot.get_chat_member(ctx.chat_id, ctx.user.id)
    if not member.is_admin:
        raise GameError("این فرمان مخصوص مدیران گروه است، فرمانده. از یکی از مدیران بخواهید آن را بنویسد.")


def _toggleable(word: str) -> Command:
    found = REGISTRY.find_by_alias(word)
    if found is None or not found.toggleable:
        names = "، ".join(
            next((a for a in c.aliases if not a.isascii()), c.name)
            for c in REGISTRY.all() if c.toggleable
        )
        raise GameError(f"این یکی را نمی‌شود خاموش کرد. فعالیت‌هایی که می‌توانید تنظیم کنید: {names}")
    return found


async def _switch(ctx: CommandContext, enabled: bool) -> None:
    word = " ".join(ctx.args)
    is_game = word in ("بازی", "ربات", "game")
    if not is_game and REGISTRY.find_by_alias(word) is None:
        return  # ordinary chat such as «فعال باش»: stay quiet
    await _require_admin(ctx)
    if is_game:
        await ctx.services.groups.set_enabled(ctx.chat_id, enabled)
        await ctx.reply("✅ دروازه‌های قلمرو در این گروه باز شد! ماجراجویان می‌توانند بازی کنند." if enabled else "⏸️ دروازه‌های قلمرو در این گروه بسته شد. با «فعال بازی» دوباره باز می‌شود.")
        return
    cmd = _toggleable(word)
    await ctx.services.groups.set_command(ctx.chat_id, cmd.name, enabled)
    state = "فعال شد ✅" if enabled else "غیرفعال شد ⛔"
    await ctx.reply(f"فرمان مدیر اجرا شد: «{word}» در این گروه {state}")


@command(
    "group_on", ["فعال", "روشن"], "(مدیر گروه) فعال کردن یک فعالیت یا کل بازی: فعال <نام>",
    category="⚙️ مدیریت گروه", needs_player=False, private=False, always_on=True, takes_args=True, points=0,
)
async def group_on(ctx: CommandContext) -> None:
    await _switch(ctx, True)


@command(
    "group_off", ["غیرفعال", "خاموش"], "(مدیر گروه) غیرفعال کردن یک فعالیت یا کل بازی: غیرفعال <نام>",
    category="⚙️ مدیریت گروه", needs_player=False, private=False, always_on=True, takes_args=True, points=0,
)
async def group_off(ctx: CommandContext) -> None:
    await _switch(ctx, False)


@command(
    "group_settings", ["تنظیمات گروه", "وضعیت گروه"], "نمایش وضعیت بازی در این گروه",
    category="⚙️ مدیریت گروه", needs_player=False, private=False, always_on=True, points=0,
)
async def group_settings(ctx: CommandContext) -> None:
    info = await ctx.services.groups.get(ctx.chat_id)
    assert info is not None
    off = [
        next((a for a in c.aliases if not a.isascii()), c.name)
        for c in REGISTRY.all() if c.name in info.disabled_commands
    ]
    lines = [
        "⚙️ دفتر مدیریت قلمرو در این گروه",
        f"دروازه‌ی قلمرو: {'✅ باز' if info.enabled else '⏸️ بسته'}",
        "فعالیت‌های بسته: " + ("، ".join(off) if off else "هیچ‌کدام"),
        "مدیران با «غیرفعال ماهیگیری» و «فعال ماهیگیری» می‌توانند هر فعالیت را ببندند و باز کنند.",
    ]
    await ctx.reply("\n".join(lines))
