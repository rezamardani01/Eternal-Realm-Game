"""«مسیر قهرمانی»: tiers, rewards and the ticket track of the current season."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot
from baleropy.exceptions import BaleAPIError

from ..game.data.season import (
    POINTS_PER_TIER, TICKET_PACK, TIERS, reward_for, season_of, season_seconds_left,
)
from ..game.data.packs import PACKS
from ..shared.text import bar, bold, duration, fa
from . import keyboards
from .panel import Ctx, Screen, _int, screen
from .services import Services

log = logging.getLogger("eternal_realm.path")

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
        "🎫 بلیط طلایی این فصل: " + ("دارید ✔" if st.premium else "ندارید"),
        "",
    ]
    nf = _next_reward(st, "free")
    if nf:
        lines += [f"🎁 جایزه‌ی رایگان بعدی (مرحله‌ی {fa(nf[0])}):", *nf[1].lines(), ""]
    nt = _next_reward(st, "ticket")
    if nt:
        lines += [f"💎 جایزه‌ی طلایی بعدی (مرحله‌ی {fa(nt[0])}):", *nt[1].lines(), ""]
    lines.append("امتیاز مسیر را با ماجراجویی، شکار، دوئل، باس، داستان و سیاه‌چال جمع می‌کنید.")
    ready = st.available()
    rows = []
    if ready:
        lines.append(f"\n🎉 {fa(len(ready))} جایزه آماده‌ی دریافت است!")
        rows.append([c.btn(f"🎁 دریافت همه ({fa(len(ready))})", "pathall", style="success")])
    rows.append([c.btn("📋 مراحل و جایزه‌ها", "pathtiers", max(1, st.tier))])
    if not st.premium:
        rows.append([c.btn(f"🎟️ خرید بلیط ({fa(price)} تومان)", "prem", "path", style="primary")])
    rows.append(c.back("profile"))
    return Screen("\n".join(lines), rows)


@screen("pathtiers")
async def path_tiers(c: Ctx) -> Screen:
    """One tier per page: a free and a golden reward side by side, each part a glass button."""
    st = await c.services.season.state(c.player)
    tier = max(1, min(_int(c.a or "1"), TIERS))
    free, gold = reward_for("free", tier), reward_for("ticket", tier)
    free_parts, gold_parts = free.lines(), gold.lines()
    mark = "✅" if tier <= st.tier else "🔒"

    def part(track: str, parts: list[str], i: int):  # noqa: ANN202
        if i >= len(parts):
            return c.btn("▫️ —", "noop")
        done = (track, tier) in st.claimed
        return c.btn(parts[i] + (" ✔" if done else ""), "pathget", track, tier)

    rows = [[c.btn("🆓 رایگان", "noop"), c.btn("👑 طلایی", "noop")]]
    for i in range(max(len(free_parts), len(gold_parts))):
        rows.append([part("free", free_parts, i), part("ticket", gold_parts, i)])
    rows.append([
        c.btn("مرحله بعدی ›", "pathtiers", min(TIERS, tier + 1)),
        c.btn("‹ مرحله قبلی", "pathtiers", max(1, tier - 1)),
    ])
    rows.append(c.back("path"))
    text = (
        f"🎟️ {bold('مسیر قهرمانی')}\n\n"
        f"{mark} مرحله‌ی {fa(tier)} از {fa(TIERS)} · مرحله‌ی شما: {fa(st.tier)}\n\n"
        "روی هر جایزه بزنید تا به کیفتان بیاید. جایزه‌های رایگان برای همه است و جایزه‌های طلایی با بلیط فصل باز می‌شود."
    )
    return Screen(text, rows)


@screen("pathget")
async def path_get(c: Ctx) -> Screen:
    tier = _int(c.b)
    reward = await c.services.season.claim(c.player, c.a, tier)
    shown = await path_tiers(replace_ctx(c, tier))
    shown.toast, shown.alert = "🎁 " + "، ".join(reward.lines()), True
    return shown


def replace_ctx(c: Ctx, tier: int) -> Ctx:
    from dataclasses import replace

    return replace(c, a=str(tier))


@screen("pathall")
async def path_all(c: Ctx) -> Screen:
    done = await c.services.season.claim_all(c.player)
    gold = sum(r.gold for _, _, r in done)
    crystal = sum(r.crystal for _, _, r in done)
    shown = await path(c)
    shown.toast = f"🎁 {fa(len(done))} جایزه گرفتید: {fa(gold)} سکه و {fa(crystal)} کریستال و بیشتر"
    shown.alert = True
    return shown


# --- telling players that a new tier opened --------------------------------------------------------------
async def notify_new_tiers(bot: Bot, services: Services) -> int:
    """Send one private message to every player whose path has moved up since they were last told."""
    season = season_of(services.ctx.now())
    news: list[tuple[int, int, bool]] = []
    async with services.ctx.db.transaction() as tx:
        rows = await tx.fetchall(
            "SELECT s.player_id, s.points, s.premium, p.platform_user_id AS uid FROM season_progress s"
            " JOIN players p ON p.id = s.player_id WHERE s.season = ? AND s.points / ? > s.notified AND p.banned = 0"
            " LIMIT 200",
            (season, POINTS_PER_TIER),
        )
        for r in rows:
            tier = min(TIERS, r["points"] // POINTS_PER_TIER)
            await tx.execute(
                "UPDATE season_progress SET notified = ? WHERE player_id = ? AND season = ?",
                (tier, r["player_id"], season),
            )
            news.append((r["uid"], tier, bool(r["premium"])))
    sent = 0
    for uid, tier, premium in news:
        track = "رایگان و طلایی" if premium else "رایگان"
        text = (
            f"🎟️ {bold('مسیر قهرمانی')}\n\n"
            f"تبریک! به مرحله‌ی {bold(fa(tier))} رسیدید.\n\n"
            f"برای دریافت جایزه‌های {track} این مرحله، دکمه‌ی زیر را بزنید 👇"
        )
        buttons = [
            [keyboards.panel_button("🎁 دریافت جوایز", "pathall", uid)],
            [keyboards.panel_button("📋 دیدن جایزه‌ها", "pathtiers", uid, str(tier))],
        ]
        with contextlib.suppress(BaleAPIError):  # the player never opened a chat with the bot
            await bot.send_message(uid, text, buttons=buttons)
            sent += 1
    return sent


async def processor(bot: Bot, services: Services, interval: float = 60.0) -> None:
    while True:
        try:
            await notify_new_tiers(bot, services)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("path notifier failed")
        await asyncio.sleep(interval)
