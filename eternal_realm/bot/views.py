"""Text rendering.

Rules of the house: every message starts with exactly ONE emoji, titles and key numbers are
bold (single ``*`` markers, the only bold Bale understands), each stat sits on its own
line, and the voice is a friendly epic storyteller in simple formal Persian.
"""

from __future__ import annotations

from ..game.data.bosses import behavior_of
from ..game.data.classes import CLASSES
from ..game.data.items import get_item
from ..game.data.leagues import league_of
from ..game.data.races import RACES, Race
from ..game.data.stats import Stats
from ..game.models import Player
from ..shared.text import bar, bold, duration, emphasize, fa

LINE = "━━━━━━━━━━━━"
DIV = "┈┈┈┈┈┈┈┈┈┈"


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
def profile_header(player: Player, xp_needed: int, now: int = 0) -> str:
    return (
        f"👤 {bold(player.name)} · سطح {fa(player.level)}\n"
        + (f"🏅 عنوان: {player.honor}\n" if player.honor else "")
        + ("💠 اشتراک VIP فعال\n" if player.vip_until > now > 0 else "")
        + f"{player.race.emoji} {player.race.name} · {player.char_class.emoji} {player.char_class.name}\n"
        + (f"🎭 کلاس دوم: {player.class2.emoji} {player.class2.name}\n" if player.class2 else "")
        + ("✨ قدرت پنهان بیدار شده\n" if player.awakened else "")
        + f"⭐ تجربه {fa(player.xp)} / {fa(xp_needed)}\n{bar(player.xp, xp_needed, 10)}\n"
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


HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("🌍 ماجراجویی (انرژی می‌خواهد)", [
        ("🎣 ماهیگیری", "ماهی، گنج و گاهی کریستال از دریاچه"),
        ("⛏️ معدن", "سنگ، آهن، طلا و پاره‌کریستال"),
        ("🌿 گیاه", "گیاه‌های شفابخش و کمیاب"),
        ("🔍 جستجو", "سکه، معجون و صندوقچه‌های پنهان"),
        ("🐺 شکار", "جنگ با هیولا برای تجربه و غنیمت"),
        ("😴 استراحت", "انرژی برمی‌گردد (هر ۳۰ دقیقه)"),
        ("🗺️ ماجراجویی", "همه‌ی فعالیت‌ها با دکمه"),
    ]),
    ("⚔️ مبارزه", [
        ("⚔️ مبارزه", "روی پیام یک نفر ریپلای کنید و بنویسید «مبارزه»؛ نبرد نوبتی با دکمه است"),
    ]),
    ("🎒 کوله‌پشتی و بازار", [
        ("🎒 کوله‌پشتی", "آیتم‌ها و تجهیزاتتان؛ پوشیدن و ارتقا با دکمه"),
        ("🎁 صندوقچه", "خرید، باز کردن و دیدن شانس‌ها"),
        ("🛒 فروشگاه", "خرید سلاح، زره و معجون"),
        ("🏪 بازار", "خرید و فروش با دیگر بازیکنان"),
        ("💎 فروشگاه ویژه", "بسته‌های سکه و کریستال (در پیوی)"),
    ]),
    ("👤 قهرمان", [
        ("🏰 قلمرو", "منوی اصلی شما با دکمه‌ها؛ از آن‌جا همه‌جا می‌روید"),
        ("👤 پروفایل", "قهرمان شما؛ با ریپلای، قهرمان دیگران"),
        ("🎁 جایزه", "گنجینه‌ی روزانه"),
        ("💸 انتقال 500", "روی پیام دوستتان ریپلای کنید تا سکه ببخشید"),
        ("📲 کیف من", "دکمه‌ی ورود به پنل شخصی در پیوی"),
        ("🏆 رتبه", "برترین‌های همین گروه و کل قلمرو"),
    ]),
]

ADMIN_HELP = (
    "🛠️ مدیران گروه",
    [
        ("⛔ غیرفعال ماهیگیری", "بستن یک فعالیت در همین گروه"),
        ("✅ فعال ماهیگیری", "باز کردن دوباره‌اش"),
        ("⚙️ تنظیمات گروه", "دیدن وضعیت بازی در گروه"),
    ],
)


def _help_block(title: str, rows: list[tuple[str, str]]) -> str:
    entries = "\n\n".join(f"{name}\n{desc}" for name, desc in rows)
    return f"{bold(title)}\n\n{entries}"


def command_help(registry, in_group: bool) -> str:  # noqa: ANN001 - kept for API compatibility
    """Complete help with a blank line between entries (a test keeps it in sync with the commands)."""
    sections = list(HELP_SECTIONS)
    if in_group:
        sections.append(ADMIN_HELP)
    tail = "💡 همه‌ی کارهای دیگر، مثل پوشیدن، خرید و فروش، فقط با دکمه‌های شیشه‌ای انجام می‌شود."
    return f"📖 {bold('راهنمای قلمرو جاودان')}\n\n" + "\n\n".join(_help_block(t, r) for t, r in sections) + "\n\n" + tail


def help_pages(balance) -> dict[str, tuple[str, str]]:  # noqa: ANN001 - Balance
    """Help topics for the glass help panel: ``key -> (button label, page text)``."""

    def page(title: str, *paragraphs: str) -> str:
        return f"{title}\n\n" + "\n\n".join(paragraphs)

    cooldown = duration(balance.boss_cooldown_seconds)
    return {
        "adv": ("🗺️ ماجراجویی", page(
            f"🗺️ {bold('ماجراجویی')}",
            "در گروه بنویسید «ماهیگیری»، «معدن»، «گیاه»، «جستجو» یا «شکار»؛ یا در پیوی از دکمه‌ی ماجراجویی بروید.",
            "هر فعالیت مقداری انرژی می‌خواهد و بین دو بار انجام دادنش کمی باید صبر کنید.",
            "نتیجه با دکمه‌های شیشه‌ای زیر پیام می‌آید: سکه، تجربه، آیتم‌ها و انرژی شما.",
            "انرژی کم شد؟ «استراحت» کنید، معجون انرژی بنوشید یا کمی صبر کنید.",
        )),
        "duel": ("⚔️ دوئل", page(
            f"⚔️ {bold('دوئل با دوستان')}",
            "در گروه روی پیام یک نفر ریپلای کنید و بنویسید «مبارزه».",
            "او دکمه‌ی «قبول» را می‌زند و نبرد نوبتی شروع می‌شود: حمله، مهارت ویژه، دفاع یا تسلیم.",
            "برنده سکه و تجربه می‌گیرد و بازنده هیچ چیزی از دست نمی‌دهد.",
        )),
        "boss": ("🐉 باس گروهی", page(
            f"🐉 {bold('باس گروهی')}",
            f"۱. در گروه بنویسید «احضار باس» (یا «باس»). هزینه‌ی احضار {fa(balance.boss_summon_gold)} سکه است و "
            f"از سطح {fa(balance.boss_min_level)} می‌شود. هر گروه هر {cooldown} یک باس دارد.",
            f"۲. ربات یک پیام ثبت‌نام می‌فرستد. هر کس «⚔️ پیوستن به نبرد» را بزند وارد می‌شود "
            f"(حداقل {fa(balance.boss_min_players)} و حداکثر {fa(balance.boss_max_players)} نفر).",
            "۳. احضارکننده «🚀 شروع نبرد» را می‌زند. اگر زمان ثبت‌نام تمام شود و جنگجوی کافی باشد، خودکار شروع می‌شود.",
            "۴. نبرد خودکار است: هر چند ثانیه همه‌ی جنگجویان بر اساس کلاسشان حمله می‌کنند و باس هم جواب می‌دهد. "
            "ربات هر چند ثانیه گزارش نبرد را روی همان پیام عوض می‌کند.",
            "۵. اگر باس بیفتد، پاداش به نسبت آسیب و محافظت هر نفر تقسیم می‌شود؛ هر که بیشتر زده صندوقچه‌ی بهتری می‌گیرد.",
        )),
        "gear": ("🎒 کوله‌پشتی", page(
            f"🎒 {bold('کوله‌پشتی و تجهیزات')}",
            "«کوله‌پشتی» را بنویسید و تجهیزات یا آیتم‌ها را باز کنید.",
            "روی هر تجهیزات بزنید تا دکمه‌ی پوشیدن، ارتقا، فروش و عرضه در بازار بیاید.",
            "معجون‌ها را همان‌جا مصرف می‌کنید.",
        )),
        "market": ("🏪 بازار و فروشگاه", page(
            f"🏪 {bold('بازار و فروشگاه')}",
            "«فروشگاه»: سلاح، زره و معجون از فروشنده‌ی قلمرو؛ قبل از خرید یک صفحه‌ی تأیید می‌بینید.",
            "«بازار»: آگهی‌های بازیکنان. دسته‌ها را عوض کنید و روی آگهی بزنید تا بخرید.",
            "برای فروش، آیتم را باز کنید و «عرضه در بازار» را بزنید.",
        )),
        "chests": ("🎁 صندوقچه", page(
            f"🎁 {bold('صندوقچه‌ها')}",
            "از ماجراجویی پیدا می‌شوند یا با سکه و کریستال خریده می‌شوند.",
            "قبل از خرید، دکمه‌ی «شانس‌ها» درصد دقیق همه‌ی جایزه‌ها را نشان می‌دهد.",
        )),
        "premium": ("💎 خزانه‌ی ویژه", page(
            f"💎 {bold('خزانه‌ی ویژه')}",
            "بسته‌های سکه، کریستال، سنگ آهن و بسته‌های شانسی روزانه؛ در پیوی ربات.",
            "پرداخت با کیف پول بله است. همه‌چیز را با بازی کردن هم می‌شود به دست آورد.",
        )),
        "hero": ("👤 قهرمان", page(
            f"👤 {bold('قهرمان و پیشرفت')}",
            "«قلمرو» پنل اصلی شماست. «پروفایل» ویژگی‌هایتان را نشان می‌دهد.",
            "با تجربه، سطح بالا می‌روید و انرژی بیشتری می‌گیرید. «جایزه» هر روز سکه می‌دهد.",
            "«انتقال 500» با ریپلای روی پیام یک دوست، به او سکه می‌بخشد.",
        )),
    }


def help_hub() -> str:
    return (
        f"❓ {bold('راهنمای ماجراجو')}\n\n"
        "هر بخش را بزنید تا توضیحش را ببینید 👇"
    )


def help_text() -> str:
    return help_hub()


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


WORKING = {
    "fishing": "🌊 قلاب در آب است... لطفاً صبر کنید",
    "mining": "⛏️ ضربه به ضربه جلو می‌روید... لطفاً صبر کنید",
    "herb": "🌿 لابه‌لای برگ‌ها می‌گردید... لطفاً صبر کنید",
    "search": "🔍 زیر هر سنگ را نگاه می‌کنید... لطفاً صبر کنید",
    "woodcutting": "🪓 تبر بالا و پایین می‌رود... لطفاً صبر کنید",
    "farming": "🌾 خاک را زیر و رو می‌کنید... لطفاً صبر کنید",
    "beekeeping": "🐝 آرام آرام به کندو نزدیک می‌شوید... لطفاً صبر کنید",
    "exploring": "🏺 فانوس را بالا می‌گیرید و جلو می‌روید... لطفاً صبر کنید",
    "performing": "🎻 آرشه روی سیم‌ها می‌رقصد... لطفاً صبر کنید",
}


def _activity_head(name: str, activity) -> str:  # noqa: ANN001 - Activity
    story = activity.intro.format(name=name).split("\n")
    story[0] = story[0].removeprefix(activity.emoji).lstrip()
    return f"{activity.emoji} {bold(activity.title)}\n" + "\n".join(story)


def activity_frames(name: str, activity) -> list[str]:  # noqa: ANN001 - Activity
    """What the player sees while the activity is «in progress»: the story, then a waiting line."""
    head = _activity_head(name, activity)
    return [head, f"{head}\n\n{WORKING.get(activity.id, '⏳ در حال انجام... لطفاً صبر کنید')}"]


def activity_result(name: str, result) -> str:  # noqa: ANN001 - ActivityResult
    """Story and outcome; the numbers (coins, xp, items, energy) are glass buttons below."""
    lines = [
        _activity_head(name, result.activity),
        "",
        emphasize(result.rolled.outcome.text.format(name=name)),
        "",
        DIV,
        f"⏰ {result.activity.title} بعدی: {duration(result.next_in)} دیگر",
        *(["", "✨ ستاره‌ی تجربه فعال است؛ تجربه‌ی این کار دو برابر شد!"] if result.double_xp else []),
        "",
        "🎁 چیزهایی که پیدا کردید یا به دست آوردید 👇",
    ]
    if result.level_up:
        lines += ["", level_up_text(result.level_up.new_level)]
    return "\n".join(lines)


def hunt_frames(name: str, r) -> list[str]:  # noqa: ANN001 - HuntResult
    """Short story told one edit at a time: searching, meeting the monster, the first blows."""
    frames = [
        f"🌲 {bold('در حال شکار')}\nفرمانده {name} در سرزمین‌های وحشی می‌گردد 👣",
        f"{r.monster.emoji} {bold(r.monster.name + ' پیدا شد!')}\nنبرد شروع می‌شود...",
    ]
    for count in (2, 4):
        if len(r.log) >= count:
            frames.append(f"⚔️ {bold('نبرد')}\n\n" + "\n".join(r.log[:count]))
    return frames


def hunt_result(name: str, r) -> str:  # noqa: ANN001 - HuntResult
    lines = [f"{r.monster.emoji} {bold('نبرد با ' + r.monster.name)}", f"فرمانده {name} · {fa(r.rounds)} دور", ""]
    if r.won:
        lines.append(f"🏆 {bold('پیروز شدید')} و هیولا به زانو درآمد.")
    else:
        lines.append(
            f"💔 {bold('این بار هیولا قوی‌تر بود')} و عقب‌نشینی کردید. چیزی از دست ندادید؛ "
            "قوی‌تر شوید و دوباره بیایید!"
        )
    lines += ["", DIV, f"⏰ شکار بعدی: {duration(r.next_in)} دیگر"]
    if r.double_xp:
        lines += ["", "✨ ستاره‌ی تجربه فعال است؛ تجربه‌ی این شکار دو برابر شد!"]
    if r.card is not None:
        lines += ["", f"🃏 {bold('کارت تازه پیدا کردید!')}", f"{r.card.emoji} {r.card.name}"]
    lines += ["", "🎁 چیزهایی که به دست آوردید 👇"]
    if r.level_up:
        lines += ["", level_up_text(r.level_up.new_level)]
    return "\n".join(lines)


# --- upgrades ----------------------------------------------------------------------------------
def upgrade_quote(piece, quote) -> str:  # noqa: ANN001
    from ..game.data.items import get_item

    mats = "، ".join(f"{get_item(i).label} ×{fa(q)}" for i, q in quote.materials.items())
    return (
        f"🔨 {bold('کارگاه آهنگری')}\n"
        f"{piece.item.name} به مرتبه‌ی {bold('+' + fa(quote.next_level))}\n\n"
        f"💰 دستمزد: {fa(quote.gold)} سکه\n"
        f"📦 منابع: {mats}\n"
        f"🎯 شانس موفقیت: {fa(round(quote.chance * 100))}٪\n\n"
        "اگر نشد، فقط منابع از بین می‌رود؛ تجهیزات سالم می‌ماند."
    )


def upgrade_result(result) -> str:  # noqa: ANN001 - UpgradeResult
    if result.success:
        return f"✨ {bold('ارتقا موفق بود')}\n{result.piece.item.name} حالا {bold('+' + fa(result.piece.upgrade))} است."
    return (
        f"💥 {bold('این بار نشد')}\n"
        f"منابع از بین رفت، اما {result.piece.item.name} سالم ماند. دوباره تلاش کنید!"
    )


# --- rankings ----------------------------------------------------------------------------------
def ranking(board, mentions: bool = False) -> str:  # noqa: ANN001 - Board
    if not board.entries:
        return f"{board.title}\n{LINE}\nهنوز کسی در این تالار نیست. اولین شما باشید!"
    medals = ["🥇", "🥈", "🥉"]
    lines = [board.title, LINE]
    for index, entry in enumerate(board.entries):
        place = medals[index] if index < 3 else f"{fa(index + 1)}."
        lines.append(f"{place} {entry.mention if mentions else entry.name} {entry.badge} · سطح {fa(entry.level)} · {fa(entry.value)} {board.unit}")
    if board.my_position:
        lines += [LINE, f"📍 جایگاه شما: {bold(fa(board.my_position))}"]
    return "\n".join(lines)


def battle_history(records) -> str:  # noqa: ANN001 - list[BattleRecord]
    from ..shared.jalali import describe

    title = f"📜 {bold('تاریخچه‌ی نبردها')}"
    if not records:
        return title + "\n\nاین گروه هنوز با هیچ باسی نجنگیده است. بنویسید «باس» و اولین نبرد را بسازید!"
    blocks = [title]
    for r in records:
        date, _, clock = describe(r.ended_at)
        verdict = "🏆 پیروزی" if r.won else "💔 شکست"
        blocks.append(
            f"{r.boss_emoji} {bold(r.boss_name)}\n{verdict} · {fa(r.fighters)} جنگجو\n"
            f"⭐ بیشترین آسیب: {r.top_name} ({fa(r.top_damage)})\n📅 {fa(date)} · {fa(clock)}"
        )
    return "\n\n".join(blocks)


# --- chests ------------------------------------------------------------------------------------
def chest_contents(item, odds) -> str:  # noqa: ANN001
    """What a chest can hold and with which chance (a block for the confirm and detail pages)."""
    from ..game.data.items import get_item

    lines = [f"🎲 {bold('محتویات و شانس‌ها')}"]
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
    lines.append("این‌ها شانس واقعی ربات هستند.")
    return "\n".join(lines)


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


def chest_opening(item) -> str:  # noqa: ANN001
    return f"🗝️ {bold('در حال باز کردن ' + item.name)}\n\nقفل می‌شکند... لطفاً صبر کنید ✨"


def lucky_odds(theme) -> str:  # noqa: ANN001 - Theme
    from ..game.data import lucky
    from ..game.data.items import get_item

    lines = [f"🎲 {bold('شانس‌های بسته‌ی شانسی امروز')}", f"تم امروز: {theme.emoji} {theme.name}", LINE]
    for prize, share in sorted(lucky.odds(theme), key=lambda x: -x[1]):
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
    lines += [LINE, "هر بسته سکه‌ی تضمینی دارد و جایزه‌ها از همین فهرست انتخاب می‌شوند. فردا تم عوض می‌شود."]
    return "\n".join(lines)


def upgrade_working() -> str:
    return f"🔨 {bold('آهنگر در کار است')}\n\nچکش بالا می‌رود... لطفاً صبر کنید ✨"


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
def pack_description(pack, now: int | None = None) -> str:  # noqa: ANN001 - Pack
    from ..game.data import lucky
    from ..game.data.items import get_item

    if pack.lucky:
        import time

        theme = lucky.theme_of_day(now if now is not None else int(time.time()))
        tier = lucky.TIERS[pack.id]
        return (
            f"شامل: {fa(tier.guaranteed_gold)} سکه‌ی تضمینی + {fa(tier.rolls)} جایزه‌ی تصادفی "
            f"از تم «{theme.name}»"
        )
    parts = []
    if pack.gold:
        parts.append(f"{fa(pack.gold)} سکه")
    if pack.crystal:
        parts.append(f"{fa(pack.crystal)} کریستال")
    parts += [f"{get_item(i).name} ×{fa(q)}" for i, q in pack.items.items()]
    if pack.season:
        return (
            "شامل: بلیط طلایی این فصل.\nجایزه‌های ویژه‌ی همه‌ی مرحله‌ها برایتان باز شد؛ "
            "از «قهرمان من ← مسیر قهرمانی» دریافتشان کنید."
        )
    if pack.vip_days:
        return (
            f"شامل: {fa(pack.vip_days)} روز اشتراک VIP.\n"
            "انتظار فعالیت‌ها کوتاه‌تر شد، مأموریت چهارم و امتیاز بیشتر در مسیر قهرمانی هم دارید."
        )
    if pack.pet:
        from ..game.data.pets import get_pet

        pet = get_pet(pack.pet)
        return f"شامل: حیوان خانگی {pet.emoji} {pet.name}.\nاز «حیوان خانگی» می‌توانید همراه خود کنیدش."
    return "شامل: " + " + ".join(parts)


def delivery(order, granted: str = "") -> str:  # noqa: ANN001 - Order
    body = f"🎲 این‌ها از بسته درآمد:\n{granted}" if granted else pack_description(order.pack)
    return (
        f"✅ {bold('پرداخت موفق بود')}\n"
        f"{order.pack.label} به گنجینه‌ی شما رسید.\n\n{body}\n\n"
        "سپاس از حمایت شما 💛"
    )


SECTION_NAMES = {
    "coins": "بسته‌ی سکه", "crystals": "بسته‌ی کریستال", "bundles": "بسته‌ی ویژه",
    "materials": "منابع", "lucky": "بسته‌ی شانسی روزانه", "deal": "تخفیف روز",
}


def discount_note(pack, amount: int) -> str:  # noqa: ANN001 - Pack
    percent = round(100 * (1 - amount / pack.price_rial))
    return f"{fa(percent)}٪ تخفیف"


def deals_text(deals, seconds_left: int) -> str:  # noqa: ANN001
    lines = [
        f"🏷️ {bold('تخفیف‌های امروز')}",
        "",
        f"فقط تا پایان امروز (به وقت تهران)؛ {duration(seconds_left)} دیگر. فردا فهرست تازه می‌آید.",
        "",
    ]
    for deal in deals:
        pack = deal.pack
        lines += [
            f"• {pack.label} — {bold(fa(deal.percent) + '٪ تخفیف')}",
            f"   قبلاً {fa(pack.price_toman)} تومان ← اکنون {bold(fa(deal.price_toman))} تومان",
            f"   {pack_description(pack)}",
            "",
        ]
    lines.append("پس از زدن، فاکتور پرداخت بله برایتان می‌آید.")
    return "\n".join(lines)


def sale_report(order, player, user, charge_id, when: int, totals, granted: str = "") -> str:  # noqa: ANN001
    """The message the bot owner receives after every successful sale."""
    from ..shared.jalali import describe

    date, weekday, clock = describe(when)
    pack = order.pack
    username = f"@{user.username}" if user.username else "ندارد"
    return "\n".join(
        [
            f"💰 {bold('فروش جدید')}",
            "",
            f"🧾 سفارش: {fa(order.id)}",
            f"📅 تاریخ: {fa(date)} · {weekday}",
            f"🕒 ساعت: {fa(clock)} (به وقت تهران)",
            "",
            f"📦 محصول: {pack.label}",
            f"🏷️ نوع: {SECTION_NAMES.get(pack.section, pack.section)}",
            f"🎁 {pack_description(pack, when)}",
            *(["🎲 محتوای تصادفی:", granted] if granted else []),
            f"💵 مبلغ: {bold(fa(order.amount // 10))} تومان ({fa(order.amount)} ریال)",
            *([f"🏷️ با تخفیف: {discount_note(pack, order.amount)} (قیمت عادی {fa(pack.price_toman)} تومان)"]
              if order.amount < pack.price_rial else []),
            "",
            f"👤 خریدار: {bold(player.name)}",
            f"🎮 سطح {fa(player.level)} · {player.race.name} · {player.char_class.name}",
            f"🪙 {fa(player.gold)} سکه · 💎 {fa(player.crystal)} کریستال",
            f"🆔 شناسه بله: {fa(user.id)}",
            f"🔗 نام کاربری: {username}",
            f"💳 کد پیگیری: {charge_id or 'ندارد'}",
            "",
            DIV,
            f"📊 جمع فروش: {fa(totals.orders)} سفارش · {fa(totals.revenue_rial // 10)} تومان",
        ]
    )


# --- group boss --------------------------------------------------------------------------------
MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]


def _clock(seconds: int) -> str:
    minutes, sec = divmod(max(0, seconds), 60)
    return fa(f"{minutes:02d}:{sec:02d}")


def boss_recruiting(v, min_players: int, max_players: int) -> str:  # noqa: ANN001 - BossView
    roster = "\n".join(f"{f.emoji} {f.mention}" for f in v.fighters)
    return "\n".join(
        [
            f"{v.type.emoji} {bold(v.type.name + ' بیدار شده است!')}",
            "",
            v.type.story,
            "فرمانده، متحدان خود را فرا بخوانید!",
            "",
            f"🔮 عنصر: {v.type.element.emoji} {v.type.element.noun} · نقطه‌ضعف: کلاس {CLASSES[v.type.weak_class].name}",
            *(
                ["🌑 باس مخفی خودش وارد گروه شد! هر جنگجو می‌تواند نبرد را شروع کند."]
                if v.free
                else [f"👤 احضارکننده: {v.summoner_mention}"]
            ),
            f"👥 جنگجویان: {bold(fa(len(v.fighters)))} / {fa(max_players)} (حداقل {fa(min_players)})",
            f"⏳ زمان ثبت‌نام: {_clock(v.seconds_left)}",
            "❤️ جان باس با تعداد جنگجویان بیشتر می‌شود.",
            "",
            f"🛡️ {bold('در صف نبرد')}",
            roster,
            "",
            "همه‌ی جنگجویان «پیوستن» را بزنند؛ احضارکننده نبرد را شروع می‌کند 👇",
        ]
    )


def boss_fight(v) -> str:  # noqa: ANN001 - BossView
    percent = round(100 * v.hp / v.max_hp) if v.max_hp else 0
    lines = [
        f"⚔️ {bold('نبرد با ' + v.type.name)}",
        "",
        f"❤️ سلامتی باس: {fa(v.hp)} / {fa(v.max_hp)}",
        f"{bar(v.hp, v.max_hp, 10)}  {fa(percent)}٪",
        f"👥 جنگجویان زنده: {fa(v.alive_count)} / {fa(len(v.fighters))} · دور {fa(v.round)}",
        f"⏳ زمان باقی‌مانده: {_clock(v.seconds_left)}",
    ]
    if v.report:
        lines += ["", f"📜 {bold('گزارش نبرد')}", *v.report]
    ranked = sorted(v.fighters, key=lambda f: -f.damage)[:3]
    if ranked and ranked[0].damage:
        lines += ["", f"🏅 {bold('بیشترین آسیب')}"]
        lines += [f"{MEDALS[i]} {f.mention} — {fa(f.damage)}" for i, f in enumerate(ranked)]
    lines += ["", "🤖 نبرد خودکار است؛ فقط تماشا کنید و تشویق کنید!"]
    return "\n".join(lines)


def boss_started(v) -> str:  # noqa: ANN001 - BossView
    return (
        f"🚀 {bold('نبرد آغاز شد!')}\n\n"
        f"{fa(len(v.fighters))} جنگجو در برابر {v.type.emoji} {bold(v.type.name)} صف کشیدند. "
        f"زمین می‌لرزد و شمشیرها از نیام بیرون آمده‌اند.\n\n"
        f"🧠 ویژگی باس: {behavior_of(v.type)[1]}\n\n"
        f"👀 لحظه‌ای تماشا می‌کنیم...\n\n" + boss_fight(v)
    )


def boss_final(v) -> str:  # noqa: ANN001 - BossView
    if v.outcome == "cancelled":
        return (
            f"🌫️ {bold('احضار ناکام ماند')}\n\n"
            f"{v.type.name} بدون نبرد به خواب برگشت؛ جنگجوی کافی نیامد.\n\n"
            "💰 سکه‌ی احضار به احضارکننده برگشت."
        )
    heads = {
        "won": f"🏆 {bold(v.type.name + ' شکست خورد!')}\n\nجنگجویان قلمرو پیروز شدند و غریو شادی بلند شد.",
        "lost": f"💀 {bold('همه‌ی جنگجویان از پا افتادند')}\n\n{v.type.name} پیروز میدان شد؛ ولی تلاشتان بی‌پاداش نماند.",
        "fled": f"⌛ {bold(v.type.name + ' گریخت')}\n\nزمان تمام شد و باس ناپدید شد؛ ولی تلاشتان بی‌پاداش نماند.",
    }
    blocks = [heads.get(v.outcome or "fled", heads["fled"]), f"📊 {bold('نتیجه‌ی نبرد')}\n{fa(v.round)} دور · {fa(len(v.fighters))} جنگجو"]
    if not v.payouts:
        blocks.append("هیچ‌کس در نبرد نبود.")
    else:
        blocks.append(f"🏅 {bold('سهم هر جنگجو')}")
    for i, p in enumerate(v.payouts):
        medal = MEDALS[i] if i < len(MEDALS) else "🔹"
        entry = [f"{medal} {p.mention} — {fa(p.damage)} آسیب ({fa(round(p.share * 100))}٪)"]
        if p.level_up:
            entry.append(f"🎉 رسید به سطح {fa(p.level_up)}")
        if p.trophy:
            entry.append(f"🏆 غنیمت ویژه: {get_item(p.trophy).label}")
        if p.card:
            entry.append(f"🃏 کارت تازه: {p.card}")
        blocks.append("\n".join(entry))
    blocks.append("🪙 پاداش هر نفر در دکمه‌های زیر است 👇")
    return "\n\n".join(blocks)


# --- random group events --------------------------------------------------------------------------
def event_text(view) -> str:  # noqa: ANN001 - EventView
    from ..game.data.items import get_item

    st = view.state
    if view.kind == "mystery_chest":
        if view.status == "done":
            prize = get_item(st["prize"])
            return (
                f"🎉 {bold('صندوقچه گشوده شد!')}\n\n"
                f"{st['mention']} رمز را کشف کرد و {prize.label} را برد.\n\n"
                f"🔑 تلاش‌ها: {fa(st['attempts'])}"
            )
        if view.status == "expired":
            return (
                f"⌛ {bold('صندوقچه برای همیشه بسته ماند')}\n\n"
                "کسی نتوانست رمزش را کشف کند و کاروان از دور خارج شد."
            )
        return (
            f"🎁 {bold('صندوقچه‌ی اسرارآمیز پیدا شد!')}\n\n"
            "در دل مه و تاریکی، کاروانی سلطنتی غافلگیر شد و فقط یک صندوقچه‌ی قفل‌شده از آن به‌جا مانده است. "
            "نقش‌های درخشانی روی قفلش می‌چرخد و هنوز هیچ دستی رمزش را نشکسته.\n\n"
            "هر کس می‌تواند شانسش را امتحان کند؛ اما فقط یک نفر برنده است. هر تلاش، قفل را کمی سست‌تر می‌کند!\n\n"
            f"🔑 تلاش‌ها تا الان: {fa(st['attempts'])}\n\n"
            f"⏳ مهلت: {_clock(view.seconds_left)}\n\n"
            "🎲 جایزه: یکی از صندوقچه‌های چوبی، جادویی یا (با شانس کم) سلطنتی\n\n"
            "زودتر دست به کار شوید 👇"
        )
    if view.kind == "merchant":
        lines = [f"🧳 {bold('تاجر دوره‌گرد رسید!')}", ""]
        if view.status == "active":
            lines += ["کاروانش را در این منطقه پهن کرده و کالاهای محدودش را ارزان می‌فروشد.", ""]
        else:
            lines += ["تاجر کاروانش را جمع کرد و رفت. شاید دفعه‌ی بعد!", ""]
        for entry in st["stock"]:
            item = get_item(entry["item"])
            left = f"{fa(entry['left'])} عدد مانده" if entry["left"] > 0 else "تمام شد"
            lines += [f"• {item.label} — {fa(entry['price'])} 🪙", f"   {left}", ""]
        if view.status == "active":
            lines.append(f"⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}")
            lines.append("هر کس زودتر بزند، می‌خرد 👇")
        return "\n".join(lines)
    if view.kind == "double_xp":
        if view.status == "active":
            return (
                f"✨ {bold('ستاره‌ی تجربه در آسمان!')}\n\n"
                f"تا {duration(view.seconds_left)} دیگر، همه‌ی ماجراجویی‌ها و شکارهای این گروه "
                f"{bold('دو برابر')} تجربه می‌دهند.\n\nهمین حالا به میدان بروید!"
            )
        return f"🌙 {bold('ستاره‌ی تجربه محو شد')}\n\nتجربه‌ی دوبرابر تمام شد."
    return f"{view.kind}"


def events_overview(views_, double_xp: bool) -> str:  # noqa: ANN001
    lines = [f"🎲 {bold('رویدادهای گروه')}", ""]
    if views_:
        for v in views_:
            label = {"mystery_chest": "🎁 صندوقچه‌ی اسرارآمیز", "merchant": "🧳 تاجر دوره‌گرد",
                     "double_xp": "✨ تجربه‌ی دوبرابر"}.get(v.kind, v.kind)
            lines.append(f"• {label} — {duration(v.seconds_left)} مانده")
        lines.append("")
    else:
        lines += ["الان رویدادی در جریان نیست.", ""]
    lines += [
        "ربات گاهی خودش در گروه‌های فعال اتفاق می‌اندازد: صندوقچه‌ی اسرارآمیز، تاجر دوره‌گرد، "
        "ستاره‌ی تجربه و باس مخفی.",
        "",
        "مدیران گروه با «غیرفعال رویدادها» می‌توانند آن‌ها را خاموش کنند.",
    ]
    return "\n".join(lines)


def welcome_back(player) -> str:  # noqa: ANN001 - Player
    return (
        f"🛡️ {bold('ورود یک قهرمان')}\n\n"
        f"{player.mention} با نام‌آوری وارد گروه شد!\n"
        f"{player.race.emoji} {player.race.name} · {player.char_class.emoji} {player.char_class.name} · "
        f"سطح {fa(player.level)}\n"
        f"🏆 {fa(player.wins)} پیروزی در دوئل"
    )


# --- duels -------------------------------------------------------------------------------------
def duel_invite(challenger, target, seconds: int) -> str:  # noqa: ANN001 - Player
    return (
        f"⚔️ {bold('فراخوان دوئل')}\n\n"
        f"{challenger.char_class.emoji} {challenger.mention} · سطح {fa(challenger.level)}\n"
        f"🏆 {fa(challenger.wins)} پیروزی · 💀 {fa(challenger.losses)} شکست\n\n"
        f"فرمانده {target.mention} ، دعوت را می‌پذیرید؟\n"
        f"⏳ {duration(seconds)} فرصت دارید."
    )


def _hp_block(f) -> str:  # noqa: ANN001 - Fighter
    percent = round(100 * max(f.hp, 0) / f.max_hp) if f.max_hp else 0
    return (
        f"{f.emoji} {f.mention or bold(f.name)}\n"
        f"❤️ {fa(max(f.hp, 0))} از {fa(f.max_hp)}\n"
        f"{bar(f.hp, f.max_hp, 10)}  {fa(percent)}٪"
    )


def _hp_line(f) -> str:  # noqa: ANN001 - Fighter
    return _hp_block(f)


def duel_status(battle, lines: list[str], turn_seconds: int) -> str:  # noqa: ANN001 - Battle
    a, b = battle.fighters
    blocks = [f"⚔️ {bold('میدان نبرد')}", _hp_block(a), _hp_block(b)]
    story = [line for line in lines if line.strip()]
    if story:
        blocks.append("\n".join(story))
    if not battle.finished:
        blocks.append(
            f"🎯 نوبت {battle.current.mention or bold(battle.current.name)}\n"
            f"🔁 دور {fa(battle.round)} از {fa(battle.max_rounds)}\n"
            f"⏳ {duration(turn_seconds)} فرصت دارید."
        )
    return "\n\n".join(blocks)


def duel_result(update) -> str:  # noqa: ANN001 - DuelUpdate
    battle = update.battle
    a, b = battle.fighters
    blocks = [f"🏁 {bold('پایان نبرد')}", _hp_block(a), _hp_block(b)]
    story = [line for line in update.lines if line.strip()]
    if story:
        blocks.append("\n".join(story))
    if battle.winner is None:
        blocks.append("🤝 مساوی شد؛ هر دو دلاور بودند!")
    else:
        winner = battle.fighters[battle.winner]
        blocks.append(f"🏆 برنده: {winner.mention or bold(winner.name)}")
    for fighter in battle.fighters:
        payout = update.payouts.get(fighter.player_id)
        if payout is None:
            continue
        gains = []
        if payout.gold:
            gains.append(f"{fa(payout.gold)} سکه")
        if payout.xp:
            gains.append(f"{fa(payout.xp)} تجربه")
        line = f"{fighter.mention or fighter.name}: " + (" و ".join(gains) if gains else "سقف پاداش امروز پر است")
        if payout.rating:
            league = league_of(payout.rating)
            sign = "+" if payout.rating_delta >= 0 else "-"
            line += f"\n{league.emoji} لیگ {league.name} · {fa(payout.rating)} امتیاز ({sign}{fa(abs(payout.rating_delta))})"
        if payout.level_up:
            line += f"\n🎉 رسید به سطح {fa(payout.level_up.new_level)}"
        blocks.append(line)
    return "\n\n".join(blocks)
