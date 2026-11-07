"""Text rendering. Plain text with emoji only, so player names can never break formatting."""

from __future__ import annotations

from ..game.data.classes import CLASSES, CharacterClass
from ..game.data.items import SLOT_LABELS
from ..game.data.races import RACES, Race
from ..game.data.stats import Stats
from ..game.models import Player
from ..shared.text import bar, duration, fa

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


def activity_result(name: str, result) -> str:  # noqa: ANN001 - ActivityResult
    rolled, player = result.rolled, result.player
    gains = []
    if rolled.gold:
        gains.append(f"🪙 +{fa(rolled.gold)} سکه")
    if rolled.crystal:
        gains.append(f"💎 +{fa(rolled.crystal)} کریستال")
    if rolled.xp:
        gains.append(f"⭐ +{fa(rolled.xp)} تجربه")
    lines = [result.activity.intro.format(name=name), rolled.outcome.text.format(name=name)]
    if gains:
        lines.append(" · ".join(gains))
    if result.items:
        lines.append("📦 " + "، ".join(f"{label} ×{fa(qty)}" for label, qty in result.items))
    if result.level_up:
        lines.append(f"🎉 سطحت بالا رفت! حالا سطح {fa(result.level_up.new_level)} هستی.")
    lines.append(f"⚡ انرژی: {fa(player.energy)}")
    return "\n".join(lines)


def shop_listing() -> str:
    from ..game.services.shop import shop_items

    groups: dict[str, list[str]] = {}
    for item in shop_items():
        title = "🧪 مصرفی‌ها" if item.kind.value == "consumable" else "⚔️ تجهیزات"
        bonus = f" {item.stats.short()}" if item.is_gear else ""
        level = f" (سطح {fa(item.level_req)})" if item.level_req > 1 else ""
        groups.setdefault(title, []).append(f"• {item.label}{bonus}{level} — {fa(item.buy)} 🪙")
    blocks = [f"{title}\n" + "\n".join(lines) for title, lines in groups.items()]
    footer = "خرید: «خرید <نام> [تعداد]»\nفروش: «فروش <نام> [تعداد]» یا «فروش #شماره»"
    return "🛒 فروشگاه\n" + LINE + "\n" + "\n\n".join(blocks) + "\n" + LINE + "\n" + footer


def upgrade_quote(piece, quote) -> str:  # noqa: ANN001
    from ..game.data.items import get_item

    mats = "، ".join(f"{get_item(i).label} ×{fa(q)}" for i, q in quote.materials.items())
    return (
        f"🔨 ارتقای {piece.label} به +{fa(quote.next_level)}\n"
        f"💰 هزینه: {fa(quote.gold)} 🪙\n"
        f"📦 مواد: {mats}\n"
        f"🎯 شانس موفقیت: {fa(round(quote.chance * 100))}٪\n"
        "اگر ارتقا شکست بخورد مواد از بین می‌رود، اما تجهیزاتت سالم می‌ماند."
    )


def upgrade_result(result) -> str:  # noqa: ANN001 - UpgradeResult
    if result.success:
        return f"✅ ارتقا موفق بود! {result.piece.label}\n{result.piece.stats.short()}"
    return f"💥 ارتقا شکست خورد؛ مواد از بین رفت ولی {result.piece.label} سالم ماند."


def market_listings(listings, item, title: str | None = None) -> str:  # noqa: ANN001
    head = title or ("🏪 بازار" + (f" · {item.label}" if item else ""))
    if not listings:
        return f"{head}\n{LINE}\nآگهی فعالی نیست."
    lines = [head, LINE]
    for lst in listings:
        seller = f" — {lst.seller_name}" if lst.seller_name else ""
        lines.append(f"🔖{fa(lst.id)}  {lst.label}  {fa(lst.price)} 🪙{seller}")
    lines += [LINE, "خرید: «بخر <شماره>»   عرضه: «عرضه ...»   لغو: «لغو <شماره>»"]
    return "\n".join(lines)


def ranking(board) -> str:  # noqa: ANN001 - Board
    if not board.entries:
        return f"{board.title}\n{LINE}\nهنوز کسی در این جدول نیست."
    medals = ["🥇", "🥈", "🥉"]
    lines = [board.title, LINE]
    for index, entry in enumerate(board.entries):
        place = medals[index] if index < 3 else f"{fa(index + 1)}."
        lines.append(f"{place} {entry.badge} {entry.name} (سطح {fa(entry.level)}) — {fa(entry.value)} {board.unit}")
    if board.my_position:
        lines += [LINE, f"📍 رتبه تو: {fa(board.my_position)}"]
    return "\n".join(lines)


def chest_list(owned: dict[str, int]) -> str:
    from ..game.data.chests import CHESTS
    from ..game.data.items import get_item

    lines = ["🎁 صندوقچه‌ها", LINE]
    for chest in CHESTS.values():
        item = get_item(chest.item_id)
        icon = "🪙" if chest.price and chest.price[0] == "gold" else "💎"
        price = f"{fa(chest.price[1])} {icon}" if chest.price else "—"
        lines.append(f"{item.label} — قیمت: {price} — داری: {fa(owned.get(item.id, 0))}")
    lines += [LINE, "خرید: «خرید صندوقچه جادویی»", "باز کردن: «باز کردن صندوقچه جادویی»", "شانس محتویات: «شانس صندوقچه جادویی»"]
    return "\n".join(lines)


def chest_odds(item, odds) -> str:  # noqa: ANN001
    from ..game.data.items import get_item

    lines = [f"🎲 شانس محتویات {item.label}", LINE]
    for prize, share in sorted(odds, key=lambda x: -x[1]):
        parts = []
        if prize.gold[1]:
            parts.append(f"🪙 {fa(prize.gold[0])} تا {fa(prize.gold[1])} سکه")
        if prize.crystal[1]:
            parts.append(f"💎 {fa(prize.crystal[0])} تا {fa(prize.crystal[1])} کریستال")
        if prize.item_id:
            qty = f" ×{fa(prize.qty[0])}" + (f" تا {fa(prize.qty[1])}" if prize.qty[1] > prize.qty[0] else "")
            parts.append(get_item(prize.item_id).label + qty)
        lines.append(f"{share * 100:.1f}٪  ".translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")) + " + ".join(parts))
    lines += [LINE, "این درصدها همان شانس واقعی ربات است."]
    return "\n".join(lines)


def chest_opened(name: str, opened) -> str:  # noqa: ANN001 - Opened
    got = []
    if opened.gold:
        got.append(f"🪙 {fa(opened.gold)} سکه")
    if opened.crystal:
        got.append(f"💎 {fa(opened.crystal)} کریستال")
    if opened.item:
        got.append(f"{opened.item.label} ×{fa(opened.qty)} ({opened.item.rarity_label})")
    return f"🎁 {name} {opened.chest.label} را باز کرد...\n✨ " + " + ".join(got)


def pack_description(pack) -> str:  # noqa: ANN001 - Pack
    from ..game.data.items import get_item

    parts = []
    if pack.gold:
        parts.append(f"{fa(pack.gold)} سکه")
    if pack.crystal:
        parts.append(f"{fa(pack.crystal)} کریستال")
    parts += [f"{get_item(i).name} ×{fa(q)}" for i, q in pack.items.items()]
    return "شامل: " + " + ".join(parts)


def premium_shop(payments_enabled: bool) -> str:
    from ..game.data.chests import CHESTS
    from ..game.data.items import get_item
    from ..game.data.packs import PACKS, SECTIONS

    lines = ["💎 فروشگاه ویژه", LINE]
    if payments_enabled:
        for section, title in SECTIONS.items():
            lines.append(title)
            for pack in (p for p in PACKS.values() if p.section == section):
                lines.append(f"• {pack.label} — {fa(pack.price_toman)} تومان")
                if section == "bundles":
                    lines.append(f"   {pack_description(pack)}")
            lines.append("")
    else:
        lines += ["خرید با پول واقعی فعلاً غیرفعال است.", ""]
    lines.append("🎁 صندوقچه‌ها (با کریستال)")
    for chest in CHESTS.values():
        if chest.price and chest.price[0] == "crystal":
            lines.append(f"• {get_item(chest.item_id).label} — {fa(chest.price[1])} 💎")
    lines += [
        "شانس دقیق محتویات هر صندوقچه: «شانس صندوقچه جادویی»",
        LINE,
        "💳 پرداخت با کیف پول بله انجام می‌شود و اطلاعات کارت شما ذخیره نمی‌شود.",
        "⚠️ کاربران زیر ۱۸ سال فقط با اطلاع و اجازه والدین خرید کنند.",
        "همه‌چیز را می‌شود بدون پرداخت هم با بازی به‌دست آورد.",
    ]
    return "\n".join(lines)


def delivery(order) -> str:  # noqa: ANN001 - Order
    return (
        f"✅ پرداخت موفق بود! سفارش {fa(order.id)}\n"
        f"{order.pack.label} به حسابت اضافه شد.\n{pack_description(order.pack)}\n"
        "ممنون که از بازی حمایت می‌کنی 💛"
    )


def duel_invite(challenger, target, seconds: int) -> str:  # noqa: ANN001 - Player
    return (
        "⚔️ درخواست مبارزه!\n\n"
        f"{challenger.title} شما را به دوئل دعوت کرده است.\n"
        f"{challenger.race.emoji} {challenger.race.name} · سطح {fa(challenger.level)}\n"
        f"🏆 پیروزی: {fa(challenger.wins)} · 💀 شکست: {fa(challenger.losses)}\n\n"
        f"{target.title}، قبول می‌کنی؟ (تا {duration(seconds)} فرصت داری)"
    )


def _hp_line(f) -> str:  # noqa: ANN001 - Fighter
    return f"{f.emoji} {f.name}  ❤️ {fa(max(f.hp, 0))}/{fa(f.max_hp)}  {bar(f.hp, f.max_hp, 8)}"


def duel_status(battle, lines: list[str], turn_seconds: int) -> str:  # noqa: ANN001 - Battle
    a, b = battle.fighters
    parts = ["⚔️ دوئل", LINE, _hp_line(a), _hp_line(b), LINE]
    parts += lines
    if not battle.finished:
        parts += [LINE, f"🎯 نوبت {battle.current.name} | دور {fa(battle.round)} از {fa(battle.max_rounds)}",
                  f"⏳ {duration(turn_seconds)} فرصت برای انتخاب"]
    return "\n".join(parts)


def duel_result(update) -> str:  # noqa: ANN001 - DuelUpdate
    battle = update.battle
    a, b = battle.fighters
    parts = ["⚔️ پایان دوئل", LINE, _hp_line(a), _hp_line(b), LINE, *update.lines, LINE]
    if battle.winner is None:
        parts.append("🤝 مساوی شد!")
    else:
        parts.append(f"🏆 برنده: {battle.fighters[battle.winner].name}")
    for fighter in battle.fighters:
        payout = update.payouts.get(fighter.player_id)
        if payout is None:
            continue
        gains = []
        if payout.gold:
            gains.append(f"🪙 +{fa(payout.gold)}")
        if payout.xp:
            gains.append(f"⭐ +{fa(payout.xp)}")
        if payout.level_up:
            gains.append(f"🎉 سطح {fa(payout.level_up.new_level)}")
        parts.append(f"{fighter.name}: " + (" · ".join(gains) if gains else "بدون پاداش (سقف روزانه)"))
    return "\n".join(parts)


def hunt_result(name: str, r) -> str:  # noqa: ANN001 - HuntResult
    lines = [
        f"{r.monster.emoji} {name} در حین شکار با «{r.monster.name}» روبه‌رو شد!",
        f"⚔️ نبرد {fa(r.rounds)} دور طول کشید.",
    ]
    if r.won:
        lines.append("🏆 پیروز شدی!")
    else:
        lines.append("💀 شکست خوردی و با زخم‌هایت فرار کردی (چیزی از دست ندادی).")
    lines.append(f"❤️ جان باقی‌مانده: {fa(r.hero_hp)} / {fa(r.hero_max_hp)}")
    gains = []
    if r.gold:
        gains.append(f"🪙 +{fa(r.gold)} سکه")
    if r.xp:
        gains.append(f"⭐ +{fa(r.xp)} تجربه")
    if gains:
        lines.append(" · ".join(gains))
    if r.items:
        lines.append("📦 " + "، ".join(f"{label} ×{fa(q)}" for label, q in r.items))
    if r.level_up:
        lines.append(f"🎉 سطحت بالا رفت! حالا سطح {fa(r.level_up.new_level)} هستی.")
    lines.append(f"⚡ انرژی: {fa(r.player.energy)}")
    return "\n".join(lines)


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
