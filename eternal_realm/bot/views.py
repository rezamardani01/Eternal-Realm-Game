"""Text rendering.

Voice: an epic storyteller speaking to «فرمانده» in formal «شما», but with simple words so a
12-year-old can read it. Plain text with emoji only, so player names can never break formatting.
"""

from __future__ import annotations

from ..game.data.classes import CLASSES, CharacterClass
from ..game.data.items import SLOT_LABELS
from ..game.data.races import RACES, Race
from ..game.data.stats import Stats
from ..game.models import Player
from ..shared.text import bar, duration, fa

LINE = "━━━━━━━━━━━━━━"


# --- first steps -------------------------------------------------------------------------------
def race_list() -> str:
    return "\n\n".join(f"{r.emoji} {r.name}\n{r.description}" for r in RACES.values())


def class_list() -> str:
    return "\n\n".join(
        f"{c.emoji} {c.name}\n{c.description}\nمهارت ویژه: {c.skill.emoji} {c.skill.name}"
        for c in CLASSES.values()
    )


def welcome() -> str:
    return (
        "🏰 درود بر شما، ماجراجوی شجاع!\n"
        "به «قلمرو جاودان» خوش آمدید.\n\n"
        "سال‌ها پیش، در سرزمین میتوریا، نیرویی جادویی به نام «جوهر جادو» به همه‌ی موجودات جان می‌داد. "
        "اما مُهر باستانی شکست و جادو همه‌جا پخش شد. حالا هیولاها بیدار شده‌اند، گنج‌ها در تاریکی "
        "منتظرند و تنها قهرمانانی مثل شما می‌توانند سرنوشت میتوریا را عوض کنند.\n\n"
        "⚔️ با هیولاها بجنگید\n🎣 ماهی بگیرید و معدن بکنید\n🛡️ در گروه‌ها با دوستانتان دوئل کنید\n"
        "💰 تجهیزات بخرید، بفروشید و قوی‌تر شوید\n\n"
        "✍️ برای شروع، نام قهرمان خود را بنویسید (۲ تا ۱۶ حرف). "
        "مردم قلمرو این نام را در سرودهایشان خواهند خواند!"
    )


def pick_race(name: str) -> str:
    return (
        f"✨ چه نام باشکوهی، «{name}»!\n\n"
        "حالا بگویید در رگ‌های شما خون کدام نژاد می‌جوشد؟ "
        "هر نژاد توانایی‌ها و ضعف‌های خودش را دارد و هیچ‌کدام در همه‌چیز بهترین نیست:\n\n"
        f"{race_list()}"
    )


def pick_class(name: str, race: Race) -> str:
    return (
        f"👤 {name} · {race.emoji} {race.name}\n\n"
        "آخرین گام: سبک جنگیدن خود را انتخاب کنید. "
        "نژاد می‌گوید شما که هستید و کلاس می‌گوید چطور می‌جنگید؛ پس هر ترکیبی ممکن است!\n\n"
        f"{class_list()}"
    )


def created(player: Player, bot_username: str) -> str:
    return (
        f"🎉 درود بر فرمانده {player.name}!\n"
        f"{player.race.emoji} {player.race.name} · {player.char_class.emoji} {player.char_class.name}\n"
        "نام شما در دفتر قلمرو جاودان نوشته شد.\n\n"
        f"🎁 پادشاه برای آغاز راه، {fa(player.gold)} سکه، یک سلاح و چند معجون انرژی به شما بخشید.\n\n"
        "📌 قدم بعدی: ربات را به گروه خود اضافه کنید و آنجا بنویسید «راهنما». "
        "قهرمان شما، سکه‌ها و تجهیزاتتان در همه‌ی گروه‌ها یکی است و هیچ‌جا از اول شروع نمی‌کنید."
    )


def pick_summary(race: Race, cls: CharacterClass) -> str:
    return f"{race.emoji} {race.name} · {cls.emoji} {cls.name}"


# --- profile and help --------------------------------------------------------------------------
def profile(player: Player, stats: Stats, xp_needed: int, max_energy: int) -> str:
    race, cls = player.race, player.char_class
    xp = fa(player.xp) + " / " + fa(xp_needed)
    return "\n".join(
        [
            f"{cls.emoji} فرمانده {player.name} | سطح {fa(player.level)}",
            f"{race.emoji} {race.name} · {cls.name}",
            LINE,
            f"❤️ جان: {fa(stats.hp)}",
            f"⚡ انرژی: {fa(player.energy)} / {fa(max_energy)} {bar(player.energy, max_energy, 8)}",
            f"⚔️ قدرت حمله: {fa(stats.atk)}   🛡️ دفاع: {fa(stats.defense)}",
            f"✨ جادو: {fa(stats.magic)}   💨 سرعت: {fa(stats.speed)}   🍀 شانس: {fa(stats.luck)}",
            f"⭐ تجربه: {xp} {bar(player.xp, xp_needed, 8)}",
            LINE,
            f"🪙 سکه: {fa(player.gold)}   💎 کریستال: {fa(player.crystal)}",
            f"🏆 پیروزی در دوئل: {fa(player.wins)}   💀 شکست: {fa(player.losses)}",
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
    blocks = [f"{title}\n" + "\n".join(lines) for title, lines in categories.items()]
    return (
        "📖 کتاب راهنمای قلمرو جاودان\n"
        "ای فرمانده، کافی است هر کدام از این کلمه‌ها را در گروه بنویسید:\n\n" + "\n\n".join(blocks)
    )


def help_text() -> str:
    return (
        "❓ راهنمای ماجراجو\n\n"
        "قلمرو جاودان دو جا دارد:\n"
        "🏠 همین‌جا (پیام خصوصی): قهرمان، کوله‌پشتی، تجهیزات و فروشگاه شما.\n"
        "🏰 گروه‌ها: جایی که زندگی در قلمرو جریان دارد؛ ماهیگیری، شکار، دوئل و بازار.\n\n"
        "ربات را به گروه خود اضافه کنید و بنویسید:\n"
        "• «پروفایل» تا قهرمان خود را ببینید (روی پیام کسی ریپلای کنید تا قهرمان او را ببینید)\n"
        "• «راهنما» تا فهرست کامل دستورها را بخوانید"
    )


# --- activities and hunting --------------------------------------------------------------------
def _gains(gold: int, crystal: int, xp: int) -> str:
    parts = []
    if gold:
        parts.append(f"🪙 {fa(gold)} سکه")
    if crystal:
        parts.append(f"💎 {fa(crystal)} کریستال")
    if xp:
        parts.append(f"⭐ {fa(xp)} تجربه")
    return " · ".join(parts)


def activity_result(name: str, result) -> str:  # noqa: ANN001 - ActivityResult
    rolled, player = result.rolled, result.player
    lines = [result.activity.intro.format(name=name), "", rolled.outcome.text.format(name=name)]
    gains = _gains(rolled.gold, rolled.crystal, rolled.xp)
    if gains or result.items:
        lines.append("")
        lines.append("🎁 غنیمت شما:")
    if gains:
        lines.append(gains)
    if result.items:
        lines.append("📦 " + "، ".join(f"{label} ×{fa(qty)}" for label, qty in result.items))
    if result.level_up:
        lines += ["", level_up_text(result.level_up.new_level)]
    lines += ["", f"⚡ انرژی باقی‌مانده: {fa(player.energy)}"]
    return "\n".join(lines)


def level_up_text(level: int) -> str:
    return (
        f"🎉 فرمانده! رنج راه بی‌ثمر نماند. به سطح {fa(level)} رسیدید و قدرتی تازه در وجودتان بیدار شد!"
    )


def hunt_result(name: str, r) -> str:  # noqa: ANN001 - HuntResult
    lines = [
        f"🌲 فرمانده {name} به دل سرزمین‌های وحشی رفت و ناگهان «{r.monster.name}» {r.monster.emoji} "
        "راهش را بست!",
        f"⚔️ نبردی سخت در گرفت و {fa(r.rounds)} دور طول کشید...",
        "",
    ]
    if r.won:
        lines.append(f"🏆 درود بر فرمانده پیروز! {r.monster.name} در برابر قدرت شما به زانو درآمد.")
    else:
        lines.append(
            f"💔 افسوس! این بار {r.monster.name} قوی‌تر بود و شما با زخم‌هایتان عقب‌نشینی کردید.\n"
            "نگران نباشید؛ هیچ سکه‌ای از دست ندادید. تجهیزاتتان را قوی‌تر کنید، کمی نیرو بگیرید "
            "و دوباره به میدان برگردید!"
        )
    lines.append(f"❤️ جان باقی‌مانده: {fa(r.hero_hp)} / {fa(r.hero_max_hp)}")
    gains = _gains(r.gold, 0, r.xp)
    if gains or r.items:
        lines += ["", "🎁 غنایم نبرد:" if r.won else "🎖️ پاداش تلاش:"]
    if gains:
        lines.append(gains)
    if r.items:
        lines.append("📦 " + "، ".join(f"{label} ×{fa(q)}" for label, q in r.items))
    if r.level_up:
        lines += ["", level_up_text(r.level_up.new_level)]
    lines += ["", f"⚡ انرژی باقی‌مانده: {fa(r.player.energy)}"]
    return "\n".join(lines)


# --- shop and upgrades -------------------------------------------------------------------------
def shop_listing() -> str:
    from ..game.services.shop import shop_items

    groups: dict[str, list[str]] = {}
    for item in shop_items():
        title = "🧪 معجون‌ها و مصرفی‌ها" if item.kind.value == "consumable" else "⚔️ سلاح و زره"
        bonus = f" {item.stats.short()}" if item.is_gear else ""
        level = f" (از سطح {fa(item.level_req)})" if item.level_req > 1 else ""
        groups.setdefault(title, []).append(f"• {item.label}{bonus}{level} — {fa(item.buy)} 🪙")
    blocks = [f"{title}\n" + "\n".join(lines) for title, lines in groups.items()]
    return (
        "🛒 بازارچه‌ی آهنگران و جادوگران\n"
        "«بفرمایید فرمانده! بهترین کالاها برای بهترین قهرمانان!»\n"
        + LINE + "\n" + "\n\n".join(blocks) + "\n" + LINE + "\n"
        "🛍️ برای خرید بنویسید: خرید نام‌کالا تعداد\n"
        "💰 برای فروش: فروش نام‌کالا تعداد  (یا فروش #شماره‌ی تجهیزات)\n"
        "📦 صندوقچه‌ها و بسته‌ها: «صندوقچه» و «فروشگاه ویژه»"
    )


def upgrade_quote(piece, quote) -> str:  # noqa: ANN001
    from ..game.data.items import get_item

    mats = "، ".join(f"{get_item(i).label} ×{fa(q)}" for i, q in quote.materials.items())
    return (
        f"🔨 کارگاه آهنگری\n"
        f"آهنگر می‌خواهد {piece.label} شما را به مرتبه‌ی +{fa(quote.next_level)} برساند.\n\n"
        f"💰 دستمزد: {fa(quote.gold)} 🪙\n"
        f"📦 مواد لازم: {mats}\n"
        f"🎯 شانس موفقیت: {fa(round(quote.chance * 100))}٪\n\n"
        "اگر کار بد پیش برود، مواد از بین می‌رود اما تجهیزات شما هرگز نابود نمی‌شود. آماده‌اید؟"
    )


def upgrade_result(result) -> str:  # noqa: ANN001 - UpgradeResult
    if result.success:
        return (
            f"✨ چکش آهنگر بر سندان فرود آمد و جرقه‌ها به آسمان رفتند!\n"
            f"ارتقا موفق بود: {result.piece.label}\n"
            f"قدرت تازه: {result.piece.stats.short()}"
        )
    return (
        "💥 این بار فلز تاب نیاورد و ترک برداشت؛ مواد از بین رفت.\n"
        f"اما خبر خوب این است که {result.piece.label} سالم ماند. دوباره تلاش کنید، "
        "قهرمانان هیچ‌وقت زود تسلیم نمی‌شوند!"
    )


# --- market ------------------------------------------------------------------------------------
def market_listings(listings, item, title: str | None = None) -> str:  # noqa: ANN001
    head = title or ("🏪 بازار بزرگ قلمرو" + (f" · {item.label}" if item else ""))
    if not listings:
        hint = (
            "بازار امروز خلوت است. شما می‌توانید اولین فروشنده باشید!\n"
            "مثال: «عرضه سنگ آهن 10 900» یعنی ۱۰ سنگ آهن را روی هم ۹۰۰ سکه می‌فروشم."
        )
        return f"{head}\n{LINE}\n🕊️ آگهی فعالی پیدا نشد.\n{hint}"
    lines = [head, "فروشندگان قلمرو کالاهایشان را به نمایش گذاشته‌اند:", LINE]
    for lst in listings:
        seller = f" — از {lst.seller_name}" if lst.seller_name else ""
        lines.append(f"🔖{fa(lst.id)}  {lst.label}  {fa(lst.price)} 🪙{seller}")
    lines += [
        LINE,
        "🛍️ خرید: «بخر شماره‌ی آگهی»",
        "🏷️ فروش کالای خودتان: «عرضه ...»",
        "↩️ پس گرفتن آگهی: «لغو شماره‌ی آگهی»",
    ]
    return "\n".join(lines)


# --- rankings ----------------------------------------------------------------------------------
def ranking(board) -> str:  # noqa: ANN001 - Board
    if not board.entries:
        return (
            f"{board.title}\n{LINE}\n"
            "هنوز هیچ قهرمانی نامش را در این تالار ننوشته است.\n"
            "شما می‌توانید اولین باشید؛ کافی است ماجراجویی کنید!"
        )
    medals = ["🥇", "🥈", "🥉"]
    lines = [board.title, "نام بزرگان قلمرو بر این لوح نوشته شده است:", LINE]
    for index, entry in enumerate(board.entries):
        place = medals[index] if index < 3 else f"{fa(index + 1)}."
        lines.append(f"{place} {entry.badge} {entry.name} (سطح {fa(entry.level)}) — {fa(entry.value)} {board.unit}")
    if board.my_position:
        lines += [LINE, f"📍 جایگاه شما در این تالار: {fa(board.my_position)}"]
    return "\n".join(lines)


# --- chests ------------------------------------------------------------------------------------
def chest_list(owned: dict[str, int]) -> str:
    from ..game.data.chests import CHESTS
    from ..game.data.items import get_item

    lines = ["🎁 گنجینه‌ی صندوقچه‌ها", "هر صندوقچه رازی در دل دارد. چه چیزی در انتظار شماست؟", LINE]
    for chest in CHESTS.values():
        item = get_item(chest.item_id)
        icon = "🪙" if chest.price and chest.price[0] == "gold" else "💎"
        price = f"{fa(chest.price[1])} {icon}" if chest.price else "—"
        lines.append(f"{item.label} — بها: {price} — در کوله‌ی شما: {fa(owned.get(item.id, 0))}")
    lines += [
        LINE,
        "🛍️ خرید: «خرید صندوقچه جادویی»",
        "🗝️ گشودن: «باز کردن صندوقچه جادویی»",
        "🎲 دیدن شانس محتویات: «شانس صندوقچه جادویی»",
    ]
    return "\n".join(lines)


def chest_odds(item, odds) -> str:  # noqa: ANN001
    from ..game.data.items import get_item

    lines = [f"🎲 رازهای {item.label}", "این‌ها همه‌ی چیزهایی است که ممکن است از آن بیرون بیاید:", LINE]
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
    lines += [LINE, "✅ این درصدها همان شانس واقعی ربات هستند و هیچ چیز پنهانی در کار نیست."]
    return "\n".join(lines)


def chest_opened(name: str, opened) -> str:  # noqa: ANN001 - Opened
    got = []
    if opened.gold:
        got.append(f"🪙 {fa(opened.gold)} سکه")
    if opened.crystal:
        got.append(f"💎 {fa(opened.crystal)} کریستال")
    if opened.item:
        got.append(f"{opened.item.label} ×{fa(opened.qty)} ({opened.item.rarity_label})")
    return (
        f"🗝️ فرمانده {name} قفل {opened.chest.label} را شکست و در را آهسته گشود...\n\n"
        "✨ ای بخت بلند! درون آن این گنج را یافتید:\n" + "\n".join(got)
    )


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

    lines = [
        "💎 خزانه‌ی ویژه‌ی قلمرو",
        "«فرمانده، اینجا گنج‌هایی است که راه ماجراجویی را کوتاه‌تر می‌کنند.»",
        LINE,
    ]
    if payments_enabled:
        for section, title in SECTIONS.items():
            lines.append(title)
            for pack in (p for p in PACKS.values() if p.section == section):
                lines.append(f"• {pack.label} — {fa(pack.price_toman)} تومان")
                if section == "bundles":
                    lines.append(f"   {pack_description(pack)}")
            lines.append("")
    else:
        lines += ["🔒 خرید با پول واقعی فعلاً بسته است. با بازی کردن هم می‌توانید به همه‌چیز برسید!", ""]
    lines.append("🎁 صندوقچه‌ها (با کریستال)")
    for chest in CHESTS.values():
        if chest.price and chest.price[0] == "crystal":
            lines.append(f"• {get_item(chest.item_id).label} — {fa(chest.price[1])} 💎")
    lines += [
        "🎲 شانس واقعی هر صندوقچه را ببینید: «شانس صندوقچه جادویی»",
        LINE,
        "💳 پرداخت با کیف پول بله انجام می‌شود و اطلاعات کارت شما هیچ‌جا ذخیره نمی‌شود.",
        "👨‍👩‍👧 دوستان زیر ۱۸ سال، لطفاً فقط با اطلاع و اجازه‌ی پدر و مادر خرید کنید.",
        "💛 یادتان باشد: همه‌چیز را می‌شود با بازی کردن هم به‌دست آورد؛ خرید فقط یک میان‌بر است.",
    ]
    return "\n".join(lines)


def delivery(order) -> str:  # noqa: ANN001 - Order
    return (
        f"✅ پرداخت شما با موفقیت انجام شد! (سفارش {fa(order.id)})\n\n"
        f"🎁 {order.pack.label} به گنجینه‌ی شما رسید.\n{pack_description(order.pack)}\n\n"
        "سپاس از اینکه از قلمرو جاودان پشتیبانی می‌کنید؛ نامتان در قلب میتوریا می‌ماند 💛"
    )


# --- duels -------------------------------------------------------------------------------------
def duel_invite(challenger, target, seconds: int) -> str:  # noqa: ANN001 - Player
    return (
        "⚔️ طبل جنگ نواخته شد!\n\n"
        f"فرمانده {challenger.name} شما را به دوئل فرا خوانده است.\n"
        f"{challenger.race.emoji} {challenger.race.name} · سطح {fa(challenger.level)}\n"
        f"🏆 پیروزی: {fa(challenger.wins)} · 💀 شکست: {fa(challenger.losses)}\n\n"
        f"فرمانده {target.name}، دعوت را می‌پذیرید؟\n"
        f"⏳ {duration(seconds)} فرصت دارید."
    )


def _hp_line(f) -> str:  # noqa: ANN001 - Fighter
    return f"{f.emoji} {f.name}  ❤️ {fa(max(f.hp, 0))}/{fa(f.max_hp)}  {bar(f.hp, f.max_hp, 8)}"


def duel_status(battle, lines: list[str], turn_seconds: int) -> str:  # noqa: ANN001 - Battle
    a, b = battle.fighters
    parts = ["⚔️ میدان نبرد", LINE, _hp_line(a), _hp_line(b), LINE]
    parts += lines
    if not battle.finished:
        parts += [
            LINE,
            f"🎯 نوبت فرمانده {battle.current.name} است | دور {fa(battle.round)} از {fa(battle.max_rounds)}",
            f"⏳ {duration(turn_seconds)} فرصت برای انتخاب حرکت دارید.",
        ]
    return "\n".join(parts)


def duel_result(update) -> str:  # noqa: ANN001 - DuelUpdate
    battle = update.battle
    a, b = battle.fighters
    parts = ["🏁 پایان نبرد", LINE, _hp_line(a), _hp_line(b), LINE, *update.lines, LINE]
    if battle.winner is None:
        parts.append("🤝 هیچ‌کس برنده نشد؛ هر دو آن‌قدر دلاور بودند که میدان مساوی شد!")
    else:
        winner = battle.fighters[battle.winner].name
        parts.append(f"🏆 درود بر فرمانده {winner}! پیروز میدان است و نامش در قلمرو می‌پیچد.")
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
            gains.append(f"🎉 رسید به سطح {fa(payout.level_up.new_level)}")
        parts.append(
            f"{fighter.name}: " + (" · ".join(gains) if gains else "امروز سقف پاداش دوئل پر شده؛ فردا دوباره!")
        )
    return "\n".join(parts)


# --- backpack ----------------------------------------------------------------------------------
def inventory(owner: str, view) -> str:  # noqa: ANN001 - InventoryView
    lines = [f"🎒 کوله‌پشتی فرمانده {owner}", LINE]
    if view.stacks:
        lines.append("📦 آیتم‌ها")
        lines += [f"• {item.label} ×{fa(qty)}" for item, qty in view.stacks]
    else:
        lines.append(
            "📦 هیچ آیتمی ندارید.\nبا «ماهیگیری»، «معدن» یا «شکار» می‌توانید کوله‌تان را پر کنید!"
        )
    lines.append(LINE)
    if view.gear:
        lines.append("⚔️ تجهیزات (برای پوشیدن بنویسید: «تجهیز شماره»)")
        for piece in view.gear:
            mark = " ✅ پوشیده" if piece.slot else ""
            lines.append(
                f"#{fa(piece.id)} {piece.label} {piece.item.rarity_label}{mark}\n    {piece.stats.short()}"
            )
    else:
        lines.append(
            "⚔️ هنوز سلاح و زرهی ندارید.\nدر «فروشگاه» تجهیزات بخرید یا از هیولاها غنیمت بگیرید."
        )
    return "\n".join(lines)


def equipment(owner: str, view, stats: Stats) -> str:  # noqa: ANN001
    worn = {p.slot: p for p in view.gear if p.slot}
    lines = [f"🧰 جنگ‌افزارهای فرمانده {owner}", LINE]
    for slot, label in SLOT_LABELS.items():
        piece = worn.get(slot)
        lines.append(f"{label}: {piece.label + ' ' + piece.stats.short() if piece else 'خالی'}")
    lines += [LINE, f"💪 قدرت کل شما: {stats.short()}"]
    return "\n".join(lines)
