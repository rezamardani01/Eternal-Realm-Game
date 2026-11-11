"""Text rendering.

Rules of the house: every message starts with exactly ONE emoji, titles and key numbers are
bold (single ``*`` markers, the only bold Bale understands), each stat sits on its own
line, and the voice is a friendly epic storyteller in simple formal Persian.
"""

from __future__ import annotations

from ..game.data.bosses import behavior_of, tier_by_id
from ..game.data.classes import CLASSES
from ..game.data.items import get_item
from ..game.data.leagues import league_of
from ..game.data.races import RACES, Race
from ..game.data.stats import Stats
from ..game.models import Player
from ..shared.text import bar, bold, duration, emphasize, fa

_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
LINE = "━━━━━━━━━━━━"
MEDAL_ICONS = ("🥇", "🥈", "🥉")


def tidy_list(entries: list[tuple[str, list[str]]], limit: int = 8, ranked: bool = True) -> list[str]:
    """A name on one line and what they got on the next, with a blank line between people:

        🥇 [آرش]
        🪙 ۷۱۵ · 💎 ۲ · 🎁 صندوقچه جادویی
    """
    lines: list[str] = []
    for index, (name, gains) in enumerate(entries[:limit]):
        icon = MEDAL_ICONS[index] if ranked and index < len(MEDAL_ICONS) else "🔹"
        lines.append(f"{icon} {name}")
        if gains:
            lines.append(" · ".join(gains))
        lines.append("")
    if len(entries) > limit:
        lines.append(f"و {fa(len(entries) - limit)} نفر دیگر")
    elif lines:
        lines.pop()  # no blank line after the last person
    return lines
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


def backpack_section(item) -> str:  # noqa: ANN001 - Item
    """Where in «کوله‌پشتی» an item shows up."""
    from ..game.data.items import Kind

    if item.is_gear:
        return "⚔️ تجهیزات"
    if item.kind is Kind.CHEST:
        return "🎁 صندوقچه‌ها"
    return "📦 آیتم‌ها"


def streak_note(reward) -> str:  # noqa: ANN001 - DailyReward
    """The «days in a row» lines of the daily reward: the streak, a chest when one was paid and what comes next."""
    if reward.streak < 2 and not reward.chest and not reward.crystal:
        return ""
    from ..game.data.items import get_item

    lines = [f"🔥 {fa(reward.streak)} روز پشت‌سرهم!"]
    if reward.chest:
        lines.append(f"🎁 پاداش زنجیره: {get_item(reward.chest).label}")
    if reward.crystal:
        lines.append(f"💎 هدیه‌ی یک هفته پشت‌سرهم: {fa(reward.crystal)} کریستال")
    lines.append(f"⏳ تا صندوقچه‌ی بعدی: {fa(reward.next_chest_in)} روز (هر روز بیایید تا زنجیره نشکند)")
    return "\n".join(lines)


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
        + (f"🎖️ خان‌پوینت: {fa(player.khan_points)}\n" if player.khan_points else "")
        + (f"🚀 بوست دو برابر فعال · {duration(player.boost_until - now)} مانده\n" if player.boost_until > now > 0 else "")
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
        ("🎣 ماهیگیری", "ماهی، گنج و گاهی کریستال"),
        ("⛏️ معدن", "سنگ، آهن، طلا و پاره‌کریستال"),
        ("🌿 گیاه", "گیاه‌های شفابخش و کمیاب"),
        ("🔍 جستجو", "سکه، معجون و صندوقچه‌ی پنهان"),
        ("🪓 هیزم", "چوب درخت"),
        ("🌾 کشاورزی", "گندم و محصول مزرعه"),
        ("🐝 زنبورداری", "عسل طلایی"),
        ("🏺 کاوش", "سکه‌ی باستانی و طومار"),
        ("🎻 هنرنمایی", "سکه از تماشاگران"),
        ("🐺 شکار", "جنگ با هیولا برای تجربه و غنیمت"),
        ("😴 استراحت", "انرژی برمی‌گردد (هر ۳۰ دقیقه)"),
        ("🗺️ ماجراجویی", "همه‌ی فعالیت‌ها با دکمه"),
    ]),
    ("⚔️ مبارزه", [
        ("⚔️ مبارزه", "روی پیام یک نفر ریپلای کنید؛ دوئل نوبتی با دکمه"),
        ("🎰 مبارزه شرطی", "شرط سر سکه، کریستال، منابع یا آیتم؛ برنده همه‌چیز را می‌برد"),
    ]),
    ("🐉 باس، رویداد و سیاه‌چال", [
        ("🐉 باس", "احضار باس گروهی؛ همه می‌پیوندند و نبرد خودکار است"),
        ("🎲 رویدادها", "صندوقچه، تاجر، باران سکه، تخم اژدها و..."),
        ("🕳️ سیاه‌چال", "تک‌نفره؛ با دوستان: «سیاه‌چال گروهی»"),
        ("📜 داستان", "داستان‌های انتخابی با پاداش"),
    ]),
    ("🎒 کوله‌پشتی و بازار", [
        ("🎒 کوله‌پشتی", "آیتم‌ها و تجهیزات؛ پوشیدن و ارتقا"),
        ("🎁 صندوقچه", "خرید، باز کردن و دیدن شانس‌ها"),
        ("🛒 فروشگاه", "سلاح، زره و معجون"),
        ("🏪 بازار", "خرید و فروش با بازیکنان دیگر"),
        ("🔥 کوره", "ساخت تجهیزات افسانه‌ای"),
        ("💎 خزانه قلمرو", "بسته‌های سکه، کریستال، بوست و تجربه (در پیوی)"),
    ]),
    ("👤 قهرمان", [
        ("🏰 قلمرو", "منوی اصلی با دکمه‌ها"),
        ("👤 پروفایل", "ویژگی‌های شما"),
        ("🎁 جایزه", "گنجینه‌ی روزانه؛ هر ۷ روز پشت‌سرهم یک صندوقچه"),
        ("📅 مأموریت‌ها", "مأموریت‌های شخصی امروز"),
        ("💸 انتقال 500", "با ریپلای روی پیام دوستتان سکه می‌بخشید"),
        ("🏆 رتبه", "برترین‌های گروه و کل قلمرو"),
        ("🏯 خاندان", "با دوستان یک خاندان بسازید"),
        ("🃏 آلبوم", "کارت‌های جمع‌آوری‌شده"),
        ("🐱 حیوان", "همراهی که قدرت می‌دهد"),
        ("🕯️ محراب", "دعا برای برکت"),
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
    if in_group:
        tail += "\n\n🗝️ در گروه فقط ماجراجویی، احضار باس، مبارزه‌ها، انتقال و پروفایل کار می‌کند؛ فروشگاه، کوله‌پشتی، خاندان و بقیه‌ی بخش‌ها در پیوی ربات است."
    return f"📖 {bold('راهنمای قلمرو جاودان')}\n\n" + "\n\n".join(_help_block(t, r) for t, r in sections) + "\n\n" + tail


def help_pages(balance) -> dict[str, tuple[str, str]]:  # noqa: ANN001 - Balance
    """Help topics for the glass help panel: ``key -> (button label, page text)``."""

    def page(title: str, *blocks: str) -> str:
        return f"{title}\n\n" + "\n\n".join(blocks)

    cooldown = duration(balance.boss_cooldown_seconds)
    return {
        "adv": ("🗺️ ماجراجویی", page(
            f"🗺️ {bold('ماجراجویی')}",
            "🌍 در گروه اسم یک فعالیت را بنویسید یا در پیوی «ماجراجویی» را بزنید:\n"
            "🎣 ماهیگیری · ⛏️ معدن · 🌿 گیاه · 🔍 جستجو\n🪓 هیزم · 🌾 کشاورزی · 🐝 زنبورداری · 🏺 کاوش · 🎻 هنرنمایی",
            "🐺 «شکار» با هیولا می‌جنگد و تجربه و غنیمت می‌دهد.",
            "⚡ هر فعالیت انرژی می‌خواهد.\n⏰ بین دو بار انجام دادن کمی صبر کنید؛ در طول روز این مکث بیشتر می‌شود و نیمه‌شب از نو شروع می‌شود.",
            "🎁 نتیجه (سکه، تجربه، آیتم) با دکمه‌های شیشه‌ای زیر پیام می‌آید.\n😴 انرژی کم شد؟ «استراحت» کنید یا معجون انرژی بنوشید.",
        )),
        "trip": ("🧭 سفر قهرمان", page(
            f"🧭 {bold('سفر قهرمان (تک‌نفره)')}",
            "🥊 «میدان بات‌ها» حریف‌های ساخته‌ی ربات با چهار سطح سختی؛ هر وقت خواستید.",
            "📖 «داستان» بیست مرحله در چهار فصل دارد؛ راه خود را انتخاب می‌کنید و باس هر فصل پاداش ویژه دارد.",
            "🏚️ «دخمه‌های روزانه» هر روز سه دخمه‌ی پنج‌طبقه؛ هر طبقه پاداش دارد.",
            "🐉 «باس‌های تک‌نفره» هر کدام ترفندی دارند؛ هشدار نبرد را بخوانید و درست دفاع کنید.",
            "🎲 «گشت‌زنی» اتفاق‌های تصادفی در راه است: کمک به مسافر، صندوق گنج، راهزن و تاجر مرموز.",
            "⚡ این بخش‌ها انرژی می‌خواهند اما هیچ‌کدام به پول واقعی یا حضور بازیکن دیگر نیاز ندارند.",
        )),
        "duel": ("⚔️ دوئل", page(
            f"⚔️ {bold('دوئل با دوستان')}",
            "1️⃣ روی پیام یک نفر ریپلای کنید و بنویسید «مبارزه».",
            "2️⃣ او «قبول» را می‌زند و نبرد نوبتی شروع می‌شود: حمله، مهارت ویژه، دفاع یا تسلیم.",
            "🏆 برنده سکه، تجربه و امتیاز لیگ می‌گیرد.\n💔 بازنده چیزی از دست نمی‌دهد.",
        )),
        "bet": ("🎰 مبارزه شرطی", page(
            f"🎰 {bold('مبارزه شرطی')}",
            "1️⃣ در گروه بنویسید «مبارزه شرطی».\n2️⃣ انتخاب کنید سر چه چیزی شرط می‌بندید: 🪙 سکه، 💎 کریستال، ⛓️ منابع یا ⚔️ آیتم.",
            "3️⃣ پیام انتظار می‌آید و هر کس شرط را قبول کند، همان لحظه وارد دوئل می‌شود.",
            "💰 هر دو طرف باید همان مقدار را داشته باشند و برنده همه‌چیز را می‌برد (۵٪ کارمزد روی سکه و کریستال).",
            "🎁 روی آیتم: حریف لازم نیست همان آیتم را داشته باشد؛ دو برابر ارزش آیتم سکه یا کمی کریستال می‌پردازد.",
            "↩️ شرط بی‌پاسخ، لغو یا مساوی برمی‌گردد.",
        )),
        "boss": ("🐉 باس گروهی", page(
            f"🐉 {bold('باس گروهی')}",
            f"1️⃣ بنویسید «احضار باس».\n💰 هزینه {fa(balance.boss_summon_gold)} سکه · از سطح {fa(balance.boss_min_level)}\n"
            f"⏳ هر گروه هر {cooldown} یک باس",
            f"2️⃣ همه «⚔️ پیوستن به نبرد» را می‌زنند.\n👥 از {fa(balance.boss_min_players)} تا {fa(balance.boss_max_players)} نفر",
            "3️⃣ احضارکننده «🚀 شروع نبرد» را می‌زند؛ با تمام شدن زمان ثبت‌نام هم خودکار شروع می‌شود.",
            "4️⃣ نبرد خودکار است و گزارشش روی همان پیام عوض می‌شود.\n"
            "🎲 قدرت هر باس شانسی است: بعضی ضعیف‌اند و بعضی افسانه‌ای.",
            "5️⃣ اگر باس بیفتد، پاداش به نسبت سهم هر نفر تقسیم می‌شود.\n"
            "🔥 اگر ببازید، تا ۲۴ ساعت می‌توانید انتقام بگیرید.",
        )),
        "events": ("🎲 رویدادها", page(
            f"🎲 {bold('رویدادهای گروه')}",
            "ربات گاهی خودش در گروه‌های فعال اتفاق می‌اندازد؛ هرچه گروه فعال‌تر باشد، بیشتر و بزرگ‌تر.",
            "🎁 صندوقچه‌ی اسرارآمیز · 🗝️ صندوقچه‌ی مخفی (با سرنخ)\n🧳 تاجر دوره‌گرد · ✨ تجربه‌ی دوبرابر · 🌑 باس مخفی",
            "🚨 تهاجم هیولاها (همه با هم دفاع می‌کنند) · ☄️ شهاب‌سنگ\n🌧️ باران سکه · 💧 چشمه‌ی برکت · 🎡 چرخ شانس · 🥚 تخم اژدها\n🧠 معما · 🔲 کاشی‌های شانس · 🎟️ قرعه‌کشی بزرگ",
            "👇 هر رویداد دکمه‌ی خودش را دارد؛ فقط همان را بزنید.\n📋 «رویدادها» وضعیت همین گروه را نشان می‌دهد.",
        )),
        "gear": ("🎒 کوله‌پشتی", page(
            f"🎒 {bold('کوله‌پشتی و تجهیزات')}",
            "«کوله‌پشتی» را بنویسید؛ سه بخش دارد:\n⚔️ تجهیزات (سلاح، زره، انگشتر...)\n📦 آیتم‌ها (معجون و منابع)\n🎁 صندوقچه‌ها",
            "روی هر تجهیزات بزنید تا دکمه‌ی پوشیدن، ارتقا، فروش و عرضه در بازار بیاید.",
            "🧪 معجون‌ها را همان‌جا مصرف می‌کنید.\n🔥 در «کوره» از منابع، تجهیزات افسانه‌ای می‌سازید.",
        )),
        "market": ("🏪 بازار و فروشگاه", page(
            f"🏪 {bold('بازار و فروشگاه')}",
            "🛒 «فروشگاه»: سلاح، زره و معجون از فروشنده‌ی قلمرو؛ قبل از خرید صفحه‌ی تأیید می‌بینید.",
            "🏪 «بازار»: آگهی‌های بازیکنان. دسته و ترتیب را عوض کنید و روی آگهی بزنید تا بخرید.",
            "🏷️ برای فروش، آیتم را باز کنید و «عرضه در بازار» را بزنید؛ قیمت را می‌نویسید و قبل از ثبت ارزش واقعی آیتم را مقایسه می‌کنید.",
        )),
        "chests": ("🎁 صندوقچه", page(
            f"🎁 {bold('صندوقچه‌ها')}",
            "از ماجراجویی و رویدادها پیدا می‌شوند یا با سکه و کریستال خریده می‌شوند.",
            "🎲 قبل از خرید، دکمه‌ی «شانس‌ها» درصد دقیق همه‌ی جایزه‌ها را نشان می‌دهد.",
        )),
        "premium": ("💎 خزانه قلمرو", page(
            f"💎 {bold('خزانه قلمرو')}",
            "در پیوی ربات: بسته‌های سکه، کریستال، سنگ آهن، حیوان همراه، بسته‌های شانسی و اشتراک VIP.",
            "💳 پرداخت با کیف پول بله است. همه‌چیز را با بازی کردن هم می‌شود به دست آورد.",
        )),
        "hero": ("👤 قهرمان", page(
            f"👤 {bold('قهرمان و پیشرفت')}",
            "🏰 «قلمرو» پنل اصلی شماست؛ «پروفایل» ویژگی‌هایتان را نشان می‌دهد.",
            "⭐ با تجربه، سطح بالا می‌روید و انرژی بیشتری می‌گیرید.\n🎁 «جایزه» هر روز سکه می‌دهد و هر ۷ روز پشت‌سرهم یک صندوقچه هم دارد.",
            "💸 «انتقال 500» با ریپلای روی پیام یک دوست، به او سکه می‌بخشد؛ بعدش می‌توانید آیتم دیگری هم بفرستید.",
            "🏆 «رتبه» برترین‌ها را نشان می‌دهد.",
        )),
        "pets": ("🐱 حیوان و کارت", page(
            f"🐱 {bold('حیوان خانگی و کارت')}",
            "🐾 «حیوان»: همراهی که کمی قدرت می‌دهد و در نبرد گاهی حمله می‌کند. حیوان‌های معمولی با سکه، قوی‌ترها از خزانه قلمرو (افسانه‌ای‌ها فقط از آنجا) خریده می‌شوند. با کریستال ارتقا می‌خورند.",
            "🃏 «آلبوم»: از شکار و باس کارت پیدا می‌کنید، مجموعه کامل می‌کنید و جایزه می‌گیرید. بسته‌ی کارت هم می‌شود خرید.",
            "♻️ کارت تکراری را می‌شود به بازارچه فروخت یا به دوستان بخشید.",
        )),
        "clan": ("🏯 خاندان", page(
            f"🏯 {bold('خاندان')}",
            "🏗️ بنویسید «ساخت خاندان نام‌دلخواه» یا به یک خاندان باز بپیوندید.",
            "💰 اعضا به خزانه‌ی مشترک کمک می‌کنند و خاندان بالا می‌رود.\n⚔️ به خاندان‌های دیگر اعلام جنگ کنید و دژهایشان را بگیرید.\n🏅 دوئل، باس و ستاره‌های جنگ برای «لیگ هفتگی» امتیاز می‌آورد.",
            "👑 مالک و قائم‌مقام‌ها عضو می‌پذیرند؛ از پنل خاندان همه‌چیز با دکمه است.",
        )),
        "progress": ("📅 مأموریت و مسیر", page(
            f"📅 {bold('مأموریت و مسیر قهرمانی')}",
            "📅 «مأموریت‌ها»: هر روز چند مأموریت شخصی دارید؛ انجامشان بدهید و پاداش را بگیرید.",
            "🎟️ «مسیر قهرمانی»: با هر کاری امتیاز می‌گیرید و مرحله‌ها باز می‌شوند. جایزه‌های رایگان برای همه است.",
            "🏁 مسابقه‌های هفتگی و 🕯️ محراب هم در منوی اصلی هستند.",
        )),
        "quests": ("📜 داستان و سیاه‌چال", page(
            f"📜 {bold('داستان و سیاه‌چال')}",
            "📜 «داستان»: ۱۰ فصل داستان انتخابی؛ هر انتخاب پایان و پاداش را عوض می‌کند. فصل‌ها با سطح باز می‌شوند.",
            "🕳️ «سیاه‌چال»: پنج اتاق و یک نگهبان؛ با انرژی تنها می‌روید.\n🤝 «سیاه‌چال گروهی» را با ۳ تا ۵ نفر می‌روید.",
        )),
        "invite": ("🤝 دعوت دوستان", page(
            f"🤝 {bold('دعوت از دوستان')}",
            "در پیوی ربات دکمه‌ی «دعوت از دوستان» لینک مخصوص شما را می‌دهد.",
            "🎁 هر دوستی که با لینک وارد شود و قهرمانش را بسازد، همان لحظه برایتان چند جایزه‌ی شانسی می‌آید (روزانه تا ۱۰ دعوت).",
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
    return f"{activity.emoji} {bold(activity.title)} · {name}"


def activity_frames(name: str, activity) -> list[str]:  # noqa: ANN001 - Activity
    """One short waiting frame (a group should not fill up with story)."""
    return [f"{_activity_head(name, activity)}\n{WORKING.get(activity.id, '⏳ در حال انجام... لطفاً صبر کنید')}"]


def gains_list(gold: int = 0, xp: int = 0, crystal: int = 0, items=()) -> list[str]:  # noqa: ANN001
    """What was collected, one thing to a line."""
    lines = []
    if gold:
        lines.append(f"🪙 {fa(gold)} سکه")
    if xp:
        lines.append(f"⭐ {fa(xp)} تجربه")
    if crystal:
        lines.append(f"💎 {fa(crystal)} کریستال")
    lines += [f"{label} ×{fa(qty)}" for label, qty, _ in items]
    return lines


def _boost_note(double_xp: bool, boosted: bool) -> str:
    if boosted:
        return "🚀 بوست فعال: پاداش دو برابر"
    return "✨ ستاره‌ی تجربه: تجربه دو برابر" if double_xp else ""


def _wait_text(seconds: int) -> str:
    return duration(seconds) if seconds > 0 else "همین حالا آماده است"


def _card(head: str, intro: list[str], loot: list[str], status: list[str], tail: list[str]) -> str:
    """One tidy card: the title and what happened, the loot as a list, then a few status lines, each block apart."""
    blocks = [[head, *intro]]
    if loot:
        blocks.append([f"📦 {bold('غنیمت جمع‌آوری‌شده')}", *loot])
    blocks.append([line for line in status if line])
    blocks.append([line for line in tail if line])
    return "\n\n".join("\n".join(block) for block in blocks if block)


def activity_result(name: str, result) -> str:  # noqa: ANN001 - ActivityResult
    rolled = result.rolled
    loot = gains_list(rolled.gold, rolled.xp, rolled.crystal, result.items)
    return _card(
        _activity_head(name, result.activity),
        [emphasize(rolled.outcome.text.format(name=name))],
        loot or ["این بار دست خالی بودید"],
        [f"⚡ انرژی: {fa(result.player.energy)}", _boost_note(result.double_xp, getattr(result, "boosted", False))],
        [f"⏰ {result.activity.title} بعدی: {_wait_text(result.next_in)}", level_up_text(result.level_up.new_level) if result.level_up else ""],
    )


def hunt_frames(name: str, r) -> list[str]:  # noqa: ANN001 - HuntResult
    return [f"🐺 {bold('شکار')} · {name}\n{r.monster.emoji} {r.monster.name} پیدا شد... نبرد آغاز می‌شود"]


def hunt_result(name: str, r) -> str:  # noqa: ANN001 - HuntResult
    verdict = "🏆 پیروز شدید" if r.won else "💔 هیولا قوی‌تر بود؛ عقب‌نشینی کردید"
    return _card(
        f"{r.monster.emoji} {bold('شکار ' + r.monster.name)} · {name}",
        [f"{verdict} ({fa(r.rounds)} دور)"],
        gains_list(r.gold, r.xp, 0, r.items) if r.won else [],
        [f"❤️ جان: {fa(r.hero_hp)} از {fa(r.hero_max_hp)}", f"⚡ انرژی: {fa(r.player.energy)}", _boost_note(r.double_xp, getattr(r, "boosted", False))],
        [
            f"🃏 {bold('کارت تازه:')} {r.card.emoji} {r.card.name}" if r.card is not None else "",
            f"⏰ شکار بعدی: {_wait_text(r.next_in)}",
            level_up_text(r.level_up.new_level) if r.level_up else "",
        ],
    )


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
    lines = [board.title, LINE, ""]
    top = [
        (f"{entry.mention if mentions else entry.name} {entry.badge}".strip(),
         [f"⭐ سطح {fa(entry.level)}", f"🔥 {fa(entry.value)} {board.unit}"])
        for entry in board.entries[:3]
    ]
    lines += tidy_list(top)
    rest = board.entries[3:]
    if rest:
        lines += [""] + [
            f"{fa(index + 4)}. {entry.mention if mentions else entry.name} · سطح {fa(entry.level)} · {fa(entry.value)} {board.unit}"
            for index, entry in enumerate(rest)
        ]
    if board.my_position:
        lines += ["", f"📍 جایگاه شما: {bold(fa(board.my_position))}"]
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
    return f"🗝️ {bold('در حال باز کردن ' + item.name)}\n\nکلید در قفل می‌چرخد و نوری از لای درز بیرون می‌زند... کمی صبر کنید ✨"


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
    return f"🔨 {bold('آهنگر در کار است')}\n\nفلز در کوره سرخ شده و چکش بالا می‌رود... جرقه‌ها می‌پرند ✨"


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
    if pack.city or pack.city_shield_hours:
        from ..game.data.city import RES, RES_INFO

        parts = [f"{RES_INFO[r][1]} {fa(pack.city[r])}" for r in RES if pack.city.get(r)]
        if pack.city_shield_hours:
            parts.append(f"سپر دفاعی {fa(pack.city_shield_hours)} ساعته")
        return "شامل (مستقیم به شهر فرمانروایی شما می‌رسد): " + "، ".join(parts)
    if pack.spins:
        return f"شامل: {fa(pack.spins)} فرصت چرخش گردونه شانس با جایزه‌های ارزشمند"
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
    if pack.boost_hours:
        return (
            f"شامل: {fa(pack.boost_hours)} ساعت بوست دو برابر.\n"
            "در این مدت سکه و تجربه‌ی بازی و آیتم‌های ماجراجویی و شکار دو برابر می‌شود. خرید دوباره به زمان باقی‌مانده اضافه می‌شود."
        )
    if pack.xp:
        return (
            f"شامل: {fa(pack.xp)} تجربه.\n"
            "همان لحظه به تجربه‌ی شما اضافه می‌شود؛ هرچه سطحتان پایین‌تر باشد، سطح بیشتری بالا می‌روید."
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
    if granted and order.pack.lucky:
        body = f"🎲 این‌ها از بسته درآمد:\n{granted}"
    else:
        body = granted or pack_description(order.pack)
    return (
        f"✅ {bold('پرداخت موفق بود')}\n"
        f"{order.pack.label} به گنجینه‌ی شما رسید.\n\n{body}\n\n"
        "سپاس از حمایت شما 💛"
    )


SECTION_NAMES = {
    "coins": "بسته‌ی سکه", "crystals": "بسته‌ی کریستال", "bundles": "بسته‌ی ویژه",
    "materials": "منابع", "lucky": "بسته‌ی شانسی روزانه", "deal": "تخفیف روز", "boost": "بوست دو برابر",
    "xp": "بسته‌ی تجربه", "wheel": "گردونه شانس", "city": "منابع فرمانروایی", "rare": "منابع کمیاب",
}


def discount_note(pack, amount: int) -> str:  # noqa: ANN001 - Pack
    percent = round(100 * (1 - amount / pack.price_rial))
    return f"{fa(percent)}٪ تخفیف"


def deals_text(deals, seconds_left: int) -> str:  # noqa: ANN001
    lines = [
        f"🏷️ {bold('تخفیف‌های امروز')}",
        "",
        f"⏳ تا پایان امروز: {duration(seconds_left)} دیگر",
        "🔄 فردا فهرست تازه می‌آید",
        "",
    ]
    for deal in deals:
        pack = deal.pack
        lines += [
            f"{pack.emoji} {bold(pack.title)} · {fa(deal.percent)}٪ تخفیف",
            f"💰 قبلاً {fa(pack.price_toman)} ← اکنون {bold(fa(deal.price_toman))} تومان",
            f"🎁 {pack_description(pack).replace(chr(10), ' ').removeprefix('شامل: ')}",
            "",
        ]
    lines.append("👇 یک مورد را بزنید؛ فاکتور پرداخت بله برایتان می‌آید")
    return "\n".join(lines)


def gift_receipt(order, recipient) -> str:  # noqa: ANN001
    """What the payer reads after paying for a gift."""
    return (
        f"✅ {bold('پرداخت موفق بود')}\n\n"
        f"{order.pack.label} ×{fa(order.qty)} برای {bold(recipient.name)} فعال شد و پیام هدیه برایش رفت.\n\n"
        "سپاس از دست‌ودل‌بازی شما 💛"
    )


def gift_received(order, granted: str, sender) -> str:  # noqa: ANN001
    """What the lucky hero reads."""
    body = granted or pack_description(order.pack)
    return (
        f"🎁 {bold('هدیه‌ی ویژه رسید!')}\n\n"
        f"فرمانده {bold(sender.name)} این هدیه را از خزانه قلمرو برایتان خرید:\n\n"
        f"{order.pack.label} ×{fa(order.qty)}\n{body}\n\n"
        "از او سپاسگزار باشید 💛"
    )


def sale_report(order, player, user, charge_id, when: int, totals, granted: str = "", gift_to: str = "") -> str:  # noqa: ANN001
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
            f"📦 محصول: {pack.label}" + (f" ×{fa(order.qty)}" if order.qty > 1 else ""),
            *([f"🎁 هدیه برای: {gift_to}"] if gift_to else []),
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
            f"🆔 شناسه بله: {str(user.id).translate(_TO_FA)}",
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
    t = v.type
    lines = [f"{t.emoji} {bold(t.name + ' بیدار شده است!')}", f"«{t.story}»", ""]
    if v.revenge:
        lines += ["🔥 انتقام! این باس خشمگین‌تر برگشته؛ پاداش پیروزی ۱٫۵ برابر است.", ""]
    lines += [
        f"🔮 عنصر: {t.element.emoji} {t.element.noun}",
        f"🎯 نقطه‌ضعف: کلاس {CLASSES[t.weak_class].name}",
        "🎲 قدرت واقعی باس تا شروع نبرد پنهان است.",
        "",
        "🌑 باس مخفی است؛ هر جنگجو می‌تواند نبرد را شروع کند." if v.free else f"👤 احضارکننده: {v.summoner_mention}",
        f"👥 جنگجویان: {bold(fa(len(v.fighters)))} از {fa(max_players)} (حداقل {fa(min_players)})",
        f"⏳ ثبت‌نام: {_clock(v.seconds_left)}",
        "",
        f"🛡️ {bold('در صف نبرد')}",
        *(f"{f.emoji} {f.mention}" for f in v.fighters),
        "",
        "👇 «پیوستن» را بزنید؛ احضارکننده نبرد را شروع می‌کند.",
    ]
    return "\n".join(lines)


def boss_fight(v) -> str:  # noqa: ANN001 - BossView
    percent = round(100 * v.hp / v.max_hp) if v.max_hp else 0
    tier = tier_by_id(v.tier)
    lines = [
        f"⚔️ {bold('نبرد با ' + v.type.name)}",
        f"🔮 هاله‌ی باس: {tier.emoji} {tier.name}",
        "",
        f"❤️ {fa(v.hp)} / {fa(v.max_hp)}",
        f"{bar(v.hp, v.max_hp, 10)}  {fa(percent)}٪",
        f"👥 زنده: {fa(v.alive_count)} از {fa(len(v.fighters))}",
        f"🔁 دور {fa(v.round)} · ⏳ {_clock(v.seconds_left)}",
    ]
    if v.report:
        lines += ["", f"📜 {bold('گزارش نبرد')}", *v.report]
    ranked = sorted(v.fighters, key=lambda f: -f.damage)[:3]
    if ranked and ranked[0].damage:
        lines += ["", f"🏅 {bold('بیشترین آسیب')}"]
        lines += [f"{MEDALS[i]} {f.mention} — {fa(f.damage)}" for i, f in enumerate(ranked)]
    return "\n".join(lines)


def boss_started(v) -> str:  # noqa: ANN001 - BossView
    return (
        f"🚀 {bold('نبرد آغاز شد!')}\n"
        f"{fa(len(v.fighters))} جنگجو در برابر {v.type.emoji} {bold(v.type.name)} صف کشیدند.\n\n"
        f"🧠 ویژگی باس: {behavior_of(v.type)[1]}\n\n" + boss_fight(v)
    )


def boss_final(v) -> str:  # noqa: ANN001 - BossView
    if v.outcome == "cancelled":
        return (
            f"🌫️ {bold('احضار ناکام ماند')}\n"
            f"{v.type.name} بدون نبرد به خواب برگشت؛ جنگجوی کافی نیامد.\n\n"
            "💰 سکه‌ی احضار به احضارکننده برگشت."
        )
    heads = {
        "won": f"🏆 {bold(v.type.name + ' شکست خورد!')}\nجنگجویان قلمرو پیروز شدند.",
        "lost": f"💀 {bold('همه‌ی جنگجویان از پا افتادند')}\n{v.type.name} پیروز میدان شد؛ ولی تلاشتان بی‌پاداش نماند.",
        "fled": f"⌛ {bold(v.type.name + ' گریخت')}\nزمان تمام شد و باس ناپدید شد؛ ولی تلاشتان بی‌پاداش نماند.",
    }
    lines = [
        heads.get(v.outcome or "fled", heads["fled"]),
        "",
        f"📊 {fa(v.round)} دور · {fa(len(v.fighters))} جنگجو",
        "",
    ]
    if not v.payouts:
        lines.append("هیچ‌کس در نبرد نبود.")
    else:
        entries = []
        for p in v.payouts:
            gains = [f"⚔️ {fa(p.damage)} آسیب ({fa(round(p.share * 100))}٪)"]
            if p.level_up:
                gains.append(f"🎉 سطح {fa(p.level_up)}")
            if p.trophy:
                gains.append(f"🏆 {get_item(p.trophy).name}")
            if p.card:
                gains.append(f"🃏 {p.card}")
            entries.append((p.mention, gains))
        lines += [f"🏅 {bold('سهم جنگجویان')}", "", *tidy_list(entries, 10)]
    lines.append("")
    if v.outcome in ("lost", "fled"):
        lines += ["🔥 تا ۲۴ ساعت می‌توانید همین باس را دوباره احضار کنید؛ خشمگین‌تر برمی‌گردد و پاداش ۱٫۵ برابر دارد.", ""]
    lines.append("🪙 پاداش هر نفر در دکمه‌های زیر 👇")
    return "\n".join(lines)


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
            f"🎁 {bold('صندوقچه‌ی اسرارآمیز!')}\n"
            "از کاروانی سلطنتی فقط یک صندوقچه‌ی قفل‌شده مانده که نقش‌های درخشانی روی قفلش می‌چرخد.\n\n"
            "هر کس می‌تواند شانسش را امتحان کند و فقط یک نفر برنده است. هر تلاش قفل را سست‌تر می‌کند.\n\n"
            f"🔑 تلاش‌ها: {fa(st['attempts'])}\n"
            f"⏳ مهلت: {_clock(view.seconds_left)}\n"
            "🎲 جایزه: صندوقچه‌ی چوبی، جادویی یا (کم‌شانس) سلطنتی\n\n"
            "👇 زودتر دست به کار شوید"
        )
    if view.kind == "merchant":
        lines = [f"🧳 {bold('تاجر دوره‌گرد رسید!')}", ""]
        if view.status == "active":
            lines += ["کاروانش را در این منطقه پهن کرده و کالاهای محدودش را ارزان می‌فروشد.", ""]
        else:
            lines += ["تاجر کاروانش را جمع کرد و رفت. شاید دفعه‌ی بعد!", ""]
        for entry in st["stock"]:
            item = get_item(entry["item"])
            left = f"📦 {fa(entry['left'])} عدد مانده" if entry["left"] > 0 else "❌ تمام شد"
            lines += [f"🛒 {item.label}", f"🪙 {fa(entry['price'])} · {left}", ""]
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
    if view.kind == "hidden_chest":
        return _hidden_chest_text(view)
    if view.kind == "invasion":
        return _invasion_text(view)
    if view.kind == "meteor":
        return _meteor_text(view)
    if view.kind == "gold_rain":
        return _rain_text(view)
    if view.kind == "spring":
        return _spring_text(view)
    if view.kind == "wheel":
        return _wheel_text(view)
    if view.kind == "egg":
        return _egg_text(view)
    if view.kind == "riddle":
        return _riddle_text(view)
    if view.kind == "tiles":
        return _tiles_text(view)
    if view.kind == "raffle":
        return _raffle_text(view)
    return f"{view.kind}"


def _riddle_text(view) -> str:  # noqa: ANN001 - EventView
    from ..game.data.group_games import RIDDLES

    st = view.state
    question, answer, _ = RIDDLES[st["q"]]
    if view.status == "done":
        gains = [f"🪙 {fa(st['gold'])} سکه", "⭐ تجربه"] + (["💎 ۱ کریستال"] if st.get("crystal") else [])
        return (
            f"🧠 {bold('معما حل شد!')}\n\n{question}\n\n✅ پاسخ: {bold(answer)}\n\n"
            f"🏆 {st['winner']} زودتر از همه پاسخ داد و برد: {'، '.join(gains)}"
        )
    if view.status == "expired":
        return f"🕸️ {bold('معما بی‌پاسخ ماند')}\n\n{question}\n\n✅ پاسخ: {bold(answer)}\n\nکسی آن را حل نکرد."
    return (
        f"🧠 {bold('معمای کاروان!')}\n\n"
        "فرزانه‌ای دوره‌گرد معمایی پیش پای گروه گذاشته. اولین کسی که درست جواب دهد، جایزه را می‌برد.\n\n"
        f"❓ {question}\n\n"
        f"🙋 حدس‌ها: {fa(len(st['at']))} نفر\n⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}\n"
        "👇 گزینه‌ی درست را بزنید (هر ۱۲ ثانیه یک حدس)"
    )


def _tiles_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    if view.status == "active":
        lines = [
            f"🔲 {bold('کاشی‌های شانس!')}", "",
            "کف تالار از کاشی‌های نقش‌دار پر شده و زیر هر کدام چیزی پنهان است. هر نفر یک کاشی برمی‌دارد.", "",
            f"🧩 کاشی‌های مانده: {fa(len(st['tiles']) - len(st['picked']))} از {fa(len(st['tiles']))}",
        ]
    else:
        lines = [f"🏁 {bold('کاشی‌ها تمام شد')}", ""]
    if st["players"]:
        entries = [(st["names"][pid], [text]) for pid, tile in list(st["players"].items())[-8:] for text in [st["picked"][str(tile)]]]
        lines += ["", f"🎯 {bold('برندگان و بازندگان')}", *tidy_list(entries, 8, ranked=False)]
    if view.status == "active":
        lines += ["", f"⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}", "👇 یک کاشی انتخاب کنید"]
    return "\n".join(lines)


def _raffle_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    count = len(st["entries"])
    if view.status == "done":
        return (
            f"🎟️ {bold('قرعه‌کشی انجام شد!')}\n\n"
            f"از میان {fa(count)} شرکت‌کننده، قرعه به نام {st['winner']} افتاد.\n"
            f"🏆 جایزه: {fa(st['prize'])} سکه و ۱ کریستال"
        )
    if view.status == "expired":
        return f"🎟️ {bold('قرعه‌کشی برگزار نشد')}\n\nشرکت‌کننده‌ی کافی نبود (دست‌کم ۲ نفر لازم است)."
    return (
        f"🎟️ {bold('قرعه‌کشی بزرگ!')}\n\n"
        "هر کس نامش را بنویسد (رایگان!) در قرعه می‌ماند و هر نام تازه، جایزه را بزرگ‌تر می‌کند.\n\n"
        f"🪙 جایزه‌ی فعلی: {fa(st['pot'])} سکه و ۱ کریستال\n"
        f"👥 شرکت‌کننده‌ها: {fa(count)} نفر\n"
        f"⏳ تا قرعه‌کشی: {_clock(view.seconds_left)}\n\n👇 نامتان را ثبت کنید"
    )


def _rain_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    if view.status == "active":
        lines = [
            f"🌧️ {bold('باران سکه!')}", "",
            "ابرهای زرین بالای گروه باز شده‌اند و سکه از آسمان می‌بارد.",
            "هر نفر حداکثر ۴ مشت برمی‌دارد.", "",
        ]
    else:
        lines = [f"☀️ {bold('باران سکه تمام شد')}", ""]
    lines.append(f"🪙 مشت‌های مانده: {fa(st['left'])}")
    if st["taken"]:
        top = sorted(st["gold"].items(), key=lambda kv: -kv[1])[:5]
        lines += ["", f"🏅 {bold('پرسودترین‌ها')}", *tidy_list([(st["names"][pid], [f"🪙 {fa(g)} سکه"]) for pid, g in top], 5)]
    if view.status == "active":
        lines += ["", f"⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}", "👇 زود باشید"]
    return "\n".join(lines)


def _spring_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    if view.status == "active":
        lines = [
            f"💧 {bold('چشمه‌ی برکت پیدا شد!')}", "",
            "هر که از آب این چشمه بنوشد، انرژی‌اش کامل می‌شود و کمی تجربه می‌گیرد.",
            "جا برای چند نفر اول است و هر نفر یک بار می‌نوشد.", "",
            f"👥 جای خالی: {fa(st['left'])}",
        ]
    else:
        lines = [f"🌙 {bold('چشمه خشک شد')}", ""]
    if st["names"]:
        lines += ["", f"💧 {bold('نوشندگان')}", *[f"🔹 {name}" for name in st["names"].values()]]
    if view.status == "active":
        lines += ["", f"⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}", "👇 بنوشید"]
    return "\n".join(lines)


def _wheel_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    if view.status == "active":
        lines = [
            f"🎡 {bold('چرخ شانس آمد!')}", "",
            "کاروان بازیگران چرخ بزرگش را وسط گروه گذاشته. هر نفر یک بار می‌چرخاند.",
            "جایزه‌ها: سکه، تجربه، کریستال، معجون و حتی صندوقچه!",
        ]
    else:
        lines = [f"🎪 {bold('چرخ شانس رفت')}", "", "کاروان بازیگران چرخش را جمع کرد."]
    if st["spins"]:
        lines += ["", f"🎯 {bold('چرخانندگان')}", *tidy_list([(st["names"][pid], [f"🎡 {text}"]) for pid, text in list(st["spins"].items())[-6:]], 6, ranked=False)]
    if view.status == "active":
        lines += ["", f"⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}", "👇 شانستان را بسنجید"]
    return "\n".join(lines)


def _egg_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    if view.status == "done":
        lines = [f"🐲 {bold('تخم اژدها شکست!')}", "", "جوجه‌اژدها با خوشحالی به همه‌ی گرم‌کننده‌ها نگاه می‌کند."]
        entries = []
        for p in st.get("payouts", []):
            gains = [f"🪙 {fa(p['gold'])} سکه", "💎 ۲ کریستال"] + ([f"🎁 {get_item(p['chest']).name}"] if p["chest"] else [])
            entries.append((p["mention"], gains))
        return "\n".join(lines + ["", *tidy_list(entries)])
    if view.status == "expired":
        return f"🧊 {bold('تخم اژدها سرد شد')}\n\nگرمای کافی نبود و تخم دوباره به خواب رفت."
    percent = round(100 * st["warm"] / st["need"]) if st["need"] else 0
    lines = [
        f"🥚 {bold('تخم اژدها!')}", "",
        "تخمی غول‌پیکر در گروه پیدا شد. اگر با هم گرمش کنید، جوجه‌اژدها بیرون می‌آید و به همه‌ی گرم‌کننده‌ها پاداش می‌دهد.", "",
        f"🔥 گرمای تخم: {bar(st['warm'], st['need'], 10)} {fa(percent)}٪",
    ]
    if st["hits"]:
        top = sorted(st["hits"].items(), key=lambda kv: -kv[1])[:5]
        lines += ["", f"🏅 {bold('گرم‌کننده‌های برتر')}", *tidy_list([(st["names"][pid], [f"🔥 {fa(n)} بار گرم کرد"]) for pid, n in top], 5)]
    lines += ["", f"⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}", "👇 همه با هم گرمش کنید"]
    return "\n".join(lines)


def _hidden_chest_text(view) -> str:  # noqa: ANN001 - EventView
    from ..game.data.items import get_item
    from ..game.data.world_events import place

    st = view.state
    if view.status == "done":
        spot = place(st["target"])
        return (
            f"🗝️ {bold('صندوقچه‌ی مخفی پیدا شد!')}\n\n"
            f"{st['mention']} در {spot.name} صندوقچه را یافت و {get_item(st['prize']).label} و ۱۵۰ سکه برد."
        )
    if view.status == "expired":
        return f"⌛ {bold('صندوقچه‌ی مخفی ناپدید شد')}\n\nکسی مکانش را پیدا نکرد و جادوی صندوقچه خاموش شد."
    lines = [
        f"🗝️ {bold('صندوقچه‌ی مخفی!')}",
        "",
        "نقشه‌ی کهنه‌ای به دست رسیده؛ صندوقچه‌ای در یکی از جاهای قلمرو پنهان شده است. سرنخ:",
        "",
        f"📜 «{st['clue']}»",
        "",
        "جایی را که فکر می‌کنید بگردید. هر جای اشتباه از لیست حذف می‌شود و برای دیگران ساده‌تر می‌شود!",
    ]
    if st["tried"]:
        lines += ["", f"{bold('گشته‌شده‌ها')}"]
        from ..game.data.world_events import place as _place

        lines += [f"❌ {_place(pid).name} — {who}" for pid, who in st["tried"].items()]
    lines += ["", f"⏳ مهلت: {_clock(view.seconds_left)}", "", "🎲 جایزه: صندوقچه + ۱۵۰ سکه برای پیدا‌کننده 👇"]
    return "\n".join(lines)


def _invasion_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    lines = []
    if view.status == "done":
        lines = [f"🏆 {bold('قلمرو نجات یافت!')}", "", f"{st['army']} شکست خورد و با ترس عقب نشست.", ""]
    elif view.status == "expired":
        lines = [f"💀 {bold('مدافعان عقب نشستند')}", "", f"{st['army']} پیش از پایان مهلت قلمرو را غارت کرد؛ اما تلاش مدافعان بی‌پاداش نماند.", ""]
    else:
        lines = [f"🚨 {bold('تهاجم! ' + st['army'])}", "", f"این لشکر {st['cry']}", "همه‌ی قهرمانان برای دفاع از قلمرو فراخوانده می‌شوند!", ""]
    percent = round(100 * st["hp"] / st["max_hp"]) if st["max_hp"] else 0
    lines.append(f"❤️ جان لشکر: {bar(st['hp'], st['max_hp'], 10)} {fa(percent)}٪")
    if st["hits"]:
        top = sorted(st["hits"].items(), key=lambda kv: -kv[1])[:5]
        lines += ["", f"🏅 {bold('برترین مدافعان')}", *tidy_list([(st["names"][pid], [f"⚔️ {fa(dmg)} آسیب"]) for pid, dmg in top], 5)]
    if view.status == "active":
        lines += ["", f"⏳ مهلت: {_clock(view.seconds_left)}", "هر کس می‌تواند هر چند ثانیه یک بار ضربه بزند؛ هرچه بیشتر بزنید سهم بیشتری می‌برید 👇"]
    elif st.get("payouts"):
        entries = []
        for p in st["payouts"]:
            gains = [f"🪙 {fa(p['gold'])} سکه", f"⭐ {fa(p['xp'])} تجربه"] + ([f"🎁 {get_item(p['chest']).name}"] if p["chest"] else [])
            entries.append((p["mention"], gains))
        lines += ["", f"🎁 {bold('پاداش مدافعان')}", *tidy_list(entries)]
    return "\n".join(lines)


def _meteor_text(view) -> str:  # noqa: ANN001 - EventView
    st = view.state
    lines = []
    if view.status == "active":
        lines = [
            f"☄️ {bold('شهاب‌سنگ سقوط کرد!')}", "",
            f"سنگی آسمانی در {st['region']} فرود آمد و تکه‌هایش پر از مواد کمیاب است.",
            "تکه‌ها محدودند؛ هر کس زودتر برسد برمی‌دارد (حداکثر ۳ تکه برای هر نفر).", "",
        ]
    else:
        lines = [f"🌌 {bold('شهاب‌سنگ خاموش شد')}", "", "دیگر چیزی از آن نمانده."]
    lines.append(f"💎 تکه‌های مانده: {fa(st['left'])}")
    if st["taken"]:
        top = sorted(st["taken"].items(), key=lambda kv: -kv[1])[:6]
        lines += ["", f"⛏️ {bold('برداشت‌کنندگان')}", *tidy_list([(st["names"][pid], [f"💎 {fa(n)} تکه"]) for pid, n in top], 6, ranked=False)]
    if view.status == "active":
        lines += ["", f"⏳ زمان باقی‌مانده: {_clock(view.seconds_left)}", "زود باشید 👇"]
    return "\n".join(lines)


def events_overview(views_, double_xp: bool) -> str:  # noqa: ANN001
    lines = [f"🎲 {bold('رویدادهای گروه')}", ""]
    if views_:
        for v in views_:
            label = {"mystery_chest": "🎁 صندوقچه‌ی اسرارآمیز", "merchant": "🧳 تاجر دوره‌گرد",
                     "double_xp": "✨ تجربه‌ی دوبرابر", "hidden_chest": "🗝️ صندوقچه‌ی مخفی",
                     "invasion": "🚨 تهاجم هیولاها", "meteor": "☄️ شهاب‌سنگ", "gold_rain": "🌧️ باران سکه",
                     "spring": "💧 چشمه‌ی برکت", "wheel": "🎡 چرخ شانس", "egg": "🥚 تخم اژدها", "riddle": "🧠 معمای کاروان",
                     "tiles": "🔲 کاشی‌های شانس", "raffle": "🎟️ قرعه‌کشی بزرگ"}.get(v.kind, v.kind)
            lines.append(f"• {label} — {duration(v.seconds_left)} مانده")
        lines.append("")
    else:
        lines += ["الان رویدادی در جریان نیست.", ""]
    lines += [
        "ربات گاهی خودش در گروه‌های فعال اتفاق می‌اندازد: صندوقچه‌ی اسرارآمیز، صندوقچه‌ی مخفی با سرنخ، "
        "تاجر دوره‌گرد، ستاره‌ی تجربه، باس مخفی، تهاجم هیولاها، شهاب‌سنگ، باران سکه، چشمه‌ی برکت، چرخ شانس، تخم اژدها، معما، کاشی‌های شانس و قرعه‌کشی. "
        "هرچه گروه فعال‌تر باشد، رویدادها بیشتر و بزرگ‌تر می‌شوند.",
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
def bet_waiting(bet, challenger, seconds: int) -> str:  # noqa: ANN001 - Bet, Player
    from ..game.services.bets import FEE_PERCENT, prize_for

    head = [
        f"🎰 {bold('دوئل شرطی')}",
        "",
        f"{challenger.char_class.emoji} {challenger.mention} · سطح {fa(challenger.level)}",
        f"🏆 {fa(challenger.wins)} پیروزی · 💀 {fa(challenger.losses)} شکست",
        "",
    ]
    if bet.kind == "gear":
        lines = head + [
            f"🎁 آیتم شرط: {bold(bet.label)}",
            f"💎 ارزش آیتم: {fa(bet.value)} سکه",
            "",
            f"{bold('برای قبول، یکی از این‌ها را می‌پردازید')}",
            f"🪙 {fa(bet.pay_gold)} سکه (دو برابر ارزش)",
            f"💎 {fa(bet.pay_crystal)} کریستال",
            "🔁 یا همین آیتم را بگذارید (اگر دارید)",
            "",
            f"🏅 برنده همه‌چیز را می‌برد؛ از پرداخت سکه یا کریستال {fa(FEE_PERCENT)}٪ کارمزد کم می‌شود.",
        ]
    else:
        prize, fee = prize_for(bet.kind, bet.amount)
        lines = head + [
            f"💰 شرط هر نفر: {bold(bet.label)}",
            f"🏅 جایزه‌ی برنده: {bold(stake_prize(bet.kind, bet.item_id, prize))}",
        ]
        if fee:
            lines.append(f"🏦 کارمزد قلمرو: {fa(FEE_PERCENT)}٪ از جایزه")
    lines += [f"⏳ مهلت: {duration(seconds)}", "", "هر کس شرط را قبول کند همان لحظه وارد دوئل می‌شود 👇"]
    return "\n".join(lines)


def stake_prize(kind: str, item_id: str, amount: int) -> str:
    from ..game.services.bets import stake_label

    return stake_label(kind, item_id, amount)


def bet_lines(update) -> list[str]:  # noqa: ANN001 - DuelUpdate
    """The «what happened to the stakes» block of a bet duel's result."""
    outcome = update.bet
    if outcome is None:
        return []
    if outcome.kind == "gear":
        if outcome.winner_id is None:
            return ["", f"🎰 {bold('شرط دوئل')}", f"🤝 مساوی شد؛ {outcome.gear} و پرداخت حریف به صاحبانشان برگشت."]
        winner = next((f for f in update.battle.fighters if f.player_id == outcome.winner_id), None)
        name = (winner.mention or winner.name) if winner else "برنده"
        lines = ["", f"🎰 {bold('شرط دوئل')}", f"🏆 {name} جایزه را برد"]
        if outcome.winner_is_creator:
            lines.append(f"🎁 آیتم خودش برگشت: {outcome.gear}")
            if outcome.payment:
                lines.append(f"💰 از حریف گرفت: {bold(outcome.payment)}")
            if outcome.fee_label:
                lines.append(f"🏦 کارمزد قلمرو: {outcome.fee_label}")
        else:
            lines.append(f"🎁 آیتم برنده شد: {bold(outcome.gear)}")
            lines.append("↩️ پرداخت او هم به خودش برگشت.")
        return lines
    if outcome.winner_id is None:
        return ["", f"🎰 {bold('شرط دوئل')}", f"🤝 مساوی شد؛ شرط {stake_prize(outcome.kind, outcome.item_id, outcome.amount)} به هر دو برگشت."]
    winner = next((f for f in update.battle.fighters if f.player_id == outcome.winner_id), None)
    name = (winner.mention or winner.name) if winner else "برنده"
    lines = ["", f"🎰 {bold('شرط دوئل')}", f"🏆 {name} جایزه را برد", f"💰 {bold(outcome.prize_label)}"]
    if outcome.fee:
        lines.append(f"🏦 کارمزد قلمرو: {fa(outcome.fee)}")
    return lines


def duel_invite(challenger, target, seconds: int, note: str = "") -> str:  # noqa: ANN001 - Player
    return "\n".join([
        f"⚔️ {bold('فراخوان دوئل')}",
        "",
        f"{challenger.char_class.emoji} {challenger.mention} · سطح {fa(challenger.level)}",
        f"🏆 {fa(challenger.wins)} پیروزی · 💀 {fa(challenger.losses)} شکست",
        *([note] if note else []),
        "",
        f"فرمانده {target.mention} ، دعوت را می‌پذیرید؟",
        f"⏳ {duration(seconds)} فرصت دارید.",
    ])


def _hp_block(f) -> str:  # noqa: ANN001 - Fighter
    hp = max(f.hp, 0)
    percent = round(100 * hp / f.max_hp) if f.max_hp else 0
    return "\n".join([
        f"{f.emoji} {f.mention or bold(f.name)}",
        f"❤️ {bar(hp, f.max_hp, 10)} {fa(percent)}٪",
        f"     {fa(hp)} از {fa(f.max_hp)} جان",
    ])


def _hp_line(f) -> str:  # noqa: ANN001 - Fighter
    return _hp_block(f)


def _story(lines: list[str], limit: int = 5) -> list[str]:
    """The last few moves, one per line."""
    kept = [line.strip() for line in lines if line.strip()][-limit:]
    return [f"• {line}" for line in kept]


def duel_status(battle, lines: list[str], turn_seconds: int) -> str:  # noqa: ANN001 - Battle
    a, b = battle.fighters
    out = [f"⚔️ {bold('میدان نبرد')}", "", _hp_block(a), "     ⚡ در برابر ⚡", _hp_block(b)]
    story = _story(lines)
    if story:
        out += ["", f"📜 {bold('آخرین حرکت‌ها')}", *story]
    if not battle.finished:
        out += [
            "",
            f"🎯 نوبت {battle.current.mention or bold(battle.current.name)}",
            f"🔁 دور {fa(battle.round)} از {fa(battle.max_rounds)} · ⏳ {duration(turn_seconds)}",
        ]
    return "\n".join(out)


def _bet_result(update) -> str:  # noqa: ANN001 - DuelUpdate
    """The end of a bet duel: short, one block each for the verdict, the stakes, the hit points and the rewards."""
    battle = update.battle
    out = [f"🏁 {bold('پایان نبرد')}", "🎰 دوئل شرطی", ""]
    if battle.winner is None:
        out.append("🤝 مساوی شد؛ هر دو دلاور بودند!")
    else:
        winner = battle.fighters[battle.winner]
        out.append(f"🏆 برنده: {winner.mention or bold(winner.name)}")
    out += ["", *[line for line in bet_lines(update)[1:] if not line.startswith("🏆")]]  # the stakes, minus the repeated winner
    out += ["", f"❤️ {bold('جان‌ها')}"]
    for f in battle.fighters:
        percent = round(100 * max(f.hp, 0) / f.max_hp) if f.max_hp else 0
        out.append(f"{f.emoji} {f.mention or f.name} — {fa(percent)}٪")
    last = _story(update.lines, 2)
    if last:
        out += ["", f"📜 {bold('ضربه‌ی پایانی')}", *last]
    rewards = []
    for fighter in battle.fighters:
        payout = update.payouts.get(fighter.player_id)
        if payout is None:
            continue
        gains = []
        if payout.gold:
            gains.append(f"🪙 {fa(payout.gold)}")
        if payout.xp:
            gains.append(f"⭐ {fa(payout.xp)}")
        if payout.rating:
            league = league_of(payout.rating)
            sign = "+" if payout.rating_delta >= 0 else "-"
            gains.append(f"{league.emoji} {sign}{fa(abs(payout.rating_delta))}")
        if payout.level_up:
            gains.append(f"🎉 سطح {fa(payout.level_up.new_level)}")
        if gains:
            rewards.append(f"👤 {fighter.mention or fighter.name}: " + " · ".join(gains))
    if rewards:
        out += ["", f"🎁 {bold('پاداش دوئل')}", *rewards]
    return "\n".join(out)


def duel_result(update) -> str:  # noqa: ANN001 - DuelUpdate
    if update.bet is not None:
        return _bet_result(update)
    battle = update.battle
    a, b = battle.fighters
    out = [f"🏁 {bold('پایان نبرد')}", ""]
    if battle.winner is None:
        out.append("🤝 مساوی شد؛ هر دو دلاور بودند!")
    else:
        winner = battle.fighters[battle.winner]
        out.append(f"🏆 برنده: {winner.mention or bold(winner.name)}")
    out += ["", _hp_block(a), "     ⚡ در برابر ⚡", _hp_block(b)]
    story = _story(update.lines, 4)
    if story:
        out += ["", f"📜 {bold('ضربه‌های پایانی')}", *story]
    rewards = []
    for fighter in battle.fighters:
        payout = update.payouts.get(fighter.player_id)
        if payout is None:
            continue
        gains = []
        if payout.gold:
            gains.append(f"🪙 {fa(payout.gold)} سکه")
        if payout.xp:
            gains.append(f"⭐ {fa(payout.xp)} تجربه")
        if not gains:
            gains.append("⏳ سقف پاداش امروز پر است")
        if payout.rating:
            league = league_of(payout.rating)
            sign = "+" if payout.rating_delta >= 0 else "-"
            gains.append(f"{league.emoji} {league.name} · {fa(payout.rating)} ({sign}{fa(abs(payout.rating_delta))})")
        if payout.level_up:
            gains.append(f"🎉 سطح {fa(payout.level_up.new_level)}")
        rewards.append((fighter.mention or fighter.name, gains))
    if rewards:
        out += ["", f"🎁 {bold('پاداش')}", "", *tidy_list(rewards, 2, ranked=False)]
    out += bet_lines(update)
    return "\n".join(out)
