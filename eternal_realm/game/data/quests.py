"""Story quests: short branching tales where each choice changes how the story (and its reward) ends."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Reward:
    gold: int = 0
    crystal: int = 0
    xp: int = 0
    items: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class Choice:
    label: str
    next: str
    #: remembered for later steps
    flag: str = ""
    #: the choice is only offered when this flag was set earlier
    requires: str = ""


@dataclass(frozen=True)
class Step:
    text: str
    choices: tuple[Choice, ...] = ()
    #: given once when the player reaches this step (endings only)
    reward: Reward | None = None
    ending: str = ""


@dataclass(frozen=True)
class Quest:
    id: str
    emoji: str
    title: str
    summary: str
    level_req: int
    steps: dict[str, Step] = field(default_factory=dict)
    #: 1-10 for the generated chapters, 0 for hand-written special stories
    chapter: int = 0


_SPECIAL: tuple[Quest, ...] = (
    Quest(
        "lost_letter", "✉️", "نامه‌ی گمشده", "نامه‌ای خاک‌خورده در راه پیدا کرده‌اید؛ مال کیست؟", 1,
        {
            "start": Step(
                "کنار جاده‌ی کاروان‌ها، نامه‌ای مهرخورده روی خاک افتاده است. نامه به نام «ییلاق‌نشین» است "
                "و بویی از عطر گل می‌دهد. چه می‌کنید؟",
                (
                    Choice("📬 نامه را به صاحبش می‌رسانم", "deliver", "honest"),
                    Choice("🔍 مهرش را باز می‌کنم و می‌خوانم", "read", "curious"),
                ),
            ),
            "deliver": Step(
                "ییلاق‌نشین پیرزنی مهربان است. نامه را که می‌گیرد، چشمانش پر از اشک می‌شود: "
                "«از پسرم است که سال‌هاست خبری نداشتم!» چند قدم دورتر هم تاجری ایستاده و نگاهتان می‌کند.",
                (
                    Choice("🤝 جایزه‌اش را قبول نمی‌کنم", "end_kind", "humble"),
                    Choice("💰 جایزه‌ی رساندن نامه را می‌گیرم", "end_fair"),
                ),
            ),
            "read": Step(
                "در نامه نقشه‌ی گنجی کوچک کشیده شده؛ زیر یک درخت سرو کنار چشمه. حالا می‌دانید پیرزن "
                "تنهاست و شاید هرگز به آنجا نرسد.",
                (
                    Choice("🗺️ به دنبال گنج می‌روم", "end_greedy"),
                    Choice("📬 نقشه را سر جایش می‌گذارم و نامه را می‌رسانم", "end_fair", "honest"),
                ),
            ),
            "end_kind": Step(
                "پیرزن شما را در آغوش می‌گیرد و گردنبندی قدیمی هدیه می‌دهد. می‌گوید: «قلبی مثل قلب شما، "
                "در این روزگار کمیاب است.»",
                reward=Reward(gold=200, crystal=2, xp=120, items=(("life_amulet", 1),)),
                ending="پایان مهربانانه",
            ),
            "end_fair": Step(
                "کار تمام می‌شود و پیرزن کیسه‌ی کوچکی سکه به شما می‌دهد. معامله‌ای ساده و درست بود.",
                reward=Reward(gold=300, xp=80),
                ending="پایان منصفانه",
            ),
            "end_greedy": Step(
                "زیر سرو، صندوقچه‌ای پیدا می‌کنید، ولی چیزی جز چند سکه‌ی زنگ‌زده در آن نیست. "
                "شاید گنج واقعی چیز دیگری بود...",
                reward=Reward(gold=60, xp=40),
                ending="پایان طمع‌کارانه",
            ),
        },
    ),
    Quest(
        "mist_gate", "🌫️", "راز دروازه‌ی مه", "پیرمردی با چراغ خاموش دروازه‌ای مه‌آلود را نشانتان می‌دهد.", 3,
        {
            "start": Step(
                "در مرز جنگل، پیرمردی با چراغی خاموش ایستاده است. می‌گوید: «پشت این مه، دروازه‌ای هست "
                "که هزار سال بسته مانده. کسی که چراغم را روشن کند، می‌تواند از آن بگذرد.»",
                (
                    Choice("🏮 چراغ را برایش روشن می‌کنم", "cave", "helped"),
                    Choice("❓ از او می‌پرسم کیست", "riddle"),
                ),
            ),
            "riddle": Step(
                "پیرمرد لبخند می‌زند: «اگر معمایم را جواب بدهی، می‌گویم. هر چه بیشتر از من بگیری، "
                "بزرگ‌تر می‌شوم. من چیستم؟»",
                (
                    Choice("🕳️ «گودال»", "cave", "wise"),
                    Choice("🌑 «سایه»", "cave"),
                ),
            ),
            "cave": Step(
                "مه کنار می‌رود و دروازه‌ای سنگی پیدا می‌شود. روی آن نقش یک چشم است و پشتش صدایی زمزمه می‌کند. "
                "نگهبان دروازه بیدار شده است!",
                (
                    Choice("🏮 با چراغ روشن پیش می‌روم", "end_light", requires="helped"),
                    Choice("📖 پاسخ معما را برای نگهبان می‌گویم", "end_wise", requires="wise"),
                    Choice("⚔️ شمشیر را می‌کشم و حمله می‌کنم", "end_fight"),
                    Choice("🏃 برمی‌گردم", "end_flee"),
                ),
            ),
            "end_light": Step(
                "نور چراغ چشم نگهبان را نرم می‌کند و دروازه آرام باز می‌شود. در پشتش گنجینه‌ی کوچکی از "
                "کریستال‌ها خوابیده است.",
                reward=Reward(gold=500, crystal=3, xp=250, items=(("crystal_shard", 2),)),
                ending="پایان روشنایی",
            ),
            "end_wise": Step(
                "نگهبان از خرد شما شگفت‌زده می‌شود و دروازه را بر شما می‌گشاید. گنجی که می‌یابید از همه‌ی "
                "پایان‌های دیگر بزرگ‌تر است.",
                reward=Reward(gold=700, crystal=5, xp=350, items=(("magic_chest", 1),)),
                ending="پایان خردمندانه",
            ),
            "end_fight": Step(
                "نبردی سخت درمی‌گیرد. زخمی می‌شوید، اما نگهبان عقب می‌نشیند و چند سکه از خود بر جا می‌گذارد.",
                reward=Reward(gold=250, xp=150),
                ending="پایان جنگاورانه",
            ),
            "end_flee": Step(
                "ترجیح می‌دهید دروازه را برای روز دیگری بگذارید. گاهی عقب‌نشینی هم نشانه‌ی احتیاط است.",
                reward=Reward(gold=40, xp=30),
                ending="پایان محتاطانه",
            ),
        },
    ),
)

from .story_gen import build_all  # noqa: E402 - needs the classes above

QUESTS: tuple[Quest, ...] = (*_SPECIAL, *build_all())
_BY_ID = {q.id: q for q in QUESTS}


def get_quest(quest_id: str) -> Quest:
    return _BY_ID[quest_id]
