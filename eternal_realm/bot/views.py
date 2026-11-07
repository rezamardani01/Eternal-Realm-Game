"""Text rendering.

Rules of the house: every message starts with exactly ONE emoji, titles and key numbers are
bold (with a space around the ``**`` markers, as Bale requires), each stat sits on its own
line, and the voice is a friendly epic storyteller in simple formal Persian.
"""

from __future__ import annotations

from ..game.data.classes import CLASSES
from ..game.data.races import RACES, Race
from ..game.data.stats import Stats
from ..game.models import Player
from ..shared.text import bar, bold, duration, fa

LINE = "━━━━━━━━━━━━"


# --- first steps -------------------------------------------------------------------------------
def welcome() -> str:
    return (
        "🏰 درود بر شما، ماجراجو!\n"
        f"به {bold('قلمرو جاودان')} خوش آمدید.\n\n"
        "مُهر باستانی میتوریا شکسته و هیولاها بیدار شده‌اند. "
        "فقط قهرمانی مثل شما می‌تواند سرزمین را نجات دهد!\n\n"
        f"✍️ {bold('نام قهرمان')} خود را بنویسید (۲ تا ۱۶ حرف):"
    )


def pick_race() -> str:
    lines = [f"🧬 {bold('نژاد')} خود را انتخاب کنید:", ""]
    lines += [f"{r.emoji} {r.name} — {r.description}" for r in RACES.values()]
    return "\n".join(lines)


def pick_class(race: Race) -> str:
    lines = [f"⚔️ حالا {bold('کلاس')} جنگیدن را انتخاب کنید:", ""]
    lines += [f"{c.emoji} {c.name} — {c.description}" for c in CLASSES.values()]
    return "\n".join(lines)


def created(player: Player) -> str:
    return (
        f"🎉 {bold('قهرمان شما ساخته شد')}\n"
        f"{player.race.emoji} {player.race.name} · {player.char_class.emoji} {player.char_class.name}\n\n"
        f"🎁 هدیه‌ی پادشاه: {bold(fa(player.gold))} سکه، یک سلاح و چند معجون انرژی.\n\n"
        "برای ماجراجویی با دوستان، ربات را به گروه اضافه کنید و بنویسید «راهنما»."
    )


# --- profile and help --------------------------------------------------------------------------
def profile_header(player: Player, xp_needed: int) -> str:
    return (
        f"👤 {bold(player.name)} · سطح {fa(player.level)}\n"
        f"{player.race.emoji} {player.race.name} · {player.char_class.emoji} {player.char_class.name}\n"
        f"⭐ تجربه {fa(player.xp)} / {fa(xp_needed)}\n{bar(player.xp, xp_needed, 10)}\n"
        f"🪙 {fa(player.gold)} سکه · 💎 {fa(player.crystal)} کریستال\n"
        f"🏆 {fa(player.wins)} پیروزی · 💀 {fa(player.losses)} شکست"
    )


def profile_lines(player: Player, stats: Stats, xp_needed: int, max_energy: int) -> str:
    """Full text profile (used when looking at another player in a group)."""
    return "\n".join(
        [
            profile_header(player, xp_needed),
            LINE,
            f"❤️ جان: {fa(stats.hp)}",
            f"⚡ انرژی: {fa(player.energy)} / {fa(max_energy)}",
            f"⚔️ حمله: {fa(stats.atk)}",
            f"🛡️ دفاع: {fa(stats.defense)}",
            f"✨ جادو: {fa(stats.magic)}",
            f"💨 سرعت: {fa(stats.speed)}",
            f"🍀 شانس: {fa(stats.luck)}",
        ]
    )


def command_help(registry, in_group: bool) -> str:  # noqa: ANN001
    """Help generated from the registry, so it always matches the real commands."""
    categories: dict[str, list[str]] = {}
    for cmd in registry.all():
        if cmd.name == "start" or cmd.category.startswith("🛠️") or (in_group and not cmd.group) or (
            not in_group and not cmd.private
        ):
            continue
        persian = [a for a in cmd.aliases if not a.isascii()]
        label = persian[0] if persian else "/" + cmd.aliases[0]
        categories.setdefault(cmd.category, []).append(f"• {label}: {cmd.description}")
    blocks = [f"{bold(title)}\n" + "\n".join(lines) for title, lines in categories.items()]
    return f"📖 {bold('راهنمای دستورها')}\n\n" + "\n\n".join(blocks)


def help_text() -> str:
    return (
        f"❓ {bold('راهنمای ماجراجو')}\n\n"
        "🏠 این‌جا (پیام خصوصی): قهرمان، کوله‌پشتی، فروشگاه و بازار شما.\n"
        "🏰 گروه‌ها: ماجراجویی، شکار، دوئل و بازار.\n\n"
        "ربات را به گروه اضافه کنید و بنویسید «راهنما» تا دستورها را ببینید."
    )


# --- activities and hunting --------------------------------------------------------------------
def _gains(gold: int, crystal: int, xp: int) -> str:
    parts = []
    if gold:
        parts.append(f"🪙 {bold(fa(gold))} سکه")
    if crystal:
        parts.append(f"💎 {bold(fa(crystal))} کریستال")
    if xp:
        parts.append(f"⭐ {bold(fa(xp))} تجربه")
    return " · ".join(parts)


def level_up_text(level: int) -> str:
    return f"🎉 {bold('سطح تازه')}! به سطح {bold(fa(level))} رسیدید و قدرتی تازه بیدار شد."


def activity_result(name: str, result) -> str:  # noqa: ANN001 - ActivityResult
    rolled, player = result.rolled, result.player
    lines = [result.activity.intro.format(name=name), "", rolled.outcome.text.format(name=name)]
    gains = _gains(rolled.gold, rolled.crystal, rolled.xp)
    if gains:
        lines += ["", gains]
    if result.items:
        lines.append("📦 " + "، ".join(f"{label} ×{fa(qty)}" for label, qty in result.items))
    if result.level_up:
        lines += ["", level_up_text(result.level_up.new_level)]
    lines += ["", f"⚡ انرژی: {fa(player.energy)}"]
    return "\n".join(lines)


def hunt_result(name: str, r) -> str:  # noqa: ANN001 - HuntResult
    lines = [
        f"🌲 فرمانده {name} در سرزمین‌های وحشی با {bold(r.monster.name)} {r.monster.emoji} روبه‌رو شد!",
        f"نبرد {fa(r.rounds)} دور طول کشید.",
        "",
    ]
    if r.won:
        lines.append(f"🏆 {bold('پیروز شدید')} و هیولا به زانو درآمد.")
    else:
        lines.append(
            f"💔 {bold('این بار هیولا قوی‌تر بود')} و عقب‌نشینی کردید. چیزی از دست ندادید؛ "
            "قوی‌تر شوید و دوباره بیایید!"
        )
    lines.append(f"❤️ جان باقی‌مانده: {fa(r.hero_hp)} / {fa(r.hero_max_hp)}")
    gains = _gains(r.gold, 0, r.xp)
    if gains:
        lines += ["", gains]
    if r.items:
        lines.append("📦 " + "، ".join(f"{label} ×{fa(q)}" for label, q in r.items))
    if r.level_up:
        lines += ["", level_up_text(r.level_up.new_level)]
    lines += ["", f"⚡ انرژی: {fa(r.player.energy)}"]
    return "\n".join(lines)


# --- upgrades ----------------------------------------------------------------------------------
def upgrade_quote(piece, quote) -> str:  # noqa: ANN001
    from ..game.data.items import get_item

    mats = "، ".join(f"{get_item(i).label} ×{fa(q)}" for i, q in quote.materials.items())
    return (
        f"🔨 {bold('کارگاه آهنگری')}\n"
        f"{piece.item.name} به مرتبه‌ی {bold('+' + fa(quote.next_level))}\n\n"
        f"💰 دستمزد: {fa(quote.gold)} سکه\n"
        f"📦 مواد: {mats}\n"
        f"🎯 شانس موفقیت: {fa(round(quote.chance * 100))}٪\n\n"
        "اگر نشد، فقط مواد از بین می‌رود؛ تجهیزات سالم می‌ماند."
    )


def upgrade_result(result) -> str:  # noqa: ANN001 - UpgradeResult
    if result.success:
        return f"✨ {bold('ارتقا موفق بود')}\n{result.piece.item.name} حالا {bold('+' + fa(result.piece.upgrade))} است."
    return (
        f"💥 {bold('این بار نشد')}\n"
        f"مواد از بین رفت، اما {result.piece.item.name} سالم ماند. دوباره تلاش کنید!"
    )


# --- rankings ----------------------------------------------------------------------------------
def ranking(board) -> str:  # noqa: ANN001 - Board
    if not board.entries:
        return f"{board.title}\n{LINE}\nهنوز کسی در این تالار نیست. اولین شما باشید!"
    medals = ["🥇", "🥈", "🥉"]
    lines = [board.title, LINE]
    for index, entry in enumerate(board.entries):
        place = medals[index] if index < 3 else f"{fa(index + 1)}."
        lines.append(f"{place} {entry.badge} {entry.name} · سطح {fa(entry.level)} · {fa(entry.value)} {board.unit}")
    if board.my_position:
        lines += [LINE, f"📍 جایگاه شما: {bold(fa(board.my_position))}"]
    return "\n".join(lines)


# --- chests ------------------------------------------------------------------------------------
def chest_odds(item, odds) -> str:  # noqa: ANN001
    from ..game.data.items import get_item

    lines = [f"🎲 {bold('شانس محتویات ' + item.name)}", LINE]
    for prize, share in sorted(odds, key=lambda x: -x[1]):
        parts = []
        if prize.gold[1]:
            parts.append(f"{fa(prize.gold[0])} تا {fa(prize.gold[1])} سکه")
        if prize.crystal[1]:
            parts.append(f"{fa(prize.crystal[0])} تا {fa(prize.crystal[1])} کریستال")
        if prize.item_id:
            qty = f" ×{fa(prize.qty[0])}" + (f" تا {fa(prize.qty[1])}" if prize.qty[1] > prize.qty[0] else "")
            parts.append(get_item(prize.item_id).name + qty)
        pct = f"{share * 100:.1f}".translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫"))
        lines.append(f"{pct}٪  " + " + ".join(parts))
    lines += [LINE, "این‌ها شانس واقعی ربات هستند."]
    return "\n".join(lines)


def chest_opened(name: str, opened) -> str:  # noqa: ANN001 - Opened
    got = []
    if opened.gold:
        got.append(f"🪙 {bold(fa(opened.gold))} سکه")
    if opened.crystal:
        got.append(f"💎 {bold(fa(opened.crystal))} کریستال")
    if opened.item:
        got.append(f"{opened.item.label} ×{bold(fa(opened.qty))} ({opened.item.rarity_label})")
    return f"🗝️ {bold(opened.chest.name + ' باز شد')}\n\n✨ این گنج را یافتید:\n" + "\n".join(got)


# --- premium shop and payments -----------------------------------------------------------------
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

    lines = [f"💎 {bold('خزانه‌ی ویژه')}", LINE]
    if payments_enabled:
        for section, title in SECTIONS.items():
            lines.append(bold(title))
            for pack in (p for p in PACKS.values() if p.section == section):
                lines.append(f"• {pack.label} — {fa(pack.price_toman)} تومان")
                if section == "bundles":
                    lines.append(f"   {pack_description(pack)}")
            lines.append("")
    else:
        lines += ["خرید با پول واقعی فعلاً بسته است.", ""]
    lines.append(bold("🎁 صندوقچه‌ها (با کریستال)"))
    for chest in CHESTS.values():
        if chest.price and chest.price[0] == "crystal":
            lines.append(f"• {get_item(chest.item_id).label} — {fa(chest.price[1])} 💎")
    lines += [
        LINE,
        "💳 پرداخت با کیف پول بله است و اطلاعات کارت ذخیره نمی‌شود.",
        "👨‍👩‍👧 زیر ۱۸ سال؟ فقط با اجازه‌ی پدر و مادر خرید کنید.",
    ]
    return "\n".join(lines)


def delivery(order) -> str:  # noqa: ANN001 - Order
    return (
        f"✅ {bold('پرداخت موفق بود')}\n"
        f"{order.pack.label} به گنجینه‌ی شما رسید.\n{pack_description(order.pack)}\n\n"
        "سپاس از حمایت شما 💛"
    )


# --- duels -------------------------------------------------------------------------------------
def duel_invite(challenger, target, seconds: int) -> str:  # noqa: ANN001 - Player
    return (
        f"⚔️ {bold('فراخوان دوئل')}\n\n"
        f"{challenger.char_class.emoji} {bold(challenger.name)} · سطح {fa(challenger.level)}\n"
        f"🏆 {fa(challenger.wins)} پیروزی · 💀 {fa(challenger.losses)} شکست\n\n"
        f"فرمانده {bold(target.name)} ، دعوت را می‌پذیرید؟\n"
        f"⏳ {duration(seconds)} فرصت دارید."
    )


def _hp_line(f) -> str:  # noqa: ANN001 - Fighter
    return f"{f.emoji} {f.name}  ❤️ {fa(max(f.hp, 0))}/{fa(f.max_hp)}\n{bar(f.hp, f.max_hp, 10)}"


def duel_status(battle, lines: list[str], turn_seconds: int) -> str:  # noqa: ANN001 - Battle
    a, b = battle.fighters
    parts = [f"⚔️ {bold('میدان نبرد')}", LINE, _hp_line(a), _hp_line(b), LINE]
    parts += lines
    if not battle.finished:
        parts += [
            LINE,
            f"🎯 نوبت {bold(battle.current.name)} · دور {fa(battle.round)} از {fa(battle.max_rounds)}",
            f"⏳ {duration(turn_seconds)} فرصت دارید.",
        ]
    return "\n".join(parts)


def duel_result(update) -> str:  # noqa: ANN001 - DuelUpdate
    battle = update.battle
    a, b = battle.fighters
    parts = [f"🏁 {bold('پایان نبرد')}", LINE, _hp_line(a), _hp_line(b), LINE, *update.lines, LINE]
    if battle.winner is None:
        parts.append("🤝 مساوی شد؛ هر دو دلاور بودند!")
    else:
        parts.append(f"🏆 برنده: {bold(battle.fighters[battle.winner].name)}")
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
        parts.append(f"{fighter.name}: " + (" · ".join(gains) if gains else "سقف پاداش امروز پر است"))
    return "\n".join(parts)
