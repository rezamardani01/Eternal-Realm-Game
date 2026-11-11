"""Solo play (سفر قهرمان): bots to spar with, a story, daily dungeons, solo bosses and events on the road.

Every enemy is an ordinary :class:`Fighter` of the shared combat engine, scaled from the hero's level, so nothing
here has a fighting system of its own: only data and a few rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..engine.combat import Fighter

#: gold and experience of every solo reward are multiplied by this (the trip is a side road, not the main income)
REWARD_SHARE = 0.45
#: how many times a day one hero may use each section of the trip (the owner is exempt)
DAILY_USES = 1
SECTION_NAMES = {
    "story": "داستان", "arena": "میدان بات‌ها", "dungeon": "دخمه‌ها", "boss": "باس‌های تک‌نفره", "maze": "هزارتوی ابدی",
    "wander": "گشت‌زنی", "world": "جهان زنده",
}
ENERGY = {"story": 5, "arena": 5, "dungeon": 10, "boss": 15, "wander": 3}
#: tiers of the bot arena: (id, name, strength multiplier, reward multiplier, minimum level)
TIERS: tuple[tuple[str, str, float, float, int], ...] = (
    ("easy", "تازه‌کار", 0.95, 0.8, 1),
    ("normal", "جنگجو", 1.0, 1.0, 1),
    ("hard", "قهرمان", 1.08, 1.6, 8),
    ("legend", "افسانه‌ای", 1.18, 2.5, 20),
)
#: wins a day in the arena that pay in full; later wins pay a third
ARENA_FULL_WINS = 10


#: measured strength of every enemy: a hero (any class, no gear) wins about two fights in three at ``mult = 1.0``;
#: this keeps one «difficulty» number meaning the same thing for a skeleton and a dragon
CALIB: dict[str, float] = {
    "skeleton_raider": 1.56,
    "dark_goblin": 1.46,
    "shadow_wolf": 1.35,
    "stone_guardian": 1.14,
    "cultist": 1.21,
    "dark_commander": 0.79,
    "ash_bandit": 1.19,
    "smuggler": 1.18,
    "burnt_warden": 1.08,
    "forbidden_mage": 1.1,
    "fire_queen": 0.76,
    "ice_wolf": 1.16,
    "frost_wraith": 1.14,
    "ice_knight": 0.88,
    "mirror_shade": 0.9,
    "ice_king": 0.75,
    "blood_giant": 0.81,
    "bridge_keeper": 0.84,
    "shadow_mage": 0.89,
    "lord_of_darkness": 0.58,
    "bot_swordsman": 1.15,
    "bot_archer": 1.11,
    "bot_guard": 1.09,
    "bot_mage": 1.08,
    "bot_bandit": 1.1,
    "bot_knight": 0.89,
    "zombie": 1.44,
    "bone_archer": 1.23,
    "crypt_lord": 0.77,
    "fire_imp": 1.16,
    "lava_beast": 0.99,
    "hell_warden": 0.68,
    "ice_golem": 1.07,
    "frost_archer": 1.15,
    "jailer": 0.72,
    "trap_spirit": 1.11,
    "sentinel": 0.92,
    "temple_guardian": 0.7,
    "drake": 0.99,
    "dragon_cultist": 1.02,
    "dragon_brood": 0.63,
    "boss_undead_king": 0.63,
    "boss_red_dragon": 0.53,
    "boss_time_keeper": 0.56,
    "boss_shadow_lord": 0.5,
    "boss_titan": 0.47,
}


@dataclass(frozen=True)
class Foe:
    id: str
    name: str
    emoji: str
    #: share of an «average hero of that level» for each stat
    hp: float
    atk: float
    defense: float
    speed: float
    #: the skill: name, emoji, kind (phys|magic), power, cooldown in turns, effect (none|pierce|crit|guard)
    skill: tuple[str, str, str, float, int, str]
    #: a line shown before the foe uses its skill, so the hero can answer with a defence
    warn: str = ""

    def fighter(self, level: int, mult: float = 1.0) -> Fighter:
        mult *= CALIB.get(self.id, 1.0)
        hp = round((105 + 11.5 * (level - 1)) * self.hp * mult)
        atk = round((11 + 1.7 * (level - 1)) * self.atk * mult)
        name, emoji, kind, power, cooldown, effect = self.skill
        return Fighter(
            name=self.name, emoji=self.emoji, max_hp=hp, hp=hp, atk=atk,
            defense=round((9 + 1.2 * (level - 1)) * self.defense), magic=atk,
            speed=round((10 + 0.9 * (level - 1)) * self.speed), luck=4, skill_name=name, skill_emoji=emoji,
            skill_kind=kind, skill_power=power, skill_cooldown=cooldown, skill_effect=effect,
        )


def _f(id_, name, emoji, hp, atk, df, sp, skill, warn=""):  # noqa: ANN001, ANN202
    return Foe(id_, name, emoji, hp, atk, df, sp, skill, warn)


FOES: dict[str, Foe] = {f.id: f for f in (
    # chapter 1
    _f("skeleton_raider", "اسکلت مهاجم", "💀", 0.8, 0.8, 0.7, 0.9, ("ضربه‌ی استخوانی", "💥", "phys", 1.4, 4, "none")),
    _f("dark_goblin", "گابلین تاریک", "👺", 0.7, 0.9, 0.5, 1.2, ("خنجر زهرآلود", "🗡️", "phys", 1.4, 4, "crit")),
    _f("shadow_wolf", "گرگ سایه", "🐺", 0.9, 0.9, 0.6, 1.3, ("زوزه‌ی شبانه", "🌙", "phys", 1.5, 4, "none")),
    _f("stone_guardian", "نگهبان سنگی", "🗿", 1.4, 0.8, 1.4, 0.5, ("کوبش سنگین", "🪨", "phys", 1.8, 4, "none"),
       "نگهبان سنگی دست‌های سنگینش را بالا می‌برد"),
    _f("cultist", "پیرو معبد", "🕯️", 0.9, 1.0, 0.8, 1.0, ("نفرین تیره", "✨", "magic", 1.6, 4, "pierce")),
    _f("dark_commander", "فرمانده تاریکی", "👿", 1.8, 1.1, 1.1, 1.0, ("شمشیر نیمه‌شب", "⚔️", "phys", 2.0, 4, "crit"),
       "فرمانده تاریکی شمشیرش را در سایه می‌کشد"),
    # chapter 2
    _f("ash_bandit", "راهزن خاکستر", "🥷", 0.9, 1.0, 0.7, 1.2, ("کمین آتشین", "🔥", "phys", 1.5, 4, "crit")),
    _f("smuggler", "قاچاقچی بازار", "🧳", 1.0, 0.95, 0.8, 1.1, ("خنجر پنهان", "🗡️", "phys", 1.5, 4, "pierce")),
    _f("burnt_warden", "دژبان سوخته", "🛡️", 1.3, 0.9, 1.3, 0.7, ("کوبش آهنین", "🔨", "phys", 1.8, 4, "none"),
       "دژبان سوخته گرز آتشینش را بالا می‌برد"),
    _f("forbidden_mage", "جادوگر ممنوع", "🧙", 0.9, 1.15, 0.7, 1.0, ("صاعقه‌ی ممنوع", "⚡", "magic", 1.8, 4, "pierce"),
       "جادوگر ممنوع کلماتی ناپاک زمزمه می‌کند"),
    _f("fire_queen", "ملکه‌ی آتش", "🔥", 1.9, 1.15, 1.0, 1.1, ("طوفان شعله", "🌋", "magic", 2.2, 4, "pierce"),
       "ملکه‌ی آتش آسمان را سرخ می‌کند"),
    # chapter 3
    _f("ice_wolf", "گرگ یخ", "❄️", 1.0, 1.0, 0.8, 1.3, ("گاز یخ‌زده", "🧊", "phys", 1.6, 4, "none")),
    _f("frost_wraith", "روح یخ", "👻", 0.9, 1.1, 0.6, 1.2, ("لمس سرما", "❄️", "magic", 1.7, 4, "pierce")),
    _f("ice_knight", "شوالیه‌ی یخ", "🧊", 1.4, 1.05, 1.3, 0.8, ("شمشیر زمستان", "⚔️", "phys", 1.9, 4, "crit"),
       "شوالیه‌ی یخ شمشیر زمستان را بالا می‌برد"),
    _f("mirror_shade", "سایه‌ی آینه", "🪞", 1.1, 1.2, 0.9, 1.4, ("بازتاب مرگبار", "💠", "magic", 1.8, 4, "crit")),
    _f("ice_king", "پادشاه یخ", "👑", 2.0, 1.2, 1.2, 1.0, ("بهمن شاهانه", "🏔️", "phys", 2.3, 4, "none"),
       "پادشاه یخ عصای بلورین را به زمین می‌کوبد"),
    # chapter 4
    _f("blood_giant", "غول خونین", "👹", 1.8, 1.2, 1.0, 0.7, ("مشت ویرانگر", "💢", "phys", 2.1, 4, "none"),
       "غول خونین مشتش را بالا می‌برد"),
    _f("bridge_keeper", "نگهبان پل", "🗿", 1.5, 1.1, 1.4, 0.8, ("سد آهنین", "🛡️", "phys", 1.9, 4, "guard")),
    _f("shadow_mage", "جادوگر سایه", "🧙", 1.1, 1.35, 0.8, 1.2, ("تیغ سایه", "🌑", "magic", 2.0, 4, "pierce"),
       "جادوگر سایه تیره‌تر می‌شود"),
    _f("lord_of_darkness", "فرمانروای تاریکی", "🌑", 2.4, 1.4, 1.3, 1.1, ("سقوط شب", "☄️", "magic", 2.6, 4, "pierce"),
       "فرمانروای تاریکی شب را فرو می‌ریزد"),
    # bots of the arena
    _f("bot_swordsman", "شمشیرزن گمنام", "🗡️", 1.0, 1.0, 1.0, 1.0, ("ضربه‌ی متعادل", "⚔️", "phys", 1.6, 4, "none")),
    _f("bot_archer", "کماندار سایه", "🏹", 0.8, 1.2, 0.6, 1.4, ("تیر شکاف‌دار", "🎯", "phys", 1.7, 4, "pierce")),
    _f("bot_guard", "نگهبان آهنین", "🛡️", 1.4, 0.8, 1.4, 0.7, ("کوبش سپر", "🔨", "phys", 1.6, 4, "guard")),
    _f("bot_mage", "جادوگر طوفان", "🧙", 0.85, 1.25, 0.6, 1.1, ("صاعقه", "⚡", "magic", 1.8, 4, "pierce")),
    _f("bot_bandit", "راهزن دره", "🥷", 0.9, 1.1, 0.7, 1.3, ("خنجر ناگهانی", "🗡️", "phys", 1.6, 4, "crit")),
    _f("bot_knight", "شوالیه‌ی سیاه", "🐴", 1.3, 1.1, 1.2, 0.9, ("یورش تاریک", "⚔️", "phys", 1.9, 4, "crit")),
    # dungeons
    _f("zombie", "زامبی گندیده", "🧟", 1.1, 0.8, 0.6, 0.6, ("چنگ مرده", "🖐️", "phys", 1.5, 4, "none")),
    _f("bone_archer", "کماندار استخوانی", "☠️", 0.8, 1.1, 0.6, 1.1, ("تیر پوسیده", "🏹", "phys", 1.6, 4, "pierce")),
    _f("crypt_lord", "سرور دخمه", "💀", 1.9, 1.15, 1.1, 0.9, ("فرمان مردگان", "☠️", "magic", 2.1, 4, "pierce"),
       "سرور دخمه استخوان‌ها را فرا می‌خواند"),
    _f("fire_imp", "شیطک آتشین", "😈", 0.8, 1.15, 0.6, 1.4, ("جرقه‌ی دوزخ", "🔥", "magic", 1.6, 4, "none")),
    _f("lava_beast", "هیولای گداخته", "🌋", 1.4, 1.05, 1.0, 0.7, ("تف گداخته", "🔥", "phys", 1.9, 4, "none")),
    _f("hell_warden", "نگهبان دوزخ", "👹", 2.0, 1.25, 1.1, 1.0, ("زنجیر آتش", "⛓️", "phys", 2.3, 4, "crit"),
       "نگهبان دوزخ زنجیرهای سرخ را می‌چرخاند"),
    _f("ice_golem", "گولم یخ‌زده", "🧊", 1.4, 0.9, 1.3, 0.6, ("مشت یخ‌زده", "❄️", "phys", 1.7, 4, "none")),
    _f("frost_archer", "کماندار زمستان", "🏹", 0.85, 1.1, 0.7, 1.2, ("تیر سرد", "❄️", "phys", 1.6, 4, "pierce")),
    _f("jailer", "زندان‌بان یخ", "⛓️", 2.0, 1.2, 1.2, 0.9, ("قفل زمستان", "🔒", "phys", 2.2, 4, "guard"),
       "زندان‌بان یخ کلیدهای یخی‌اش را به صدا درمی‌آورد"),
    _f("trap_spirit", "روح تله", "🪤", 0.9, 1.05, 0.8, 1.3, ("تیغ پنهان", "🗡️", "phys", 1.6, 4, "crit")),
    _f("sentinel", "دیده‌بان باستانی", "🗿", 1.5, 1.0, 1.4, 0.7, ("نگاه سنگی", "👁️", "magic", 1.8, 4, "pierce")),
    _f("temple_guardian", "نگهبان معبد", "🏛️", 2.0, 1.2, 1.3, 0.9, ("داوری خدایان", "⚖️", "magic", 2.3, 4, "pierce"),
       "نگهبان معبد داوری خدایان را فرا می‌خواند"),
    _f("drake", "اژدهای نوزاد", "🦎", 1.2, 1.1, 0.9, 1.1, ("نفس گرم", "🔥", "magic", 1.8, 4, "none")),
    _f("dragon_cultist", "پرستشگر اژدها", "🐉", 1.0, 1.2, 0.8, 1.0, ("آیین آتش", "🔥", "magic", 1.8, 4, "pierce")),
    _f("dragon_brood", "مادر اژدها", "🐲", 2.2, 1.3, 1.2, 1.0, ("نفس ویرانگر", "🔥", "magic", 2.5, 4, "pierce"),
       "مادر اژدها نفس عمیقی می‌کشد"),
    # solo bosses
    _f("boss_undead_king", "پادشاه مردگان", "💀", 2.6, 1.3, 1.2, 0.9, ("لمس مرگ", "☠️", "magic", 2.0, 4, "pierce"),
       "پادشاه مردگان دست استخوانی‌اش را دراز می‌کند؛ این ضربه زره را نمی‌شناسد"),
    _f("boss_red_dragon", "اژدهای سرخ", "🐉", 3.0, 1.4, 1.2, 1.0, ("نفس آتشین", "🔥", "magic", 2.6, 3, "none"),
       "اژدهای سرخ نفس عمیقی می‌کشد؛ هر سه نوبت یک بار آتش می‌ریزد، دفاع کنید"),
    _f("boss_time_keeper", "نگهبان زمان", "⏳", 2.4, 1.3, 1.1, 1.6, ("توقف زمان", "⌛", "magic", 2.0, 2, "crit"),
       "نگهبان زمان ساعت شنی را برمی‌گرداند؛ تندتر از شماست و ضربه‌ی کاری می‌زند"),
    _f("boss_shadow_lord", "فرمانروای سایه‌ها", "🌑", 3.0, 1.4, 1.3, 1.2, ("کمین سایه", "🌑", "phys", 2.4, 3, "guard"),
       "فرمانروای سایه‌ها در تاریکی ناپدید می‌شود تا ضربه‌ی بعدی را سپر کند"),
    _f("boss_titan", "تایتان باستانی", "🗿", 4.2, 1.5, 1.6, 0.6, ("لرزش زمین", "🌍", "phys", 3.0, 5, "none"),
       "تایتان باستانی زمین را به لرزه می‌اندازد؛ کند است اما ضربه‌اش سنگین"),
)}


def get_foe(foe_id: str) -> Foe:
    return FOES[foe_id]


# --- the bot arena ------------------------------------------------------------------------------------------------------------
ARENA_BOTS = ("bot_swordsman", "bot_archer", "bot_guard", "bot_mage", "bot_bandit", "bot_knight")


def get_tier(tier_id: str) -> tuple[str, str, float, float, int]:
    return next(t for t in TIERS if t[0] == tier_id)


# --- the story ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage:
    number: int
    chapter: int
    title: str
    emoji: str
    text: str
    foe: str
    #: labels of the three ways to meet the danger (see ``STYLES``)
    labels: dict[str, str] = field(default_factory=dict)
    #: the last stage of a chapter: a boss, with a better prize
    boss: bool = False


#: what each way of meeting a fight changes: foe hit points, foe attack, a shield for the hero, gold and experience shares
STYLES: dict[str, dict[str, float]] = {
    "fight": {"foe_hp": 1.0, "foe_atk": 1.0, "shield": 0, "gold": 1.0, "xp": 1.0},
    "careful": {"foe_hp": 1.0, "foe_atk": 1.0, "shield": 1, "gold": 0.8, "xp": 0.8},
    "bold": {"foe_hp": 1.0, "foe_atk": 1.2, "shield": 0, "gold": 1.4, "xp": 1.4},
    "scout": {"foe_hp": 0.85, "foe_atk": 1.0, "shield": 0, "gold": 1.0, "xp": 1.0},
    "mercy": {"foe_hp": 1.0, "foe_atk": 1.0, "shield": 0, "gold": 0.7, "xp": 1.5},
    "plunder": {"foe_hp": 1.0, "foe_atk": 1.0, "shield": 0, "gold": 1.6, "xp": 0.7},
}
STYLE_HINTS = {
    "fight": "بی‌پروا و مستقیم؛ پاداش عادی",
    "careful": "با احتیاط و سپر؛ پاداش کمتر",
    "bold": "جسورانه؛ دشمن خشمگین‌تر ولی پاداش بیشتر",
    "scout": "بررسی پیش از نبرد؛ دشمن ضعیف‌تر شروع می‌کند",
    "mercy": "با رحم و کمک؛ تجربه‌ی بیشتر، سکه‌ی کمتر",
    "plunder": "غارت و طمع؛ سکه‌ی بیشتر، تجربه‌ی کمتر",
}
CHAPTERS: dict[int, tuple[str, str, int, float]] = {
    1: ("طلوع تاریکی", "🌑", 1, 0.85),
    2: ("شهر خاکستر", "🔥", 5, 0.9),
    3: ("کوه‌های یخ‌زده", "🧊", 12, 0.95),
    4: ("دل تاریکی", "🌌", 20, 1.0),
}

STAGES: tuple[Stage, ...] = (
    Stage(1, 1, "صدای ناشناس", "🌑", "نیمه‌شب است. فریادی از روستایی نزدیک جنگل به گوش می‌رسد. وقتی می‌رسی، موجوداتی تیره به مردم حمله کرده‌اند و پیرمردی زخمی از تو یاری می‌خواهد.", "skeleton_raider",
          {"fight": "⚔️ مبارزه با اسکلت", "scout": "🔍 بررسی اطراف روستا", "mercy": "🤝 اول پیرمرد را نجات بده"}),
    Stage(2, 1, "روستای متروکه", "🏚️", "از میان کوچه‌های خالی می‌گذری. بوی خاکستر و سایه‌هایی که بی‌صدا می‌دوند. گابلینی تاریک در انبار غله کمین کرده است.", "dark_goblin",
          {"fight": "⚔️ وارد انبار شو", "careful": "🛡️ با احتیاط و سپر پیش برو", "plunder": "💰 اول گنجینه‌ی روستا را بردار"}),
    Stage(3, 1, "جنگل نفرین‌شده", "🌲", "درختان خمیده‌اند و چشم‌هایی سبز از تاریکی نگاهت می‌کنند. گرگی از سایه بیرون می‌آید و راهت را می‌بندد.", "shadow_wolf",
          {"fight": "⚔️ رو در رو بجنگ", "bold": "🔥 جسورانه یورش ببر", "scout": "👣 ردپاها را بخوان"}),
    Stage(4, 1, "نگهبان باستانی", "🗿", "در ورودی دره، پیکره‌ای سنگی بیدار می‌شود. «کسی بدون آزمون نمی‌گذرد.» زمین زیر پایش می‌لرزد.", "stone_guardian",
          {"fight": "⚔️ آزمون را بپذیر", "careful": "🛡️ دفاع کن و فرسوده‌اش کن", "scout": "🔍 نقطه‌ضعفش را بجوی"}),
    Stage(5, 1, "معبد فراموش‌شده", "🛕", "معبدی زیر خزه‌ها پنهان است. نقش‌های روی دیوار از رازی کهن می‌گویند و پیروی تیره‌پوش آیینی نیمه‌کاره را دنبال می‌کند.", "cultist",
          {"fight": "⚔️ آیین را بر هم بزن", "mercy": "🕯️ شمع‌ها را خاموش کن و بگذار تسلیم شود", "plunder": "💎 جام قربانی را بربا"}),
    Stage(6, 1, "فرمانده تاریکی", "👿", "پایان فصل. در تالار آخر، فرمانده‌ی تاریکی بر تختی از استخوان نشسته است. «تو پایان این روشنایی هستی؟»", "dark_commander",
          {"fight": "⚔️ به نبرد پایانی برو", "careful": "🛡️ سپر بالا و آرام پیش برو", "bold": "🔥 با تمام توان حمله کن"}, boss=True),
    Stage(7, 2, "گذرگاه خاکستر", "🌫️", "از شهر سوخته نشان‌هایی به جا مانده. راهزنی خاکستری‌پوش گذرگاه را بسته و باج می‌خواهد.", "ash_bandit",
          {"fight": "⚔️ باج نده و بجنگ", "bold": "🔥 بی‌هشدار حمله کن", "plunder": "💰 غنیمتش را هم بردار"}),
    Stage(8, 2, "بازار سایه‌ها", "🏮", "در بازار زیرزمینی، تاجری رازآلود نقشه‌ای می‌فروشد. وقتی نمی‌خری، قاچاقچی‌اش خنجر می‌کشد.", "smuggler",
          {"fight": "⚔️ دفاع کن", "scout": "🔍 پیش از نبرد کیسه‌اش را بررسی کن", "mercy": "🤝 بگذار فرار کند"}),
    Stage(9, 2, "دروازه‌ی سوخته", "🚪", "دروازه‌ی بزرگ شهر نیمه‌ذوب شده و دژبانی سوخته هنوز نگهبانی می‌دهد، بی‌خبر از آنکه شهر مرده است.", "burnt_warden",
          {"fight": "⚔️ از دروازه بگذر", "careful": "🛡️ با سپر نزدیک شو", "mercy": "🕊️ به او بگو جنگ تمام شده"}),
    Stage(10, 2, "کتابخانه‌ی ممنوع", "📚", "طومارهای سوخته در هوا می‌چرخند و جادوگری که قرن‌ها حبس بوده، کلمات ناپاک زمزمه می‌کند.", "forbidden_mage",
           {"fight": "⚔️ جادوگر را متوقف کن", "scout": "🔍 طومارها را بخوان", "plunder": "📜 طومار کمیاب را بردار"}),
    Stage(11, 2, "ملکه‌ی آتش", "🔥", "پایان فصل. در دل کاخ گداخته، ملکه‌ی آتش از میان شعله‌ها برمی‌خیزد. «شهر مرا سوزاندند و تو آمده‌ای؟»", "fire_queen",
           {"fight": "⚔️ ملکه را به چالش بکش", "careful": "🛡️ سپر بالا", "bold": "🔥 آتش را با آتش پاسخ بده"}, boss=True),
    Stage(12, 3, "گذر طوفان", "🌨️", "طوفان برفی راه کوهستان را بسته. گرگی سپید از میان برف‌ها می‌آید و دندان‌هایش مثل یخ برق می‌زند.", "ice_wolf",
           {"fight": "⚔️ در برف بجنگ", "bold": "🔥 پیش از رسیدنش حمله کن", "careful": "🛡️ پشت صخره دفاع کن"}),
    Stage(13, 3, "غار زمزمه‌ها", "🕳️", "در غار صداهایی نجوا می‌کنند: نام‌های گمشدگان. روحی سرد از دیواره بیرون می‌آید.", "frost_wraith",
           {"fight": "⚔️ روح را بران", "mercy": "🕯️ نام‌هایشان را به یاد بیاور", "scout": "🔍 منبع زمزمه را بیاب"}),
    Stage(14, 3, "قلعه‌ی فراموشی", "🏰", "قلعه‌ای از یخ، پر از زره‌های خالی. شوالیه‌ای یخی هنوز به عهد قدیم وفادار است.", "ice_knight",
           {"fight": "⚔️ به دوئل شوالیه برو", "careful": "🛡️ با احتیاط ضربه‌هایش را بگیر", "plunder": "👑 شمشیر قدیمی‌اش را بخواه"}),
    Stage(15, 3, "تالار آینه‌ها", "🪞", "در تالار، هزار آینه تو را نشان می‌دهند، و یکی از آن‌ها بیرون می‌آید و شبیه تو می‌جنگد.", "mirror_shade",
           {"fight": "⚔️ با سایه‌ات بجنگ", "scout": "🔍 آینه‌ی اصلی را پیدا کن", "bold": "🔥 تردید نکن"}),
    Stage(16, 3, "پادشاه یخ", "👑", "پایان فصل. بر تخت بلورین، پادشاه یخ عصایش را به زمین می‌کوبد. «زمستان هیچ‌گاه نمی‌میرد.»", "ice_king",
           {"fight": "⚔️ پادشاه را به نبرد بخوان", "careful": "🛡️ سپر بالا و فرسوده‌اش کن", "bold": "🔥 با شعله بجنگ"}, boss=True),
    Stage(17, 4, "رود خون", "🩸", "رودی سرخ از دل زمین می‌جوشد و غولی که از آن سیراب شده، پیش‌رویت می‌ایستد.", "blood_giant",
           {"fight": "⚔️ غول را از پا بینداز", "careful": "🛡️ از ضربه‌هایش جاخالی بده", "bold": "🔥 به چشمانش حمله کن"}),
    Stage(18, 4, "پل شکسته", "🌉", "پل باستانی تنها گذرگاه است و نگهبانی آهنین هنوز آن را پاس می‌دارد.", "bridge_keeper",
           {"fight": "⚔️ نگهبان را کنار بزن", "scout": "🔍 قفل پل را پیدا کن", "mercy": "🕊️ از او بخواه کنار برود"}),
    Stage(19, 4, "برج سایه", "🗼", "در بالای برج، جادوگری سایه را می‌نویسد. هر پله تو را به تاریکی نزدیک‌تر می‌کند.", "shadow_mage",
           {"fight": "⚔️ تا بالای برج بجنگ", "careful": "🛡️ سپر بالا و پله‌پله بالا برو", "plunder": "💰 عصای سایه را بربا"}),
    Stage(20, 4, "فرمانروای تاریکی", "🌌", "پایان داستان. در دل شب، فرمانروای تاریکی سر برمی‌آورد. «هزار سال منتظرت بودم، قهرمان.»", "lord_of_darkness",
           {"fight": "⚔️ سرنوشت را رقم بزن", "careful": "🛡️ سپر بالا", "bold": "🔥 همه‌چیز را به خطر بینداز"}, boss=True),
)
_STAGE = {s.number: s for s in STAGES}
CHAPTER_DONE_CRYSTALS = 3
#: a stage is graded by the health the hero kept: 1 bronze (won), 2 silver (40%+), 3 gold (75%+)
GRADES = {1: "برنزی", 2: "نقره‌ای", 3: "طلایی"}


def get_stage(number: int) -> Stage:
    return _STAGE[number]


def stage_reward(stage: Stage) -> tuple[int, int]:
    """Base gold and experience for a stage (scaled by the hero's level later)."""
    boss = 2 if stage.boss else 1
    return (30 + 10 * stage.number) * boss, (40 + 8 * stage.number) * boss


# --- daily dungeons ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Dungeon:
    id: str
    emoji: str
    name: str
    blurb: str
    foes: tuple[str, str, str]
    boss: str


DUNGEONS: tuple[Dungeon, ...] = (
    Dungeon("crypt", "💀", "دخمه‌ی مردگان", "زامبی‌ها و اسکلت‌هایی که آرام نمی‌گیرند.", ("zombie", "skeleton_raider", "bone_archer"), "crypt_lord"),
    Dungeon("inferno", "🔥", "دوزخ آتشین", "دره‌ای از گدازه و شیاطین شعله‌ور.", ("fire_imp", "lava_beast", "fire_imp"), "hell_warden"),
    Dungeon("prison", "🧊", "زندان یخی", "سلول‌هایی از یخ که اسیرانش دیگر انسان نیستند.", ("ice_golem", "frost_archer", "frost_wraith"), "jailer"),
    Dungeon("temple", "🏛️", "معبد باستانی", "تله‌ها و نگهبانان سنگی که هزاره‌ها بیدارند.", ("trap_spirit", "sentinel", "cultist"), "temple_guardian"),
    Dungeon("lair", "🐲", "لانه‌ی اژدها", "آتش، طلا و مادری که نمی‌بخشد.", ("drake", "dragon_cultist", "drake"), "dragon_brood"),
)
FLOORS = 5
_DUNGEON = {d.id: d for d in DUNGEONS}


def get_dungeon(dungeon_id: str) -> Dungeon:
    return _DUNGEON[dungeon_id]


def todays_dungeons(day: int) -> list[Dungeon]:
    """Three of the five dungeons are open each day; the choice rotates."""
    return [DUNGEONS[(day + i) % len(DUNGEONS)] for i in range(3)]


def floor_foe(dungeon: Dungeon, floor: int) -> str:
    return dungeon.boss if floor == FLOORS else dungeon.foes[(floor - 1) % 3]


def floor_mult(floor: int) -> float:
    return 0.74 + 0.05 * floor


def floor_reward(floor: int) -> tuple[int, int]:
    return 25 + 12 * floor, 35 + 10 * floor


# --- solo bosses --------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SoloBoss:
    foe: str
    min_level: int
    #: strength multiplier on top of the foe's own numbers
    mult: float
    gold: int
    xp: int
    crystal: int
    item: tuple[str, int]


SOLO_BOSSES: tuple[SoloBoss, ...] = (
    SoloBoss("boss_undead_king", 5, 1.0, 900, 700, 2, ("magic_chest", 1)),
    SoloBoss("boss_red_dragon", 12, 1.02, 1_800, 1_400, 3, ("magic_chest", 1)),
    SoloBoss("boss_time_keeper", 20, 1.02, 3_000, 2_300, 4, ("royal_chest", 1)),
    SoloBoss("boss_shadow_lord", 28, 1.03, 4_500, 3_400, 5, ("royal_chest", 1)),
    SoloBoss("boss_titan", 35, 1.05, 7_000, 5_200, 6, ("royal_chest", 1)),
)


def get_solo_boss(foe_id: str) -> SoloBoss:
    return next(b for b in SOLO_BOSSES if b.foe == foe_id)


# --- events on the road -------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Choice:
    label: str
    #: what happens: {"gold": (a, b)}, {"xp": (a, b)}, {"item": (id, qty)}, {"crystal": n}, {"pay": gold}, {"fight": foe}, {"text": ...}
    #: or {"chance": p, "win": {...}, "lose": {...}}
    result: dict


@dataclass(frozen=True)
class RoadEvent:
    id: str
    emoji: str
    title: str
    text: str
    choices: tuple[Choice, ...]


EVENTS: tuple[RoadEvent, ...] = (
    RoadEvent("traveler", "🩹", "مسافر زخمی", "مسافری کنار جاده افتاده و از درد می‌نالد. کیسه‌اش پر از چیزهای باارزش است.", (
        Choice("🤝 کمکش کن", {"xp": (60, 120), "gold": (20, 60), "text": "مسافر سپاس‌گزار است و نشانه‌ای از قدردانی می‌دهد."}),
        Choice("💰 کیسه‌اش را بردار", {"gold": (150, 300), "text": "کیسه را برداشتی و دور شدی؛ وجدانت کمی سنگین است."}),
    )),
    RoadEvent("chest", "📦", "صندوق گنج", "میان بوته‌ها صندوقی کهنه پیدا کردی. قفلش زنگ‌زده است.", (
        Choice("🔓 قفل را بشکن", {"chance": 0.65, "win": {"gold": (120, 260), "item": ("wooden_chest", 1), "text": "قفل شکست و گنج در دستان توست!"},
                                  "lose": {"text": "تله بود! چیزی عایدت نشد و کمی سر خوردی."}}),
        Choice("🚶 کنار بگذر", {"xp": (10, 25), "text": "با احتیاط دور شدی؛ کنجکاوی همیشه خوب نیست."}),
    )),
    RoadEvent("bandit", "🗡️", "راهزن", "راهزنی از پشت درختان بیرون می‌پرد: «هرچه داری بده!»", (
        Choice("⚔️ بجنگ", {"fight": "bot_bandit"}),
        Choice("💸 باج بده", {"pay": 80, "text": "کیسه‌ات سبک شد، اما بی‌خونریزی گذشتی."}),
    )),
    RoadEvent("trader", "🧳", "تاجر مرموز", "تاجری ردای تیره‌پوش، کیسه‌ای رازآلود را به تو عرضه می‌کند: «فقط ۲۰۰ سکه!»", (
        Choice("💰 بخر", {"pay": 200, "chance": 0.7, "win": {"item": ("big_energy_potion", 2), "text": "داخل کیسه دو معجون انرژی بزرگ بود!"},
                          "lose": {"text": "کیسه پر از سنگ بود؛ فریب خوردی."}}),
        Choice("🚶 نه، ممنون", {"text": "تاجر شانه بالا انداخت و در تاریکی گم شد."}),
    )),
    RoadEvent("path", "🧭", "مسیر مخفی", "پشت آبشاری راهی سنگی پیدا کردی که به دخمه‌ای ناشناخته می‌رود.", (
        Choice("🕳️ واردش شو", {"chance": 0.6, "win": {"crystal": 2, "gold": (100, 200), "text": "در دخمه کریستال‌های درخشانی یافتی!"},
                               "lose": {"xp": (20, 40), "text": "راه بن‌بست بود، ولی چیزهایی یاد گرفتی."}}),
        Choice("📜 نقشه بکش و برگرد", {"xp": (30, 60), "text": "مسیر را در نقشه‌ات ثبت کردی."}),
    )),
    RoadEvent("well", "⛲", "چاه کهن", "کنار جاده چاهی قدیمی است که کسی ته آن می‌خواند: «سکه‌ای بینداز تا آرزویت برآورده شود.»", (
        Choice("🪙 سکه بینداز", {"pay": 40, "chance": 0.55, "win": {"gold": (120, 260), "text": "صدای خنده‌ای آمد و کیسه‌ای از چاه بالا آمد."},
                                "lose": {"xp": (10, 30), "text": "هیچ اتفاقی نیفتاد؛ فقط پژواک آرزویتان."}}),
        Choice("📣 بلند آرزو کن", {"xp": (40, 90), "text": "خواندن چاه آرام شد و حس سبکی کردی."}),
        Choice("🚶 بگذر", {"text": "از کنار چاه گذشتی؛ صدا تا مدتی دنبالت آمد."}),
    )),
    RoadEvent("caravan", "🐪", "کاروان تاجران", "کاروانی بزرگ از دور می‌آید و نگهبانی برای مسیر کوهستان می‌خواهد.", (
        Choice("🛡️ نگهبانی کن", {"gold": (90, 180), "xp": (30, 70), "text": "مسیر را پاس داشتی و سرپرست کاروان مزدت را داد."}),
        Choice("🗡️ باج بگیر", {"chance": 0.5, "win": {"gold": (200, 360), "text": "ترسیدند و باج را دادند."}, "lose": {"fight": "bot_bandit"}}),
    )),
    RoadEvent("hermit", "🧙", "گوشه‌نشین کوه", "پیرمردی در غاری آتش روشن کرده و می‌گوید: «بنشین؛ هر کس حکایتی دارد.»", (
        Choice("🍵 بنشین و گوش بده", {"xp": (80, 140), "text": "حکایتش پر از درس بود و تو غنی‌تر برخاستی."}),
        Choice("💬 از او راهنمایی بخواه", {"chance": 0.6, "win": {"item": ("herb", 4), "xp": (30, 60), "text": "جای گیاهی کمیاب را نشانت داد."}, "lose": {"text": "فقط خندید و گفت: «خودت پیدا کن.»"}}),
    )),
    RoadEvent("duel", "🤺", "شوالیه‌ی دوره‌گرد", "شوالیه‌ای زره‌پوش راه را بسته و مبارزه می‌خواهد: «برای شرافت، نه خون.»", (
        Choice("⚔️ بپذیر", {"fight": "bot_knight"}),
        Choice("🙇 تعظیم کن و بگذر", {"xp": (20, 50), "text": "شوالیه سر تکان داد و راه را باز کرد."}),
    )),
    RoadEvent("fisher", "🎣", "ماهی‌گیر قدیمی", "ماهی‌گیری کنار رود می‌گوید قلاب جادویی‌اش را به تو قرض می‌دهد.", (
        Choice("🎣 قلاب بینداز", {"chance": 0.6, "win": {"gold": (80, 200), "item": ("wooden_chest", 1), "text": "ماهی نبود؛ صندوقچه‌ای به قلاب افتاد!"}, "lose": {"text": "فقط چکمه‌ای کهنه صید شد."}}),
        Choice("🍢 با او غذا بخور", {"xp": (30, 70), "gold": (20, 50), "text": "شام گرمی خوردی و ماهی‌گیر کمی سکه هم داد."}),
    )),
    RoadEvent("ruins", "🏛️", "ویرانه‌ی باستانی", "ستون‌های شکسته‌ای میان درختان پیداست؛ روی یکی نقشی درخشان می‌تپد.", (
        Choice("🔍 ویرانه را بگرد", {"chance": 0.55, "win": {"gold": (140, 280), "crystal": 1, "text": "زیر آوار یک کریستال کهن پیدا کردی!"}, "lose": {"xp": (15, 35), "text": "جز خاک و عنکبوت چیزی نبود."}}),
        Choice("📖 نقش ستون را بخوان", {"xp": (60, 120), "text": "نوشته‌ای باستانی را خواندی و چیزی از آن آموختی."}),
    )),
    RoadEvent("orphan", "🧒", "کودک گمشده", "کودکی کنار جاده گریه می‌کند و می‌گوید راه خانه‌اش را گم کرده.", (
        Choice("🤝 همراهش برو", {"xp": (70, 130), "gold": (30, 80), "text": "کودک را به خانه رساندی و مادرش دعایت کرد."}),
        Choice("🗺️ نقشه‌اش را بده و برو", {"xp": (10, 30), "text": "نقشه را دادی و راهت را رفتی."}),
    )),
    RoadEvent("gambler", "🎲", "قمارباز جاده", "مردی با تاس‌های عاجی می‌گوید: «یک دست بازی؟ برنده همه را می‌برد.»", (
        Choice("🎲 بازی کن", {"pay": 100, "chance": 0.45, "win": {"gold": (250, 450), "text": "تاس‌ها به نفع تو آمد!"}, "lose": {"text": "باختی؛ قمارباز با لبخند سکه‌ها را جمع کرد."}}),
        Choice("🙅 نه، ممنون", {"xp": (10, 25), "text": "قمارباز شانه بالا انداخت و رفت."}),
    )),
    RoadEvent("storm", "⛈️", "توفان ناگهانی", "آسمان سیاه شده و باد درخت‌ها را خم می‌کند. پناهگاهی دور و نزدیک نیست.", (
        Choice("🏃 تا غار بدو", {"chance": 0.65, "win": {"xp": (40, 80), "gold": (30, 90), "text": "به غار رسیدی و در آن چند سکه‌ی فراموش‌شده یافتی."}, "lose": {"text": "توفان خیست کرد، اما چیزی از دست ندادی."}}),
        Choice("🛡️ سپر بالا بگیر", {"xp": (30, 60), "text": "ایستادی و توفان گذشت؛ استوارتر شدی."}),
    )),
    RoadEvent("shrine", "🛕", "زیارتگاه کوچک", "زیارتگاهی گوشه‌ی راه است با کاسه‌ای پر از سکه‌ی نذری.", (
        Choice("🙏 نذر کن", {"pay": 60, "chance": 0.7, "win": {"xp": (90, 160), "crystal": 1, "text": "حس کردی نیرویی بر تو سایه افکند."}, "lose": {"xp": (20, 40), "text": "آرام گرفتی؛ همین هم کم نیست."}}),
        Choice("🪙 از کاسه بردار", {"chance": 0.4, "win": {"gold": (120, 220), "text": "کسی ندید و کیسه‌ات پر شد."}, "lose": {"fight": "trap_spirit"}}),
    )),
    RoadEvent("bard", "🪕", "نوازنده‌ی دوره‌گرد", "نوازنده‌ای کنار آتش داستان قهرمانان را می‌خواند و کلاهش را پیش می‌آورد.", (
        Choice("🪙 سکه بینداز", {"pay": 30, "xp": (60, 120), "text": "آواز او جانی تازه به تو داد."}),
        Choice("🎶 با او همخوانی کن", {"chance": 0.5, "win": {"gold": (60, 140), "xp": (30, 70), "text": "جمعیت دست زد و کلاه پر از سکه شد؛ سهم تو هم رسید."}, "lose": {"text": "صدایت خشن بود؛ همه خندیدند."}}),
    )),
    RoadEvent("ambush", "🏹", "کمین", "ناگهان تیری کنار پایت به خاک می‌نشیند؛ کسی از دور شما را می‌پاید.", (
        Choice("🛡️ پشت سنگ پناه بگیر", {"chance": 0.6, "win": {"xp": (50, 100), "text": "کمین‌گر خسته شد و رفت."}, "lose": {"fight": "bot_archer"}}),
        Choice("🏃 به سمتش بدو", {"fight": "bot_archer"}),
    )),
    RoadEvent("merchant_cart", "🛒", "گاری فروشنده", "گاری‌ای وسط راه خراب شده؛ فروشنده کمک می‌خواهد و وعده‌ی پاداش می‌دهد.", (
        Choice("🔧 تعمیر کن", {"xp": (50, 100), "item": ("iron_ore", 3), "text": "گاری راه افتاد و فروشنده سنگ آهنی هدیه داد."}),
        Choice("📦 بارش را بخر", {"pay": 150, "chance": 0.65, "win": {"item": ("crystal_shard", 2), "text": "داخل بار خرده‌کریستال بود!"}, "lose": {"text": "بار فقط سفال بود."}}),
    )),
    RoadEvent("wolf_pack", "🐺", "گله‌ی گرگ", "زوزه‌ای از تپه می‌آید و چشمانی در تاریکی می‌درخشند.", (
        Choice("🔥 آتش روشن کن", {"chance": 0.7, "win": {"xp": (40, 90), "text": "گرگ‌ها از آتش ترسیدند و رفتند."}, "lose": {"fight": "shadow_wolf"}}),
        Choice("⚔️ بجنگ", {"fight": "shadow_wolf"}),
    )),
    RoadEvent("treasure_map", "🗺️", "نقشه‌ی گنج", "لای پرچین‌ها، پارچه‌ای پیدا کردی که روی آن نقشه‌ی گنجی کشیده شده.", (
        Choice("🧭 دنبال نقشه برو", {"chance": 0.5, "win": {"gold": (220, 420), "item": ("magic_chest", 1), "text": "سرانجام گنج پیدا شد؛ صندوقچه‌ای جادویی!"}, "lose": {"xp": (30, 60), "text": "نقشه قدیمی بود و گنج را خیلی وقت پیش برده بودند."}}),
        Choice("💰 نقشه را بفروش", {"gold": (90, 160), "text": "نقشه را فروختی و کیسه‌ات سنگین شد."}),
    )),
    RoadEvent("ghost_bridge", "🌉", "پل ارواح", "پلی کهنه روی رودی مه‌آلود؛ نجواهایی از زیرش بالا می‌آید.", (
        Choice("🚶 از پل بگذر", {"chance": 0.6, "win": {"xp": (60, 120), "gold": (40, 100), "text": "ارواح تو را نادیده گرفتند و تو گذشتی."}, "lose": {"fight": "frost_wraith"}}),
        Choice("🕯️ برای ارواح دعا بخوان", {"xp": (50, 110), "text": "نجواها آرام شد و حس آرامشی کردی."}),
    )),
    RoadEvent("stranger", "🎭", "غریبه‌ی ناشناس", "غریبه‌ای در سایه می‌گوید کاری برایت دارد: «حلقه‌ام را از تپه‌ی جنگل بیاور.»", (
        Choice("✅ بپذیر", {"xp": (90, 160), "gold": (60, 120), "text": "حلقه را آوردی و غریبه سخاوتمندانه پاداش داد."}),
        Choice("❌ رد کن", {"text": "غریبه سر تکان داد و رفت؛ هرگز نفهمیدی چه می‌خواست."}),
    )),
)
_EVENT = {e.id: e for e in EVENTS}


def get_event(event_id: str) -> RoadEvent:
    return _EVENT[event_id]
