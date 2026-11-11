"""The parts of the game the mini app stages as scenes of their own: the wheel, the hero path and a fight.

Each handler only reads or calls the service the bot's own panel uses, and describes the outcome as plain data so the
page can animate it (a wheel that really turns, a reward track, two fighters facing each other).
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from ..game.data import season as season_data
from ..game.data import solo as solo_data
from ..game.data import wheel as wheel_data
from ..game.data.cards import get_card
from ..game.data.items import get_item
from ..game.data.packs import PACKS
from ..shared.errors import GameError
from . import bridge
from .server import SERVICES, body, hero, item_json, ok, player_json

SPIN_PACKS = ("wheel_1", "wheel_2", "wheel_5", "wheel_10")


# --- the wheel of fortune ------------------------------------------------------------------------------------------------
def _slice(s: wheel_data.Slice) -> dict[str, Any]:
    icon_item = s.items[0][0] if s.items and not s.gold and not s.crystal else ""
    return {
        "id": s.id, "emoji": s.emoji, "label": wheel_data.describe(s), "jackpot": s.jackpot,
        "item": item_json(get_item(icon_item)) if icon_item else None, "gold": s.gold, "crystal": s.crystal,
    }


async def wheel(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    one = PACKS[SPIN_PACKS[0]]
    return ok(
        spins=await services.wheel.spins(p.id), free=await services.wheel.free_ready(p.id),
        slices=[_slice(s) for s in wheel_data.SLICES], free_slices=[_slice(s) for s in wheel_data.FREE_SLICES],
        packs=[
            {"id": pid, "spins": PACKS[pid].spins, "toman": PACKS[pid].price_toman,
             "save": round(100 * (1 - PACKS[pid].price_rial / (PACKS[pid].spins * one.price_rial)))}
            for pid in SPIN_PACKS
        ] if services.ctx.settings.payments_enabled else [],
    )


async def wheel_spin(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    free = bool((await body(request)).get("free"))
    prize, left = await services.wheel.spin(p, free=free)
    return ok(prize=_slice(prize), left=left, free=free)


# --- the hero path ---------------------------------------------------------------------------------------------------------
def _reward(reward: season_data.TierReward) -> dict[str, Any] | None:
    if not reward:
        return None
    return {
        "gold": reward.gold, "crystal": reward.crystal, "title": reward.title,
        "items": [{"item": item_json(get_item(item_id)), "qty": qty} for item_id, qty in reward.items],
        "cards": [{"name": get_card(card_id).name, "emoji": get_card(card_id).emoji} for card_id in reward.cards],
    }


async def path(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    state = await services.season.state(p)
    return ok(
        season=state.season + 1, points=state.points, tier=state.tier, premium=state.premium,
        per_tier=season_data.POINTS_PER_TIER, tiers=season_data.TIERS,
        seconds_left=season_data.season_seconds_left(services.ctx.now()),
        ticket={"id": season_data.TICKET_PACK, "toman": PACKS[season_data.TICKET_PACK].price_toman} if services.ctx.settings.payments_enabled else None,
        track=[
            {
                "tier": tier, "free": _reward(season_data.reward_for("free", tier)), "ticket": _reward(season_data.reward_for("ticket", tier)),
                "free_claimed": ("free", tier) in state.claimed, "ticket_claimed": ("ticket", tier) in state.claimed,
            }
            for tier in range(1, season_data.TIERS + 1)
        ],
    )


async def path_claim(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    data = await body(request)
    if data.get("all"):
        done = await services.season.claim_all(p)
        return ok(claimed=len(done))
    track, tier = str(data.get("track", "")), int(data.get("tier", 0) or 0)
    if track not in ("free", "ticket"):
        raise GameError("این مسیر وجود ندارد.")
    reward = await services.season.claim(p, track, tier)
    return ok(claimed=1, reward=_reward(reward))


# --- a fight ---------------------------------------------------------------------------------------------------------------
async def _fight_state(services: Any, player_id: int) -> dict[str, Any] | None:
    fight = await services.solo.active(player_id)
    if fight is None:
        return None
    hero_, foe = fight.battle.fighters
    foe_id = fight.info.get("foe", "")
    warn = solo_data.FOES[foe_id].warn if foe_id in solo_data.FOES else ""

    def fighter(f: Any) -> dict[str, Any]:
        return {"name": f.name, "emoji": f.emoji, "hp": max(0, f.hp), "max_hp": f.max_hp, "shield": f.shield}

    return {
        "title": fight.info.get("title", "نبرد"), "kind": fight.kind, "round": fight.battle.round, "max_rounds": fight.battle.max_rounds,
        "hero": fighter(hero_), "foe": fighter(foe),
        "skill": {"name": hero_.skill_name, "emoji": hero_.skill_emoji, "wait": max(0, hero_.skill_ready_in - 1)},
        "warn": warn if warn and foe.skill_ready else "",
    }


async def fight(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    return ok(fight=await _fight_state(services, p.id))


async def fight_act(request: web.Request) -> web.Response:
    """One move of the hero (attack, skill, defend) or leaving the field; the panel's own screens do the work."""
    services = request.app[SERVICES]
    p = await hero(request)
    action = str((await body(request)).get("action", ""))
    if action == "flee":
        shown = await bridge.run(services, p, "sfleeok")
    elif action in ("attack", "skill", "defend"):
        shown = await bridge.run(services, p, "sact", action)
    else:
        raise GameError("این حرکت وجود ندارد.")
    fresh = await services.players.find(p.platform_user_id)
    return ok(shown=shown, fight=await _fight_state(services, p.id), player=player_json(services, services.players.with_energy(fresh)) if fresh else None)


# --- the treasury: every real-money product, grouped as the bot groups them -------------------------------------------------
#: the order and the names of the treasury's shelves in the app
SHELVES: tuple[tuple[str, str], ...] = (
    ("vip", "VIP"), ("coins", "سکه"), ("crystals", "کریستال"), ("bundles", "بسته‌ها"), ("rare", "منابع کمیاب"),
    ("boost", "بوست"), ("xp", "تجربه"), ("pets", "حیوان خانگی"), ("materials", "سنگ آهن"), ("services", "خدمات"), ("city", "فرمانروایی"),
)
#: what VIP gives (the same list the bot shows)
VIP_PERKS: tuple[tuple[str, str, str], ...] = (
    ("clock", "۲۰٪ انتظار کمتر", "ماجراجویی و شکار"),
    ("mission", "مأموریت چهارم", "هر روز یک مأموریت بیشتر"),
    ("path", "۱۰٪ امتیاز مسیر", "سریع‌تر در مسیر قهرمانی"),
    ("crown", "نشان VIP", "روی پروفایل شما"),
)


def _pack(pack: Any, price_rial: int | None = None) -> dict[str, Any]:
    from ..bot import views

    return {
        "id": pack.id, "emoji": pack.emoji, "title": pack.title, "section": pack.section,
        "toman": (price_rial if price_rial is not None else pack.price_rial) // 10, "full_toman": pack.price_toman,
        "gold": pack.gold, "crystal": pack.crystal, "xp": pack.xp, "spins": pack.spins, "vip_days": pack.vip_days,
        "boost_hours": pack.boost_hours, "pet": pack.pet, "season": pack.season, "lucky": pack.lucky,
        "items": [{"item": item_json(get_item(item_id)), "qty": qty} for item_id, qty in pack.items.items()],
        "about": views.pack_description(pack).removeprefix("شامل: ").replace("\n", " "),
    }


async def treasury(request: web.Request) -> web.Response:
    from ..game.data.deals import daily_deals, seconds_left

    services = request.app[SERVICES]
    p = await hero(request)
    now = services.ctx.now()
    shelves = []
    for key, name in SHELVES:
        packs = [_pack(pack) for pack in PACKS.values() if pack.section == key and not pack.lucky]
        if packs:
            shelves.append({"id": key, "name": name, "packs": packs})
    return ok(
        enabled=services.ctx.settings.payments_enabled, shelves=shelves,
        deals=[{**_pack(d.pack, d.price_rial), "percent": d.percent} for d in daily_deals(now)], deals_left=seconds_left(now),
        vip={"active": p.vip_until > now, "left": max(0, p.vip_until - now), "perks": [list(x) for x in VIP_PERKS]},
        boost_left=max(0, p.boost_until - now),
    )


# --- the daily gift: a week of rising rewards ---------------------------------------------------------------------------------------
async def daily(request: web.Request) -> web.Response:
    from ..game.services.players import DAY, streak_chest

    services = request.app[SERVICES]
    p = await hero(request)
    now, b = services.ctx.now(), services.ctx.balance
    ready = not p.daily_at or now - p.daily_at >= DAY
    alive = bool(p.daily_at) and now - p.daily_at < 2 * DAY
    done = p.daily_streak if alive else 0  # the streak the next claim builds on
    week_start = (done // 7) * 7 if not (ready and done % 7 == 0 and done) else done
    days = []
    for n in range(week_start + 1, week_start + 8):
        bonus = min(n, b.daily_streak_cap) - 1
        days.append({
            "day": n, "gold": b.daily_gold + b.daily_gold_per_level * p.level + 50 * bonus,
            "chest": item_json(get_item(streak_chest(n))) if streak_chest(n) else None, "crystal": 3 if n % 7 == 0 else 0,
            "state": "claimed" if n <= done else "today" if n == done + 1 and ready else "next" if n == done + 1 else "locked",
        })
    streak, savable = services.players.streak_status(p)
    return ok(ready=ready, streak=done, days=days, next_in=max(0, p.daily_at + DAY - now) if p.daily_at else 0,
              rescue={"streak": streak, "cost": services.players.RESCUE_COST} if savable else None)


async def daily_claim(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    reward = await services.players.claim_daily(p.id)
    return ok(gold=reward.gold, streak=reward.streak, crystal=reward.crystal,
              chest=item_json(get_item(reward.chest)) if reward.chest else None)


# --- the leaderboards ------------------------------------------------------------------------------------------------------
#: the boards the app shows, in order: id -> tab name
LEADER_BOARDS: tuple[tuple[str, str], ...] = (
    ("level", "سطح"), ("rich", "ثروت"), ("wins", "دوئل"), ("rating", "لیگ"), ("path", "مسیر"), ("bosses", "باس‌کش‌ها"),
    ("clans", "خاندان‌ها"),
)


def _who(badge: str) -> tuple[str, str]:
    """The race and class ids behind a board's badge (the badge is their two emojis)."""
    from ..game.data.classes import CLASSES
    from ..game.data.races import RACES

    race = next((r for r in RACES.values() if badge.startswith(r.emoji)), None)
    rest = badge.removeprefix(race.emoji) if race else badge
    klass = next((k for k in CLASSES.values() if rest.startswith(k.emoji)), None)
    return (race.id if race else "", klass.id if klass else "")


async def leaders(request: web.Request) -> web.Response:
    from ..game.services.rankings import BOARDS, BRACKETS

    services = request.app[SERVICES]
    p = await hero(request)
    board_id = request.query.get("board", "level")
    bracket = request.query.get("bracket", "all")
    ranking = services.rankings
    boards = [{"id": i, "name": n} for i, n in LEADER_BOARDS]
    if board_id == "clans":  # the clans, strongest first (the same list as the bot's «برترین خاندان‌ها»)
        clans, _ = await services.clans.listing(0, 10)
        mine = await services.clans.of(p.id)
        entries = [
            {"rank": i, "name": v.name, "race": "", "class": "", "value": v.power, "level": v.level, "size": v.size,
             "leader": v.leader, "me": bool(mine and mine.id == v.id)}
            for i, v in enumerate(clans, 1)
        ]
        position = next((e["rank"] for e in entries if e["me"]), None)
        return ok(board="clans", title="برترین خاندان‌ها", unit="قدرت", entries=entries, my_position=position,
                  boards=boards, brackets=[], bracket="", clans=True)
    if board_id == "path":
        board = await ranking.path_board(p)
    elif board_id == "bosses":
        board = await ranking.boss_hunters(p)
    elif board_id in BOARDS:
        board = await ranking.global_board(board_id, p, bracket=bracket)
    else:
        raise GameError("این جدول وجود ندارد.")
    entries = []
    for rank, e in enumerate(board.entries, 1):
        race, klass = _who(e.badge)
        entries.append({"rank": rank, "name": e.name, "race": race, "class": klass, "value": e.value, "level": e.level, "me": e.uid == p.platform_user_id})
    return ok(
        board=board_id, title=board.title, unit=board.unit, entries=entries, my_position=board.my_position,
        boards=boards,
        brackets=[{"id": k, "name": v[0]} for k, v in BRACKETS.items()] if board_id in BOARDS else [],
        bracket=bracket if board_id in BOARDS else "",
    )


# --- the exchange: gold and crystals for each other ---------------------------------------------------------------------------
async def exchange(request: web.Request) -> web.Response:
    from ..game.services.exchange import MAX_TRADE

    services = request.app[SERVICES]
    p = await hero(request)
    ex = services.exchange
    return ok(rate=ex.rate, fee_percent=ex.fee_percent, max=MAX_TRADE, left_today=await ex.left_today(p.id), gold=p.gold, crystal=p.crystal)


async def exchange_trade(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    data = await body(request)
    side, amount = str(data.get("side", "")), int(data.get("amount", 0) or 0)
    if side == "buy":
        quote = await services.exchange.buy(p, amount)
    elif side == "sell":
        quote = await services.exchange.sell(p, amount)
    else:
        raise GameError("این مبادله وجود ندارد.")
    return ok(crystals=quote.crystals, gold=quote.gold, fee=quote.fee)


# --- the forge: every recipe with what it needs and what the hero has --------------------------------------------------------
def _stat_lines(item: Any) -> list[str]:
    return item.stats.bonus_lines()


async def forge(request: web.Request) -> web.Response:
    from ..game.data.recipes import RECIPES

    services = request.app[SERVICES]
    p = await hero(request)
    recipes = []
    for r in RECIPES:
        v = await services.crafting.view(p, r.id)
        needs = []
        if v.base is not None:
            needs.append({"item": item_json(v.base.item), "have": v.base.have, "need": 1, "base": True})
        needs += [{"item": item_json(n.item), "have": n.have, "need": n.need, "base": False} for n in v.materials]
        recipes.append({
            "id": r.id, "result": item_json(v.result), "stats": _stat_lines(v.result), "needs": needs,
            "gold": r.gold, "gold_have": v.gold_have, "owned": v.already_owned, "ready": v.ready,
        })
    return ok(recipes=recipes)


async def forge_make(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    made = await services.crafting.craft(p, str((await body(request)).get("id", "")))
    return ok(item=item_json(made), stats=_stat_lines(made))


# --- chests: the ones the hero owns, the ones for sale, and opening one --------------------------------------------------------
async def chests(request: web.Request) -> web.Response:
    from ..game.data.chests import CHESTS
    from ..game.data.items import Kind

    services = request.app[SERVICES]
    p = await hero(request)
    view = await services.inventory.view(p.id)
    owned = {i.id: q for i, q in view.stacks if i.kind is Kind.CHEST}
    return ok(
        gold=p.gold, crystal=p.crystal,
        chests=[
            {"item": item_json(get_item(cid)), "owned": owned.get(cid, 0),
             "price": {"currency": c.price[0], "amount": c.price[1]} if c.price else None}
            for cid, c in CHESTS.items() if c.price or owned.get(cid)
        ],
    )


async def chests_act(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    data = await body(request)
    if data.get("buy"):
        currency, total = await services.chests.buy(p, str(data["buy"]), 1)
        return ok(bought=str(data["buy"]), currency=currency, total=total)
    opened = await services.chests.open(p, get_item(str(data.get("open", ""))))
    return ok(
        gold=opened.gold, crystal=opened.crystal, qty=opened.qty,
        item=item_json(opened.item) if opened.item else None, chest=item_json(opened.chest),
    )


# --- today's missions and the week's prize --------------------------------------------------------------------------------------
async def missions(request: web.Request) -> web.Response:
    from ..game.services.missions import WEEK_PRIZES

    services = request.app[SERVICES]
    p = await hero(request)
    todays = await services.missions.today(p)
    week = await services.missions.week(p)
    return ok(
        missions=[{"slot": m.slot, "emoji": m.emoji, "title": m.title, "progress": m.progress, "target": m.target,
                   "gold": m.gold, "claimed": m.claimed, "done": m.done, "special": m.kind_id == "welcome"} for m in todays],
        week={"days": week.days, "claimed": week.claimed, "earned": week.earned[0] if week.earned else 0, "left": week.seconds_left,
              "prizes": [{"days": d, "crystal": c, "chest": item_json(get_item(chest))} for d, c, chest in sorted(WEEK_PRIZES)]},
    )


def register(app: web.Application) -> None:
    app.router.add_get("/api/missions", missions)
    app.router.add_get("/api/forge", forge)
    app.router.add_post("/api/forge", forge_make)
    app.router.add_get("/api/chests", chests)
    app.router.add_post("/api/chests", chests_act)
    app.router.add_get("/api/leaders", leaders)
    app.router.add_get("/api/exchange", exchange)
    app.router.add_post("/api/exchange", exchange_trade)
    app.router.add_get("/api/treasury", treasury)
    app.router.add_get("/api/daily", daily)
    app.router.add_post("/api/daily", daily_claim)
    app.router.add_get("/api/wheel", wheel)
    app.router.add_post("/api/wheel", wheel_spin)
    app.router.add_get("/api/path", path)
    app.router.add_post("/api/path", path_claim)
    app.router.add_get("/api/fight", fight)
    app.router.add_post("/api/fight", fight_act)
