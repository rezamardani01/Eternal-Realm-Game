"""The after-fight review: what happened to one hero and a few honest tips, built from the finished battle alone.

Pure functions, no database: the bot adds the tips that depend on the hero's build (spare points, empty gear slots).
"""

from __future__ import annotations

from ...shared.text import fa
from .combat import Battle, power_of


def summary(battle: Battle, index: int) -> list[str]:
    """Lines about how the hero at ``index`` fought."""
    me, foe = battle.fighters[index], battle.fighters[1 - index]
    turns = me.n_attack + me.n_skill + me.n_defend
    return [
        f"🗡️ آسیبی که زدید: {fa(me.dealt)} · آسیبی که خوردید: {fa(foe.dealt)}",
        f"🎬 حرکت‌های شما: {fa(me.n_attack)} حمله · {fa(me.n_skill)} مهارت · {fa(me.n_defend)} دفاع ({fa(turns)} نوبت)",
        f"❤️ جان باقی‌مانده‌ی شما: {fa(round(me.hp_ratio * 100))}٪ · حریف: {fa(round(foe.hp_ratio * 100))}٪",
    ]


def tips(battle: Battle, index: int) -> list[str]:
    """Why the hero lost (or how to win more easily), at most four short tips. A win gets one encouraging remark."""
    me, foe = battle.fighters[index], battle.fighters[1 - index]
    won = battle.winner == index
    out: list[str] = []
    turns = me.n_attack + me.n_skill + me.n_defend
    mine, theirs = power_of(me), power_of(foe)
    if won:
        if mine > 0 and theirs / mine > 1.15:
            out.append("🌟 حریف از شما قوی‌تر بود و بردید؛ انتخاب حرکت‌هایتان عالی بود.")
        elif me.hp_ratio < 0.25:
            out.append("😮‍💨 با جان کم بردید؛ دفاع به‌موقع یا معجون انرژی می‌تواند نبردهای بعدی را راحت‌تر کند.")
        else:
            out.append("👏 نبرد را خوب اداره کردید؛ همین روند را ادامه بدهید.")
        return out
    if battle.winner is None:
        out.append("🤝 نبرد مساوی شد؛ کمی آسیب بیشتر در همان دورها برنده‌تان می‌کرد.")
    if me.has_skills and me.n_skill == 0 and turns >= 2:
        out.append("✨ هیچ مهارتی نزدید؛ مهارت‌ها آسیب و اثر ویژه دارند و بعد از چند نوبت دوباره آماده می‌شوند.")
    if not battle.surrendered and me.n_defend == 0 and me.hp_ratio < 0.4 and turns >= 3:
        out.append("🛡️ وقتی جانتان پایین آمد دفاع نزدید؛ دفاع جان تازه می‌دهد و ضربه‌ی بعدی را سبک‌تر می‌کند.")
    if mine > 0 and theirs / mine >= 1.2:
        out.append(f"⚖️ حریف حدود {fa(round((theirs / mine - 1) * 100))}٪ از شما قوی‌تر بود؛ تجهیزات، ویژگی‌ها و استعدادها شما را هم‌سطح می‌کند.")
    if foe.hp_ratio <= 0.25 and not battle.surrendered:
        out.append(f"🔥 خیلی نزدیک بودید؛ فقط {fa(round(foe.hp_ratio * 100))}٪ از جان حریف مانده بود. یک ضربه‌ی دیگر کافی بود!")
    if battle.round >= battle.max_rounds and battle.winner is not None:
        out.append("⏳ نبرد تا پایان زمانش کشید؛ ضربه‌های سنگین‌تر و کم‌تر دفاع‌کردن در دورهای اول کمک می‌کند.")
    if not out:
        out.append("💡 چند نبرد دیگر هم بجنگید؛ هر نبرد حس بهتری از زمان‌بندی مهارت‌ها می‌دهد.")
    return out[:4]
