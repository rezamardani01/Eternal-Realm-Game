"""The HTTP side of the mini app: a small JSON API over the same services the bot uses, and the built page itself.

Nothing here decides anything about the game: every request is turned into a call of an existing service or panel
screen, under the caller's own hero, and the answer is described as JSON. It runs inside the bot's process, so both
share one database connection, one set of services and one set of locks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from ..bot import views
from ..bot.services import Services
from ..game.data.activities import ACTIVITIES
from ..game.data.classes import CLASSES
from ..game.data.items import RARITIES, SLOT_LABELS, Item
from ..game.data.races import RACES
from ..game.models import Player
from ..shared.errors import AwayError, GameError
from . import bridge
from .auth import AuthError, WebUser, validate

log = logging.getLogger("eternal_realm.web")

DIST = Path(__file__).resolve().parents[2] / "miniapp" / "dist"
SERVICES = web.AppKey("services", Services)
BOT = web.AppKey("bot", object)
#: requests one user may make in a short window (a tap is one request; this only stops scripts)
RATE_WINDOW, RATE_MAX = 10.0, 40
GENERIC_ERROR = "طوفانی در قلمرو وزید و کار نیمه‌کاره ماند؛ چند لحظه‌ی دیگر دوباره امتحان کنید."


# --- small helpers ---------------------------------------------------------------------------------------------------
def ok(**data: Any) -> web.Response:
    return web.json_response({"ok": True, **data})


def fail(message: str, status: int = 200, **extra: Any) -> web.Response:
    return web.json_response({"ok": False, "error": message, **extra}, status=status)


def item_json(item: Item) -> dict[str, Any]:
    return {
        "id": item.id, "name": item.name, "emoji": item.emoji, "kind": item.kind.value, "rarity": item.rarity,
        "rarity_name": RARITIES[item.rarity][1],
    }


def player_json(services: Services, p: Player) -> dict[str, Any]:
    now = services.ctx.now()
    return {
        "id": p.id, "name": p.name, "level": p.level, "xp": p.xp, "xp_needed": services.characters.xp_needed(p),
        "energy": p.energy, "max_energy": services.characters.max_energy(p), "gold": p.gold, "crystal": p.crystal,
        "race": {"id": p.race_id, "name": p.race.name, "emoji": p.race.emoji},
        "class": {"id": p.class_id, "name": p.char_class.name, "emoji": p.char_class.emoji},
        "class2": {"id": p.class2_id, "name": p.class2.name, "emoji": p.class2.emoji} if p.class2 else None,
        "awakened": p.awakened, "honor": p.honor, "vip": p.vip_until > now, "boost_left": max(0, p.boost_until - now),
        "wins": p.wins, "losses": p.losses, "streak": p.daily_streak, "khan_points": p.khan_points,
        "daily_in": max(0, p.daily_at + 86400 - now) if p.daily_at else 0,
    }


# --- who is asking -------------------------------------------------------------------------------------------------------
class Session:
    """Per-process guards: one request at a time per user, and a ceiling on how fast one user may ask."""

    def __init__(self) -> None:
        self.locks: dict[int, asyncio.Lock] = {}
        self.hits: dict[int, list[float]] = {}

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        hits = [t for t in self.hits.get(user_id, []) if now - t < RATE_WINDOW]
        hits.append(now)
        self.hits[user_id] = hits
        if len(self.hits) > 20_000:
            self.hits.clear()
        return len(hits) <= RATE_MAX

    def lock(self, user_id: int) -> asyncio.Lock:
        if len(self.locks) > 20_000:
            self.locks = {uid: lock for uid, lock in self.locks.items() if lock.locked()}
        return self.locks.setdefault(user_id, asyncio.Lock())


SESSION = web.AppKey("session", Session)


def identify(request: web.Request) -> WebUser:
    services = request.app[SERVICES]
    settings = services.ctx.settings
    dev_user = request.headers.get("X-Dev-User", "")
    if dev_user and settings.miniapp_dev:  # the local preview only; never switched on in production
        return WebUser(int(dev_user), "preview", "پیش‌نمایش")
    return validate(request.headers.get("X-Init-Data", ""), settings.token, int(time.time()))


@web.middleware
async def guard(request: web.Request, handler: Any) -> web.StreamResponse:
    """Authenticate every API call, serialise the calls of one user and turn game errors into friendly answers."""
    if not request.path.startswith("/api/"):
        return await handler(request)
    try:
        user = identify(request)
    except (AuthError, ValueError):
        return fail("ورود شما تأیید نشد؛ مینی‌اپ را از داخل بله دوباره باز کنید.", status=401)
    session = request.app[SESSION]
    if not session.allow(user.id):
        return fail("کمی آرام‌تر، فرمانده! چند ثانیه صبر کنید.", status=429)
    request["user"] = user
    async with session.lock(user.id):
        try:
            return await handler(request)
        except AwayError as error:
            return fail(error.message, away=True)
        except GameError as error:
            return fail(error.message)
        except web.HTTPException:
            raise
        except Exception:
            log.exception("mini app request failed: %s", request.path)
            return fail(GENERIC_ERROR)


async def hero(request: web.Request) -> Player:
    """The caller's hero; a caller without one is sent to the creation screen by the page."""
    user: WebUser = request["user"]
    services = request.app[SERVICES]
    player = await services.players.find(user.id, user.username)
    if player is None:
        raise web.HTTPConflict(text='{"ok": false, "error": "no_hero", "needs_hero": true}', content_type="application/json")
    if player.banned:
        raise GameError("نگهبانان قلمرو درهای شهر را به روی شما بسته‌اند.")
    return player


async def body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


# --- reading ---------------------------------------------------------------------------------------------------------------
async def me(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    stats = await services.characters.stats(p)
    missions = await services.missions.today(p)
    week = await services.missions.week(p)
    fight = await services.solo.active(p.id)
    run = await services.solo.maze_run(p.id)
    popup = await services.popups.latest(p)
    streak, savable = services.players.streak_status(p)
    return ok(
        player=player_json(services, p),
        stats={"hp": stats.hp, "atk": stats.atk, "defense": stats.defense, "magic": stats.magic, "speed": stats.speed, "luck": stats.luck},
        power=stats.hp // 4 + stats.atk + stats.defense + stats.magic + stats.speed + stats.luck,
        badges=await services.social.titles(p.id, 6),
        missions=[
            {"slot": m.slot, "emoji": m.emoji, "title": m.title, "progress": m.progress, "target": m.target, "gold": m.gold,
             "claimed": m.claimed, "done": m.done} for m in missions
        ],
        week={"days": week.days, "claimed": week.claimed, "ready": week.earned is not None and not week.claimed},
        ready={
            "daily": not p.daily_at or services.ctx.now() - p.daily_at >= 86400,
            "fight": fight.info.get("title", "") if fight else "",
            "maze_floor": run.floor if run else 0,
            "gifts": await services.clan_gifts.waiting(p.id),
            "popup": {"id": popup.id, "title": popup.popup.title, "emoji": popup.popup.emoji} if popup else None,
            "rescue": streak if savable else 0,
        },
        is_admin=services.ctx.settings.is_admin(p.platform_user_id),
        payments=services.ctx.settings.payments_enabled,
    )


async def hero_page(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    view = await services.inventory.view(p.id)

    def piece(g: Any) -> dict[str, Any]:
        return {
            "id": g.id, "item": item_json(g.item), "upgrade": g.upgrade, "slot": g.slot,
            "stats": g.stats.bonus_lines(),
        }

    worn = {g.slot: piece(g) for g in view.gear if g.slot}
    return ok(
        slots=[{"id": slot, "label": label, "piece": worn.get(slot)} for slot, label in SLOT_LABELS.items()],
        bag=[piece(g) for g in view.gear if not g.slot][:60],
        stacks=[{"item": item_json(i), "qty": q} for i, q in view.stacks][:80],
    )


async def adventure(request: web.Request) -> web.Response:
    from ..db.repos import inventory as inv_repo
    from ..game.services.hunting import HUNT_ENERGY

    services = request.app[SERVICES]
    p = await hero(request)
    now = services.ctx.now()
    async with services.ctx.db.read() as tx:
        waits = {key: max(0, await inv_repo.cooldown_until(tx, p.id, key) - now) for key in (*ACTIVITIES, "hunt")}
    cards = [{"id": "hunt", "title": "شکار هیولا", "emoji": "🐺", "energy": HUNT_ENERGY, "wait": waits["hunt"], "danger": True}]
    cards += [{"id": a.id, "title": a.title, "emoji": a.emoji, "energy": a.energy, "wait": waits[a.id]} for a in ACTIVITIES.values()]
    return ok(activities=cards, energy=p.energy, max_energy=services.characters.max_energy(p))


async def act(request: web.Request) -> web.Response:
    """One calm activity or a hunt: the same service call as the bot, described for a result card."""
    services = request.app[SERVICES]
    p = await hero(request)
    kind = str((await body(request)).get("id", ""))

    def loot(items: list[tuple[str, int, str]]) -> list[dict[str, Any]]:
        from ..game.data.items import get_item

        return [{"item": item_json(get_item(item_id)), "qty": qty} for _, qty, item_id in items]

    if kind == "hunt":
        r = await services.hunting.hunt(p.id, None)
        return ok(result={
            "kind": "hunt", "title": f"شکار {r.monster.name}", "emoji": r.monster.emoji, "won": r.won, "rounds": r.rounds,
            "text": "پیروز شدید" if r.won else "هیولا قوی‌تر بود؛ عقب‌نشینی کردید",
            "gold": r.gold, "xp": r.xp, "crystal": 0, "items": loot(r.items), "hp": [r.hero_hp, r.hero_max_hp],
            "energy": r.player.energy, "next_in": r.next_in, "level_up": r.level_up.new_level if r.level_up else 0,
            "card": {"name": r.card.name, "emoji": r.card.emoji} if r.card is not None else None, "log": r.log[-6:],
        })
    if kind not in ACTIVITIES:
        raise GameError("این فعالیت وجود ندارد.")
    done = await services.activities.perform(p.id, kind, None)
    return ok(result={
        "kind": "activity", "title": done.activity.title, "emoji": done.activity.emoji, "won": True,
        "text": done.rolled.outcome.text.format(name=p.name),
        "gold": done.rolled.gold, "xp": done.rolled.xp, "crystal": done.rolled.crystal, "items": loot(done.items),
        "energy": done.player.energy, "next_in": done.next_in, "level_up": done.level_up.new_level if done.level_up else 0,
    })


async def clan(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    mine = await services.clans.of(p.id)
    if mine is None:
        return ok(clan=None, create_gold=services.ctx.balance.clan_create_gold)
    people = await services.clans.members(mine.id)
    return ok(
        clan={
            "id": mine.id, "name": mine.name, "leader": mine.leader, "level": mine.level, "size": mine.size,
            "capacity": mine.capacity, "power": mine.power, "treasury": mine.treasury, "open": mine.open,
            "role": mine.my_role or "member", "min_level": mine.min_level, "exit_fine": mine.exit_fine,
        },
        members=[
            {"id": m["player_id"], "name": m["name"], "level": m["level"], "role": m["role"], "donated": m["donated"]}
            for m in people[:50]
        ],
        khan_points=await services.clans.khan_points(p.id),
    )


async def market(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    sort = request.query.get("sort", "new")
    page = max(0, int(request.query.get("page", "0") or 0))
    found, more = await services.market.page(None, sort if sort in ("new", "cheap", "expensive", "rare") else "new", page, 12)
    return ok(
        listings=[
            {"id": lst.id, "item": item_json(lst.item), "qty": lst.qty, "price": lst.price, "upgrade": lst.upgrade,
             "seller": lst.seller_name, "mine": lst.seller_id == p.id} for lst in found
        ],
        more=more, page=page, gold=p.gold,
    )


# --- the panel bridge ----------------------------------------------------------------------------------------------------------
async def screen(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    p = await hero(request)
    data = await body(request)
    name = str(data.get("s", ""))[:24]
    if name.startswith("adm") and not services.ctx.settings.is_admin(p.platform_user_id):
        return fail("این بخش فقط برای مدیران قلمرو است.")
    try:
        shown = await bridge.run(services, p, name, str(data.get("a", ""))[:64], str(data.get("b", ""))[:64])
    except KeyError:
        return fail("این بخش در مینی‌اپ در دسترس نیست؛ از داخل ربات انجامش دهید.")
    fresh = await services.players.find(p.platform_user_id)
    return ok(shown=shown, player=player_json(services, services.players.with_energy(fresh)) if fresh else None)


async def prompt(request: web.Request) -> web.Response:
    """A value the bot would have asked for as a typed message (the name of a new city)."""
    services = request.app[SERVICES]
    p = await hero(request)
    data = await body(request)
    if data.get("kind") != "city_name":
        return fail("این فرم شناخته نشد.")
    from ..bot import city_panel
    from ..bot import keyboards as kb
    from ..game.data import city as city_data

    name = city_panel.clean_city_name(str(data.get("text", "")))
    city_panel._names[p.platform_user_id] = name
    flags = kb.grid(
        [kb.panel_button(f"{emoji} {label}", "cityflag", p.platform_user_id, str(i)) for i, (emoji, label) in enumerate(city_data.FLAGS)], 3
    )
    flags.append([kb.panel_button("❌ انصراف", "city", p.platform_user_id)])
    shown = {
        "screen": "cityflag", "a": "", "b": "", "toast": None, "alert": False,
        "text": f"🚩 *پرچم شهر*\n\nشهر *{name}*\n\nنشان و پرچم شهرتان را برگزینید 👇",
        "rows": [[bridge._button(btn) for btn in row] for row in flags],
    }
    return ok(shown=shown)


# --- creating a hero -----------------------------------------------------------------------------------------------------------
async def onboarding(request: web.Request) -> web.Response:
    return ok(
        races=[{"id": r.id, "name": r.name, "emoji": r.emoji, "about": r.description} for r in RACES.values()],
        classes=[{"id": c.id, "name": c.name, "emoji": c.emoji, "about": c.description} for c in CLASSES.values()],
    )


async def register(request: web.Request) -> web.Response:
    services = request.app[SERVICES]
    user: WebUser = request["user"]
    data = await body(request)
    if await services.players.find(user.id, user.username) is not None:
        return fail("شما از قبل قهرمان دارید.")
    name = await services.players.name_available(str(data.get("name", "")))
    player = await services.players.register(user.id, user.username, name, str(data.get("race", "")), str(data.get("class", "")))
    await services.players.grant_welcome_boost(player.id)
    return ok(player=player_json(services, player))


# --- paying ----------------------------------------------------------------------------------------------------------------------
async def buy(request: web.Request) -> web.Response:
    """Book an order and hand the page what it needs to open Bale's own payment sheet.

    Nothing is delivered here: the goods arrive only when Bale tells the bot the payment succeeded, through the same
    pre-checkout and delivery code the chat uses.
    """
    from baleropy.types import LabeledPrice

    services = request.app[SERVICES]
    bot = request.app[BOT]
    p = await hero(request)
    data = await body(request)
    settings = services.ctx.settings
    if not settings.payments_enabled:
        return fail("خرید با پول واقعی فعلاً بسته است.")
    if bot is None:
        return fail("در پیش‌نمایش محلی درگاه پرداخت وصل نیست؛ داخل بله پرداخت باز می‌شود.")
    order = await services.payments.create_order(p, str(data.get("id", "")), deal=data.get("kind") == "deal")
    pack = order.pack
    description = (
        views.pack_description(pack, services.ctx.now())
        + (f" · {views.discount_note(pack, order.amount)}" if order.amount < pack.price_rial else "")
    )[:255]
    prices = [LabeledPrice(label=pack.title[:32], amount=order.amount)]
    if data.get("via") == "chat":  # an old client without openInvoice: the invoice goes to the chat with the bot
        await bot.send_invoice(  # type: ignore[attr-defined]
            chat_id=p.platform_user_id, title=pack.title[:32], description=description, payload=order.payload,
            provider_token=settings.provider_token, prices=prices,
        )
        return ok(sent_to_chat=True)
    link = await bot.create_invoice_link(  # type: ignore[attr-defined]
        title=pack.title[:32], description=description, payload=order.payload, provider_token=settings.provider_token, prices=prices,
    )
    return ok(invoice=link, title=pack.title, amount=order.amount)


# --- the page itself ---------------------------------------------------------------------------------------------------------------
@web.middleware
async def page_headers(request: web.Request, handler: Any) -> web.StreamResponse:
    response = await handler(request)
    # Bale's web client shows the mini app in a frame of its own pages
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' https://*.bale.ai https://*.ble.ir"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.path.startswith("/assets/") or request.path.startswith("/icons/"):
        response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
    return response


async def index(request: web.Request) -> web.StreamResponse:
    page = DIST / "index.html"
    if not page.exists():
        return web.Response(text="mini app is not built yet: run `npm run build` in miniapp/", status=503)
    return web.FileResponse(page, headers={"Cache-Control": "no-cache"})


def create_app(services: Services, bot: object | None = None) -> web.Application:
    app = web.Application(middlewares=[page_headers, guard], client_max_size=64 * 1024)
    app[SERVICES], app[BOT], app[SESSION] = services, bot, Session()
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/hero", hero_page)
    app.router.add_get("/api/adventure", adventure)
    app.router.add_post("/api/act", act)
    app.router.add_get("/api/clan", clan)
    app.router.add_get("/api/market", market)
    app.router.add_post("/api/screen", screen)
    app.router.add_post("/api/prompt", prompt)
    app.router.add_get("/api/onboarding", onboarding)
    app.router.add_post("/api/register", register)
    app.router.add_post("/api/buy", buy)
    from . import scenes

    scenes.register(app)
    app.router.add_get("/", index)
    if DIST.exists():
        for folder in ("assets", "icons", "art"):
            if (DIST / folder).exists():
                app.router.add_static(f"/{folder}/", DIST / folder)
    return app


async def start(services: Services, bot: object | None = None) -> web.AppRunner:
    settings = services.ctx.settings
    runner = web.AppRunner(create_app(services, bot), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, settings.miniapp_host, settings.miniapp_port).start()
    log.info("mini app API is listening on %s:%s", settings.miniapp_host, settings.miniapp_port)
    return runner
