"""Commands only the realm owner can use, with no limits: items, levels, summoning events and bosses.

Gifts (``اهدا ...``) are in ``gifts.py``. Every command works on the player whose message is replied to, or on the
owner's own hero without a reply. Anyone else who writes them is ignored. «دستورات مالک» lists them all.
"""

from __future__ import annotations

from ...game.data.items import ITEMS, get_item
from ...game.data.packs import PACKS
from ...game.services.invites import GIFT_PACKS
from ...game.data.pets import PETS
from ...game.services.events import EventAction
from ...shared.errors import GameError
from ...shared.text import bold, duration, fa, to_int
from .. import events as events_ui
from ..invite_panel import box_button, notify_box
from .context import CommandContext
from .gifts import _OPTIONS, _announce, _owner, _target
from .registry import command

#: word -> event kind the owner may summon at any time, even while something else is running
SUMMON_WORDS = {
    "دوره گرد": "merchant", "دوره‌گرد": "merchant", "تاجر": "merchant",
    "صندوقچه": "mystery_chest", "صندوقچه مخفی": "hidden_chest", "صندوقچه‌ی مخفی": "hidden_chest",
    "تهاجم": "invasion", "شهاب": "meteor", "شهاب‌سنگ": "meteor", "شهاب سنگ": "meteor",
    "ستاره تجربه": "double_xp", "تجربه دوبرابر": "double_xp", "باس مخفی": "hidden_boss",
    "باران سکه": "gold_rain", "چشمه": "spring", "چرخ شانس": "wheel", "تخم اژدها": "egg", "تخم": "egg",
    "معما": "riddle", "کاشی": "tiles", "کاشی شانس": "tiles", "قرعه کشی": "raffle", "قرعه‌کشی": "raffle",
}

OWNER_COMMANDS = """\
🎁 اهدا (روی پیام یک بازیکن ریپلای کنید؛ بدون ریپلای برای خودتان انجام می‌شود)
• اهدا مسیر قهرمانی — بلیط طلایی این فصل
• اهدا اشتراک 30 — ۳۰ روز VIP
• اهدا سکه 3000 · اهدا کریستال 200
• اهدا ققنوس · اهدا حیوان عقاب — حیوان خانگی با نام
• اهدا سنگ آهن 399 — هر آیتم با نام و تعداد
• اهدا بسته کوچک | متوسط | بزرگ | ماجراجو — صندوق با دکمه‌ی باز کردن
• اهدا برگه تغییر نام | نژاد | کلاس
• اهدا بوست 24 — بوست دو برابر (ساعت)
• اهدا سطح 40 — تعیین سطح
• اهدا انرژی — پر کردن انرژی
• اهدا ریست — پاک شدن همه‌ی زمان‌های انتظار

🎲 احضار (در هر گروه، بدون محدودیت و حتی وقتی رویداد دیگری هست)
• احضار دوره گرد · احضار صندوقچه · احضار صندوقچه مخفی
• احضار تهاجم · احضار شهاب · احضار ستاره تجربه · احضار باس مخفی
• احضار باران سکه · احضار چشمه · احضار چرخ شانس · احضار تخم اژدها
• احضار معما · احضار کاشی · احضار قرعه کشی
• احضار باس — بدون هزینه، سطح و فاصله‌ی زمانی

⚔️ مبارزه و ماجراجویی
• دوئل: سقف روزانه‌ی هر جفت و سقف پاداش برای مالک برداشته شده است
• انرژی و زمان انتظار شکار، ماهیگیری و... برای مالک صفر است

🛠️ پنل مدیریت — پنل شیشه‌ای: آمار، بازیکنان، گروه‌ها، خاندان‌ها، فروش، پیام همگانی، عضویت اجباری

📋 دستورات مالک — همین فهرست"""


def _find_pet(words: list[str]):  # noqa: ANN202
    wanted = " ".join(words).strip().replace("‌", " ")
    if not wanted:
        return None
    for pet in PETS:
        if pet.id == wanted.lower() or pet.name.replace("‌", " ") == wanted:
            return pet
    for pet in PETS:
        if wanted in pet.name.replace("‌", " "):
            return pet
    return None


def _find_item(words: list[str]):  # noqa: ANN202
    wanted = " ".join(words).strip().replace("‌", " ")
    for item in ITEMS.values():
        if wanted and (item.id == wanted.lower() or item.name.replace("‌", " ") == wanted):
            return item
    for item in ITEMS.values():
        if wanted and wanted in item.name.replace("‌", " "):
            return item
    return None


@command("gift_item", ["اهدا"], "(مالک) اهدای هر آیتم: اهدا سنگ آهن 399", **_OPTIONS)
async def gift_item(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    args = list(ctx.args)
    qty = 1
    if args and (n := to_int(args[-1])) is not None:
        qty, args = n, args[:-1]
    pet = _find_pet(args) if qty == 1 else None  # «اهدا ققنوس»: a companion pet by its name
    if pet is not None:
        target = await _target(ctx)
        if not await ctx.services.admin.grant_pet(ctx.user.id, target.id, pet.id, True):
            raise GameError(f"{target.name} این حیوان خانگی را از قبل دارد.")
        await _announce(ctx, target, f"{pet.emoji} حیوان خانگی {pet.name}", "از «حیوان خانگی» همراه خودش کنید.")
        return
    item = _find_item(args)
    if item is None:
        raise GameError("چیزی با این نام پیدا نشد. مثال: «اهدا سنگ آهن 399»، «اهدا صندوقچه جادویی 2» یا «اهدا ققنوس»")
    target = await _target(ctx)
    await ctx.services.admin.give_item_id(ctx.user.id, target.id, item, qty)
    await _announce(ctx, target, f"{item.label} ×{fa(qty)}")


@command("gift_pack", ["اهدا بسته", "اهدا بست"], "(مالک) اهدای صندوق: اهدا بسته کوچک | متوسط | بزرگ | ماجراجو", **_OPTIONS)
async def gift_pack(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    name = " ".join(ctx.args).strip()
    pack_id = GIFT_PACKS.get(name)
    if pack_id is None:
        raise GameError("کدام بسته؟ بنویسید: اهدا بسته کوچک، اهدا بسته متوسط، اهدا بسته بزرگ یا اهدا بسته ماجراجو")
    target = await _target(ctx)
    pack = PACKS[pack_id]
    box_id = await ctx.services.invites.give_box(ctx.user.id, target.id, pack_id)
    await ctx.reply(
        f"📦 {bold('صندوق هدیه رسید!')}\n\n"
        f"فرمانده {ctx.who(target)} ، مالک قلمرو یک صندوق به شما اهدا کرد:\n\n"
        f"🎁 {pack.label}\n\n"
        "👇 برای دیدن محتوایش بازش کنید",
        buttons=[box_button(target.platform_user_id, box_id)],
    )
    await notify_box(ctx.bot, target, box_id, pack.label)


def _ticket_command(name: str, alias: str, item_id: str, icon: str, title: str, use: str) -> None:
    @command(name, [alias], f"(مالک) اهدای {title}", **_OPTIONS)
    async def handler(ctx: CommandContext) -> None:
        if not _owner(ctx):
            return
        qty = to_int(ctx.args[0]) if ctx.args else 1
        if qty is None or not 1 <= qty <= 100:
            raise GameError("تعداد را درست بنویسید؛ مثلاً «%s 2»" % alias)
        target = await _target(ctx)
        await ctx.services.admin.give_item_id(ctx.user.id, target.id, get_item(item_id), qty)
        await _announce(ctx, target, f"{icon} {title}" + (f" ×{fa(qty)}" if qty > 1 else ""), use)


_ticket_command("gift_rename_ticket", "اهدا برگه تغییر نام", "rename_ticket", "🏷️", "برگه‌ی تغییر نام",
                "از «قهرمان من ← ارتقای قهرمان ← خدمات» مصرفش کنید.")
_ticket_command("gift_race_ticket", "اهدا برگه تغییر نژاد", "race_ticket", "🧬", "برگه‌ی تغییر نژاد",
                "از «قهرمان من ← ارتقای قهرمان ← خدمات» مصرفش کنید.")
_ticket_command("gift_class_ticket", "اهدا برگه تغییر کلاس", "class_ticket", "⚔️", "برگه‌ی تغییر کلاس",
                "از «قهرمان من ← ارتقای قهرمان ← خدمات» مصرفش کنید.")


@command("gift_boost", ["اهدا بوست"], "(مالک) اهدای بوست دو برابر: اهدا بوست 24", **_OPTIONS)
async def gift_boost(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    hours = to_int(ctx.args[0]) if ctx.args else None
    if hours is None:
        raise GameError("ساعت را بنویسید؛ مثال: «اهدا بوست 24»")
    target = await _target(ctx)
    until = await ctx.services.admin.give_boost(ctx.user.id, target.id, hours)
    left = until - ctx.services.ctx.now()
    await _announce(ctx, target, f"🚀 {fa(hours)} ساعت بوست دو برابر", f"بوست شما {duration(left)} دیگر فعال است؛ سکه، تجربه و غنیمت‌ها دو برابر می‌شود.")


@command("gift_level", ["اهدا سطح"], "(مالک) تعیین سطح: اهدا سطح 40", **_OPTIONS)
async def gift_level(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    level = to_int(ctx.args[0]) if ctx.args else None
    if level is None:
        raise GameError("سطح را بنویسید؛ مثال: «اهدا سطح 40»")
    target = await _target(ctx)
    await ctx.services.admin.set_level_id(ctx.user.id, target.id, level)
    await _announce(ctx, target, f"⭐ سطح {fa(level)}")


@command("gift_energy", ["اهدا انرژی"], "(مالک) پر کردن انرژی", **_OPTIONS)
async def gift_energy(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    target = await _target(ctx)
    await ctx.services.admin.refill_energy(ctx.user.id, target.id)
    await _announce(ctx, target, "⚡ انرژی کامل")


@command("gift_reset", ["اهدا ریست"], "(مالک) پاک کردن زمان‌های انتظار", **_OPTIONS)
async def gift_reset(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    target = await _target(ctx)
    await ctx.services.admin.reset_cooldowns(ctx.user.id, target.id)
    await _announce(ctx, target, "⏱️ همه‌ی زمان‌های انتظار پاک شد")


@command("owner_summon", ["احضار"], "(مالک) احضار رویداد: احضار دوره گرد، احضار تهاجم، احضار شهاب ...", **_OPTIONS)
async def owner_summon(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    kind = SUMMON_WORDS.get(" ".join(ctx.args).strip())
    if kind is None:
        raise GameError("چه چیزی؟ این‌ها را بنویسید: " + "، ".join(f"احضار {w}" for w in dict.fromkeys(SUMMON_WORDS)))
    view = await ctx.services.events.spawn(ctx.chat_id, kind, force=True)
    if view is None:
        raise GameError("الان نمی‌شود این رویداد را این‌جا ساخت (مثلاً باس زنده است یا کسی در گروه فعال نیست).")
    await events_ui.announce(ctx.bot, ctx.services, EventAction("spawned", view))


@command("owner_commands", ["دستورات مالک", "لیست دستورات مالک"], "(مالک) فهرست دستورهای مالک", **_OPTIONS)
async def owner_commands(ctx: CommandContext) -> None:
    if not _owner(ctx):
        return
    await ctx.reply(f"🛠️ {bold('دستورات مالک قلمرو')}\n\n{OWNER_COMMANDS}")
