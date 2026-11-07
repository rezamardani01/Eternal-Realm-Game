"""Text rendering. Plain text with emoji only, so player names can never break formatting."""

from __future__ import annotations

from ..game.data.classes import CLASSES, CharacterClass
from ..game.data.items import SLOT_LABELS
from ..game.data.races import RACES, Race
from ..game.data.stats import Stats
from ..game.models import Player
from ..shared.text import bar, fa

LINE = "━━━━━━━━━━━━━━"


def race_list() -> str:
    return "\n\n".join(f"{r.emoji} {r.name}\n{r.description}" for r in RACES.values())


def class_list() -> str:
    return "\n\n".join(
        f"{c.emoji} {c.name}\n{c.description}\nمهارت: {c.skill.emoji} {c.skill.name}"
        for c in CLASSES.values()
    )


def profile(player: Player, stats: Stats, xp_needed: int, max_energy: int) -> str:
    race, cls = player.race, player.char_class
    xp = fa(player.xp) + " / " + fa(xp_needed)
    return "\n".join(
        [
            f"{cls.emoji} {player.name} | سطح {fa(player.level)}",
            f"{race.emoji} {race.name} · {cls.name}",
            LINE,
            f"❤️ سلامتی: {fa(stats.hp)}",
            f"⚡ انرژی: {fa(player.energy)} / {fa(max_energy)} {bar(player.energy, max_energy, 8)}",
            f"⚔️ حمله: {fa(stats.atk)}   🛡️ دفاع: {fa(stats.defense)}",
            f"✨ جادو: {fa(stats.magic)}   💨 سرعت: {fa(stats.speed)}   🍀 شانس: {fa(stats.luck)}",
            f"⭐ تجربه: {xp} {bar(player.xp, xp_needed, 8)}",
            LINE,
            f"🪙 سکه: {fa(player.gold)}   💎 کریستال: {fa(player.crystal)}",
            f"🏆 پیروزی: {fa(player.wins)}   💀 شکست: {fa(player.losses)}",
        ]
    )


def welcome() -> str:
    return (
        "🏰 به قلمرو جاودان خوش آمدی!\n\n"
        "در سرزمین میتوریا، جوهر جادو پراکنده شده و ماجراجویان برای یافتن آن با هم رقابت می‌کنند. "
        "اینجا شخصیتت را می‌سازی و بعد با ربات در گروه‌ها ماهیگیری، معدن‌کاری، شکار و دوئل می‌کنی.\n\n"
        "✍️ اول یک نام برای شخصیتت بفرست (۲ تا ۱۶ حرف):"
    )


def pick_race(name: str) -> str:
    return f"👤 {name}\n\n🧬 نژاد شخصیتت را انتخاب کن:\n\n{race_list()}"


def pick_class(name: str, race: Race) -> str:
    return f"👤 {name} · {race.emoji} {race.name}\n\n⚔️ کلاس مبارزه‌ات را انتخاب کن:\n\n{class_list()}"


def created(player: Player, bot_username: str) -> str:
    return (
        f"🎉 شخصیت «{player.name}» ساخته شد!\n"
        f"{player.race.emoji} {player.race.name} · {player.char_class.emoji} {player.char_class.name}\n\n"
        f"🎁 هدیه شروع: {fa(player.gold)} سکه\n\n"
        "📌 حالا ربات را به گروهت اضافه کن و آنجا بنویس «راهنما» تا دستورها را ببینی.\n"
        "شخصیت، سکه و تجهیزاتت در همه گروه‌ها یکسان است."
    )


def pick_summary(race: Race, cls: CharacterClass) -> str:
    return f"{race.emoji} {race.name} · {cls.emoji} {cls.name}"


def command_help(registry, in_group: bool) -> str:  # noqa: ANN001
    """Help generated from the registry, so it always matches the real commands."""
    categories: dict[str, list[str]] = {}
    for cmd in registry.all():
        if cmd.name == "start" or (in_group and not cmd.group) or (not in_group and not cmd.private):
            continue
        persian = [a for a in cmd.aliases if not a.isascii()]
        label = persian[0] if persian else "/" + cmd.aliases[0]
        categories.setdefault(cmd.category, []).append(f"• {label}: {cmd.description}")
    blocks = [f"{title}\n" + "\n".join(lines) for title, lines in categories.items()]
    return "📖 دستورهای قلمرو جاودان\n\n" + "\n\n".join(blocks)


def help_text() -> str:
    return (
        "❓ راهنمای قلمرو جاودان\n\n"
        "بازی اصلی داخل گروه‌هاست. ربات را به گروهت اضافه کن و این‌ها را بنویس:\n"
        "• پروفایل: مشخصات شخصیت (روی پیام کسی ریپلای کنی، مشخصات او را می‌بینی)\n"
        "• راهنما: فهرست کامل دستورها\n\n"
        "این منو برای مدیریت شخصیت، تجهیزات و فروشگاه است."
    )


def inventory(owner: str, view) -> str:  # noqa: ANN001 - InventoryView
    lines = [f"🎒 کوله‌پشتی {owner}", LINE]
    if view.stacks:
        lines.append("📦 آیتم‌ها")
        lines += [f"• {item.label} ×{fa(qty)}" for item, qty in view.stacks]
    else:
        lines.append("📦 آیتمی نداری.")
    lines.append(LINE)
    if view.gear:
        lines.append("⚔️ تجهیزات (پوشیدن: «تجهیز شماره»)")
        for piece in view.gear:
            mark = " ✅" if piece.slot else ""
            lines.append(
                f"#{fa(piece.id)} {piece.label} {piece.item.rarity_label}{mark}\n    {piece.stats.short()}"
            )
    else:
        lines.append("⚔️ تجهیزاتی نداری.")
    return "\n".join(lines)


def equipment(owner: str, view, stats: Stats) -> str:  # noqa: ANN001
    worn = {p.slot: p for p in view.gear if p.slot}
    lines = [f"🧰 تجهیزات {owner}", LINE]
    for slot, label in SLOT_LABELS.items():
        piece = worn.get(slot)
        lines.append(f"{label}: {piece.label + ' ' + piece.stats.short() if piece else '—'}")
    lines += [LINE, f"قدرت کل: {stats.short()}"]
    return "\n".join(lines)
