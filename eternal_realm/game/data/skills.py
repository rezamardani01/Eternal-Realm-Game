"""Hero skills: every class has three skill *mechanics*, every race dresses them in its own element.

Three slots, three different jobs (this is data: add a class or a race here and the fight engine picks it up):

* slot 1 - the quick one: light damage, short wait;
* slot 2 - the tricky one: heavier damage plus a special effect;
* slot 3 - the signature move: the biggest blow or effect, with the longest wait.

The wait is counted in turns of the fighter, never in seconds: ``cd`` is the value written to the counter when the
skill is used, so a skill with ``cd=3`` stays locked for the next 2 turns and is ready again on the 3rd.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ...shared.text import fa


@dataclass(frozen=True)
class Effect:
    """One thing a skill does besides hitting.

    k  kind (see ``EFFECT_INFO``); v  strength; t  turns it lasts; c  chance (1 = always)
    """

    k: str
    v: float = 0.0
    t: int = 0
    c: float = 1.0


#: effect kind -> (icon, Persian name, how it is explained)
EFFECT_INFO: dict[str, tuple[str, str]] = {
    "poison": ("☠️", "مسموم"),
    "burn": ("🔥", "سوخته"),
    "bleed": ("🩸", "خونریز"),
    "def_down": ("🛡️", "زره‌شکسته"),
    "atk_down": ("🥀", "ضعیف‌شده"),
    "slow": ("🐌", "کُند"),
    "stun": ("💫", "گیج"),
    "freeze": ("❄️", "یخ‌زده"),
    "shock": ("⚡", "شوک‌زده"),
    "regen": ("💚", "بازیابی"),
    "cleanse": ("✨", "پاک‌سازی"),
    "atk_up": ("💢", "خشمگین"),
    "def_up": ("🧱", "مستحکم"),
    "crit_up": ("🎯", "هوشیار"),
    "lifesteal": ("🩸", "جذب جان"),
    "heal": ("💚", "ترمیم"),
    "shield": ("🛡️", "سپر"),
    "execute": ("⚰️", "ضربه‌ی پایان"),
    "pierce": ("🗡️", "زره‌سوز"),
    "crit": ("🎯", "ضربه‌ی کاری حتمی"),
}

DOTS = ("poison", "burn", "bleed")
#: statuses that sit on the *target* (the rest sit on the caster)
HARMFUL = ("poison", "burn", "bleed", "def_down", "atk_down", "slow", "stun", "freeze", "shock")
#: statuses that deal or give something every turn (they tick that many times)
TICKING = DOTS + ("regen",)


@dataclass(frozen=True)
class HeroSkill:
    id: str
    slot: int
    name: str
    emoji: str
    #: "phys" scales with attack, "magic" with the magic stat
    kind: str
    #: damage multiplier of ONE hit
    power: float
    hits: int
    cd: int
    effects: tuple[Effect, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def waits(self) -> int:
        """Turns the skill stays locked after use."""
        return self.cd - 1

    def describe(self) -> list[str]:
        """The facts of the skill, one short line each (shown on the hero's skill page)."""
        hit = f"💥 ضریب آسیب {fa(f'{self.power:.2f}'.rstrip('0').rstrip('.').replace('.', '٫'))}" + (
            f" × {fa(self.hits)} ضربه" if self.hits > 1 else ""
        )
        lines = [hit + (" · ✨ جادویی" if self.kind == "magic" else " · ⚔️ فیزیکی")]
        lines += [effect_text(e) for e in self.effects]
        lines.append(f"⏳ انتظار: {fa(self.waits)} نوبت پس از استفاده")
        return lines


def _pct(x: float) -> str:
    return fa(f"{round(x * 100)}") + "٪"


def effect_text(e: Effect) -> str:
    icon, name = EFFECT_INFO[e.k]
    chance = f" ({_pct(e.c)} شانس)" if e.c < 1 else ""
    turns = f" برای {fa(e.t)} نوبت" if e.t else ""
    if e.k in DOTS:
        return f"{icon} {name}: هر نوبت آسیب بی‌توجه به دفاع{turns}{chance}"
    return {
        "def_down": f"{icon} دفاع دشمن {_pct(e.v)} کم می‌شود{turns}{chance}",
        "atk_down": f"{icon} حمله‌ی دشمن {_pct(e.v)} کم می‌شود{turns}{chance}",
        "slow": f"{icon} دشمن کُند می‌شود و مهارت‌هایش دیرتر آماده می‌شوند{turns}{chance}",
        "stun": f"{icon} دشمن نوبتش را از دست می‌دهد{chance}",
        "freeze": f"{icon} دشمن یخ می‌زند و نمی‌تواند مهارت بزند{turns}{chance}",
        "shock": f"{icon} حمله‌ی دشمن {_pct(e.v)} کم می‌شود{turns}{chance}",
        "regen": f"{icon} هر نوبت {_pct(e.v)} از جان کل‌تان برمی‌گردد{turns}{chance}",
        "cleanse": f"{icon} اثرهای بد (زهر، سوختگی، یخ، ...) از تن‌تان پاک می‌شود{chance}",
        "atk_up": f"{icon} حمله‌ی شما {_pct(e.v)} بیشتر می‌شود{turns}{chance}",
        "def_up": f"{icon} دفاع شما {_pct(e.v)} بیشتر می‌شود{turns}{chance}",
        "crit_up": f"{icon} شانس ضربه‌ی کاری {_pct(e.v)} بیشتر می‌شود{turns}{chance}",
        "lifesteal": f"{icon} {_pct(e.v)} از آسیب به جان شما برمی‌گردد{chance}",
        "heal": f"{icon} {_pct(e.v)} از جان کل‌تان برمی‌گردد{chance}",
        "shield": f"{icon} سپر می‌گیرید؛ ضربه‌ی بعدی نصف می‌شود{chance}",
        "execute": f"{icon} اگر جان دشمن کمتر از ۴۰٪ باشد آسیب {_pct(e.v)} بیشتر می‌شود",
        "pierce": f"{icon} دفاع دشمن را کامل نادیده می‌گیرد",
        "crit": f"{icon} همیشه ضربه‌ی کاری است",
    }[e.k]


# --- the three mechanics of each class --------------------------------------------------------------------------------
#: class -> three (name pattern, emoji, kind, power, hits, effects); ``{a}`` becomes the race's word
CLASS_SKILLS: dict[str, tuple[tuple[str, str, str, float, int, tuple[Effect, ...]], ...]] = {
    "warrior": (
        ("ضربه‌ی زره‌شکن {a}", "🔨", "phys", 1.05, 1, (Effect("def_down", 0.25, 2),)),
        ("تبر دوگانه‌ی {a}", "🪓", "phys", 0.75, 2, (Effect("bleed", 0.16, 3),)),
        ("خشم {a}", "💢", "phys", 2.0, 1, (Effect("atk_up", 0.25, 3), Effect("lifesteal", 0.25))),
    ),
    "mage": (
        ("جرقه‌ی {a}", "✨", "magic", 0.95, 1, (Effect("shock", 0.2, 2),)),
        ("تیغ جادوی {a}", "🔮", "magic", 1.35, 1, (Effect("pierce"), Effect("burn", 0.28, 3))),
        ("ویرانگر {a}", "☄️", "magic", 2.2, 1, (Effect("pierce"), Effect("execute", 0.4))),
    ),
    "archer": (
        ("رگبار {a}", "🏹", "phys", 0.4, 3, ()),
        ("تیر زهرآگین {a}", "☠️", "phys", 1.35, 1, (Effect("pierce"), Effect("poison", 0.24, 3))),
        ("تیر مرگ {a}", "🎯", "phys", 1.9, 1, (Effect("crit"), Effect("slow", 0.3, 2))),
    ),
    "guardian": (
        ("کوبش سپر {a}", "🛡️", "phys", 1.0, 1, (Effect("stun", 0, 1, 0.4),)),
        ("حصار {a}", "🧱", "phys", 1.2, 1, (Effect("shield"), Effect("def_up", 0.35, 3), Effect("regen", 0.04, 3))),
        ("دژ {a}", "🏰", "phys", 1.6, 1, (Effect("heal", 0.22), Effect("cleanse"), Effect("atk_down", 0.25, 3), Effect("shield"))),
    ),
    "rogue": (
        ("خنجر دوگانه‌ی {a}", "🔪", "phys", 0.6, 2, (Effect("crit_up", 0.25, 2),)),
        ("زخم {a}", "🩸", "phys", 1.4, 1, (Effect("bleed", 0.35, 3),)),
        ("ترور {a}", "🌑", "phys", 2.4, 1, (Effect("execute", 0.8), Effect("lifesteal", 0.35))),
    ),
}

#: race -> (adjective used in the skill names, extra effect the race adds to its second skill)
RACE_SKILLS: dict[str, tuple[str, Effect]] = {
    "elf": ("جنگلی", Effect("poison", 0.12, 3, 0.7)),
    "dwarf": ("کوهی", Effect("def_down", 0.15, 2)),
    "fairy": ("پریانی", Effect("freeze", 0.0, 1, 0.35)),
    "dragonborn": ("آتشین", Effect("burn", 0.2, 3)),
    "shadowborn": ("سایه‌ای", Effect("lifesteal", 0.15)),
    "human": ("نورانی", Effect("crit_up", 0.12, 2)),
}

#: skill waits (turns of locking + 1): 2, 3 and 4 blocked turns
SLOT_CD = {1: 3, 2: 4, 3: 5}


def skills_for(race_id: str, class_id: str) -> tuple[HeroSkill, HeroSkill, HeroSkill]:
    """The three skills of a hero of this race and class (the second one carries the race's extra effect)."""
    word, rider = RACE_SKILLS.get(race_id, RACE_SKILLS["human"])
    out = []
    for slot, (pattern, emoji, kind, power, hits, effects) in enumerate(CLASS_SKILLS[class_id], start=1):
        extra = (rider,) if slot == 2 and all(rider.k != e.k for e in effects) else ()
        out.append(
            HeroSkill(f"{class_id}:{race_id}:{slot}", slot, pattern.format(a=word), emoji, kind, power, hits,
                      SLOT_CD[slot], effects + extra)
        )
    return out[0], out[1], out[2]
