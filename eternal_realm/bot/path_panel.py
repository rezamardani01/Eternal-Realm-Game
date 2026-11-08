"""«مسیر قهرمانی»: tiers, rewards and the ticket track of the current season."""

from __future__ import annotations

from ..game.data.season import (
    POINTS_PER_TIER, TICKET_PACK, TIERS, reward_for, season_seconds_left,
)
from ..game.data.packs import PACKS
from ..shared.text import bar, bold, duration, fa
from .panel import Ctx, Screen, _int, screen

PER_PAGE_TIERS = 5


def _next_reward(state, track: str):  # noqa: ANN001, ANN202
    for tier in range(state.tier + 1, TIERS + 1):
        reward = reward_for(track, tier)
        if reward:
            return tier, reward
    return None


@screen("path")
async def path(c: Ctx) -> Screen:
    st = await c.services.season.state(c.player)
    price = PACKS[TICKET_PACK].price_toman
    into = st.points - st.tier * POINTS_PER_TIER if st.tier < TIERS else POINTS_PER_TIER
    left = season_seconds_left(c.services.ctx.now())
    lines = [
        f"🎟️ {bold('مسیر قهرمانی')}",
        "",
        f"⏳ پایان فصل: {duration(left)} دیگر",
        f"🏁 مرحله‌ی شما: {fa(st.tier)} از {fa(TIERS)}",
        f"{bar(into, POINTS_PER_TIER, 10)}  {fa(into)}/{fa(POINTS_PER_TIER)}",
        "🎫 بلیط این فصل: " + ("دارید ✔" if st.premium else "ندارید"),
        "",
    ]
    nf = _next_reward(st, "free")
    if nf:
        lines += [f"🎁 جایزه‌ی رایگان بعدی (مرحله‌ی {fa(nf[0])}):", *nf[1].lines(), ""]
    nt = _next_reward(st, "ticket")
    if nt:
        lines += [f"💎 جایزه‌ی بلیط بعدی (مرحله‌ی {fa(nt[0])}):", *nt[1].lines(), ""]
    lines.append("امتیاز مسیر را با ماجراجویی، شکار، دوئل، باس، داستان و سیاه‌چال جمع می‌کنید.")
    ready = st.available()
    rows = []
    if ready:
        lines.append(f"\n🎉 {fa(len(ready))} جایزه آماده‌ی دریافت است!")
        rows.append([c.btn(f"🎁 دریافت همه ({fa(len(ready))})", "pathall", style="success")])
    rows.append([c.btn("📋 مراحل و جایزه‌ها", "pathtiers", max(0, st.tier // PER_PAGE_TIERS))])
    if not st.premium:
        rows.append([c.btn(f"🎟️ خرید بلیط ({fa(price)} تومان)", "prem", "path", style="primary")])
    rows.append(c.back("profile"))
    return Screen("\n".join(lines), rows)


@screen("pathtiers")
async def path_tiers(c: Ctx) -> Screen:
    st = await c.services.season.state(c.player)
    page = max(0, min(_int(c.a or "0"), (TIERS - 1) // PER_PAGE_TIERS))
    first = page * PER_PAGE_TIERS + 1
    lines = [f"📋 {bold('مراحل مسیر قهرمانی')}", f"مرحله‌ی شما: {fa(st.tier)}", ""]
    rows = []
    for tier in range(first, min(TIERS, first + PER_PAGE_TIERS - 1) + 1):
        reached = tier <= st.tier
        lines.append(f"{'✅' if reached else '🔒'} {bold('مرحله‌ی ' + fa(tier))}")
        free, ticket = reward_for("free", tier), reward_for("ticket", tier)
        if free:
            lines.append("رایگان: " + "، ".join(free.lines()))
        if ticket:
            lines.append("بلیط: " + "، ".join(ticket.lines()))
        lines.append("")
        for track, reward, label in (("free", free, "رایگان"), ("ticket", ticket, "بلیط")):
            if reward and reached and (track, tier) not in st.claimed and (track == "free" or st.premium):
                rows.append([c.btn(f"🎁 دریافت {label} · مرحله‌ی {fa(tier)}", "pathget", track, tier)])
    nav = []
    if page > 0:
        nav.append(c.btn("‹ قبلی", "pathtiers", page - 1))
    if first + PER_PAGE_TIERS <= TIERS:
        nav.append(c.btn("بعدی ›", "pathtiers", page + 1))
    if nav:
        rows.append(nav)
    rows.append(c.back("path"))
    return Screen("\n".join(lines).strip(), rows)


@screen("pathget")
async def path_get(c: Ctx) -> Screen:
    reward = await c.services.season.claim(c.player, c.a, _int(c.b))
    shown = await path_tiers(replace_ctx(c, (_int(c.b) - 1) // PER_PAGE_TIERS))
    shown.toast, shown.alert = "🎁 " + "، ".join(reward.lines()), True
    return shown


def replace_ctx(c: Ctx, page: int) -> Ctx:
    from dataclasses import replace

    return replace(c, a=str(page))


@screen("pathall")
async def path_all(c: Ctx) -> Screen:
    done = await c.services.season.claim_all(c.player)
    gold = sum(r.gold for _, _, r in done)
    crystal = sum(r.crystal for _, _, r in done)
    shown = await path(c)
    shown.toast = f"🎁 {fa(len(done))} جایزه گرفتید: {fa(gold)} سکه و {fa(crystal)} کریستال و بیشتر"
    shown.alert = True
    return shown
