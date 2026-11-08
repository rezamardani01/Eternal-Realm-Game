"""The web admin panel: a small aiohttp app living inside the bot process.

Sign-in is only possible with a one-time link the bot sends to an administrator. After that a short
session cookie (HttpOnly, SameSite=Strict) and a CSRF header protect every change.
"""

from __future__ import annotations

import asyncio
import hmac
import html
import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from ..bot.services import Services
from ..game.data.items import ITEMS, find_item
from ..shared.errors import GameError
from ..shared.jalali import describe
from .auth import SESSION_TTL, Session, WebAuth

log = logging.getLogger("eternal_realm.web")
STATIC = Path(__file__).parent / "static"
COOKIE = "er_sid"
SESSION_KEY = web.RequestKey("session", Session)
PAGE = 25

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def fmt(ts: int | None) -> str:
    if not ts:
        return "—"
    date, _, clock = describe(int(ts))
    return f"{date} {clock}"


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


class AdminWeb:
    def __init__(self, services: Services, auth: WebAuth, bot: Any = None, secure_cookie: bool = False) -> None:
        self.s = services
        self.auth = auth
        self.bot = bot
        self.secure_cookie = secure_cookie

    # --- middleware ----------------------------------------------------------------------------------
    @web.middleware
    async def guard(self, request: web.Request, handler):  # noqa: ANN001, ANN202
        path = request.path
        if path.startswith("/api/"):
            session = self.auth.session(request.cookies.get(COOKIE))
            if session is None:
                return _json({"error": "نشست شما تمام شده است. از ربات لینک تازه بگیرید."}, 401)
            request[SESSION_KEY] = session
            if request.method not in ("GET", "HEAD"):
                sent = request.headers.get("X-CSRF-Token", "")
                if not hmac.compare_digest(sent, session.csrf):
                    return _json({"error": "درخواست نامعتبر است (CSRF)."}, 403)
        try:
            response = await handler(request)
        except web.HTTPException:
            raise
        except GameError as error:
            return _json({"error": error.message}, 400)
        except Exception:
            log.exception("web panel error on %s", path)
            return _json({"error": "خطای داخلی سرور."}, 500)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    # --- pages ----------------------------------------------------------------------------------------
    async def index(self, request: web.Request) -> web.StreamResponse:
        if self.auth.session(request.cookies.get(COOKIE)) is None:
            return web.Response(text=_login_page("برای ورود، در ربات «پنل وب» را بفرستید و روی لینک یک‌بارمصرف بزنید."),
                                content_type="text/html")
        return web.FileResponse(STATIC / "index.html")

    async def login_page(self, request: web.Request) -> web.Response:
        token = request.query.get("token", "")
        if not self.auth.peek(token):
            return web.Response(text=_login_page("این لینک منقضی یا استفاده‌شده است. از ربات لینک تازه بگیرید."),
                                content_type="text/html", status=403)
        # a confirmation click is required so that link-preview robots cannot use the link up
        body = (
            f'<form method="post" action="/login"><input type="hidden" name="token" value="{html.escape(token)}">'
            '<button type="submit">ورود به پنل مدیریت</button></form>'
        )
        return web.Response(text=_login_page("لینک معتبر است. برای ورود دکمه را بزنید.", body), content_type="text/html")

    async def login(self, request: web.Request) -> web.Response:
        form = await request.post()
        token = str(form.get("token", ""))
        address = request.remote or "?"
        sid = self.auth.redeem(token, address)
        if sid is None:
            return web.Response(text=_login_page("ورود ناموفق بود. لینک تازه بگیرید."), content_type="text/html", status=403)
        response = web.HTTPFound("/")
        response.set_cookie(COOKIE, sid, max_age=SESSION_TTL, httponly=True, samesite="Strict", secure=self.secure_cookie, path="/")
        raise response

    async def logout(self, request: web.Request) -> web.Response:
        self.auth.end(request.cookies.get(COOKIE))
        response = _json({"ok": True})
        response.del_cookie(COOKIE, path="/")
        return response

    # --- api: overview ---------------------------------------------------------------------------------
    async def me(self, request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        return _json({"admin_id": session.admin_id, "csrf": session.csrf, "bot": self.s.bot_username})

    async def stats(self, request: web.Request) -> web.Response:
        now = self.s.ctx.now()
        day = (now + 12600) // 86400
        async with self.s.ctx.db.read() as tx:
            one = tx.scalar
            data = {
                "players": await one("SELECT COUNT(*) FROM players", (), 0),
                "new_today": await one("SELECT COUNT(*) FROM players WHERE (created_at + 12600) / 86400 = ?", (day,), 0),
                "active_24h": await one(
                    "SELECT COUNT(DISTINCT player_id) FROM transactions WHERE created_at >= ?", (now - 86400,), 0),
                "banned": await one("SELECT COUNT(*) FROM players WHERE banned = 1", (), 0),
                "vip": await one("SELECT COUNT(*) FROM players WHERE vip_until > ?", (now,), 0),
                "groups": await one("SELECT COUNT(*) FROM groups", (), 0),
                "clans": await one("SELECT COUNT(*) FROM clans", (), 0),
                "orders": await one("SELECT COUNT(*) FROM orders WHERE status = 'delivered'", (), 0),
                "revenue_toman": (await one("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status = 'delivered'", (), 0)) // 10,
                "gold": await one("SELECT COALESCE(SUM(gold), 0) FROM players", (), 0),
                "crystal": await one("SELECT COALESCE(SUM(crystal), 0) FROM players", (), 0),
                "duels": await one("SELECT COUNT(*) FROM duels WHERE status = 'active'", (), 0),
                "bosses": await one("SELECT COUNT(*) FROM bosses WHERE status = 'active'", (), 0),
            }
            since = (day - 13) * 86400 - 12600
            new_rows = await tx.fetchall(
                "SELECT (created_at + 12600) / 86400 AS d, COUNT(*) AS n FROM players WHERE created_at >= ? GROUP BY d", (since,))
            rev_rows = await tx.fetchall(
                "SELECT (delivered_at + 12600) / 86400 AS d, SUM(amount) AS n FROM orders"
                " WHERE status = 'delivered' AND delivered_at >= ? GROUP BY d", (since,))
            act_rows = await tx.fetchall(
                "SELECT (created_at + 12600) / 86400 AS d, COUNT(DISTINCT player_id) AS n FROM transactions"
                " WHERE created_at >= ? GROUP BY d", (since,))

        def series(rows, scale: int = 1) -> list[dict[str, Any]]:
            by_day = {r["d"]: r["n"] // scale for r in rows}
            out = []
            for d in range(day - 13, day + 1):
                label = describe(d * 86400 - 12600 + 43200)[0][5:]
                out.append({"day": label, "value": int(by_day.get(d, 0))})
            return out

        data["series"] = {"new": series(new_rows), "revenue": series(rev_rows, 10), "active": series(act_rows)}
        return _json(data)

    # --- api: players -------------------------------------------------------------------------------------
    async def players(self, request: web.Request) -> web.Response:
        q = request.query.get("q", "").strip()[:40]
        page = max(0, int(request.query.get("page", "0") or 0))
        where, args = "1 = 1", []
        if q:
            where = "(display_name LIKE ? ESCAPE '\\' OR CAST(platform_user_id AS TEXT) = ? OR username LIKE ? ESCAPE '\\')"
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args = [like, q, like]
        now = self.s.ctx.now()
        async with self.s.ctx.db.read() as tx:
            total = await tx.scalar(f"SELECT COUNT(*) FROM players WHERE {where}", tuple(args), 0)  # noqa: S608
            rows = await tx.fetchall(
                f"SELECT * FROM players WHERE {where} ORDER BY level DESC, id LIMIT ? OFFSET ?",  # noqa: S608
                (*args, PAGE, page * PAGE),
            )
        return _json({
            "total": total, "page": page, "per": PAGE,
            "rows": [_player_row(r, now) for r in rows],
        })

    async def player(self, request: web.Request) -> web.Response:
        pid = int(request.match_info["id"])
        now = self.s.ctx.now()
        async with self.s.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM players WHERE id = ?", (pid,))
            if row is None:
                raise GameError("بازیکن پیدا نشد.")
            stacks = await tx.fetchall("SELECT item_id, qty FROM inventory WHERE player_id = ? AND qty > 0", (pid,))
            gear = await tx.fetchall("SELECT item_id, upgrade, slot FROM gear WHERE player_id = ?", (pid,))
            clan = await tx.fetchone(
                "SELECT c.name, m.role FROM clan_members m JOIN clans c ON c.id = m.clan_id WHERE m.player_id = ?", (pid,))
            pets = await tx.fetchall("SELECT pet_id, level, active FROM player_pets WHERE player_id = ?", (pid,))
            cards = await tx.scalar("SELECT COALESCE(SUM(qty), 0) FROM player_cards WHERE player_id = ?", (pid,), 0)
            history = await tx.fetchall(
                "SELECT gold_delta, crystal_delta, reason, created_at FROM transactions WHERE player_id = ?"
                " ORDER BY id DESC LIMIT 20", (pid,))
        def label(item_id: str) -> str:
            item = ITEMS.get(item_id)
            return f"{item.emoji} {item.name}" if item else item_id

        detail = _player_row(row, now)
        detail.update({
            "xp": row["xp"], "energy": row["energy"], "race": row["race"], "class2": row["class2"],
            "awakened": bool(row["awakened"]), "title": row["title"], "cards": cards,
            "clan": {"name": clan["name"], "role": clan["role"]} if clan else None,
            "pets": [{"id": p["pet_id"], "level": p["level"], "active": bool(p["active"])} for p in pets],
            "items": [{"label": label(s["item_id"]), "qty": s["qty"]} for s in stacks],
            "gear": [{"label": label(g["item_id"]), "upgrade": g["upgrade"], "worn": bool(g["slot"])} for g in gear],
            "history": [{"gold": h["gold_delta"], "crystal": h["crystal_delta"], "reason": h["reason"], "at": fmt(h["created_at"])}
                        for h in history],
        })
        return _json(detail)

    async def _player_name(self, pid: int) -> str:
        async with self.s.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT display_name FROM players WHERE id = ?", (pid,))
        if row is None:
            raise GameError("بازیکن پیدا نشد.")
        return row["display_name"]

    async def _body(self, request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except Exception as exc:
            raise GameError("بدنه‌ی درخواست درست نیست.") from exc
        if not isinstance(data, dict):
            raise GameError("بدنه‌ی درخواست درست نیست.")
        return data

    @staticmethod
    def _int(data: dict[str, Any], key: str, low: int, high: int) -> int:
        value = data.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int | float) or value != int(value):
            raise GameError("مقدار عددی درست نیست.")
        value = int(value)
        if not low <= value <= high:
            raise GameError(f"مقدار باید بین {low} تا {high} باشد.")
        return value

    async def give(self, request: web.Request) -> web.Response:
        pid, data = int(request.match_info["id"]), await self._body(request)
        gold, crystal = self._int(data, "gold", -10_000_000, 10_000_000), self._int(data, "crystal", -100_000, 100_000)
        if not gold and not crystal:
            raise GameError("حداقل یکی از سکه یا کریستال را پر کنید.")
        await self.s.admin.give_currency(request[SESSION_KEY].admin_id, await self._player_name(pid), gold=gold, crystal=crystal)
        return _json({"ok": True})

    async def set_level(self, request: web.Request) -> web.Response:
        pid, data = int(request.match_info["id"]), await self._body(request)
        level = self._int(data, "level", 1, self.s.ctx.balance.max_level)
        await self.s.admin.set_level(request[SESSION_KEY].admin_id, await self._player_name(pid), level)
        return _json({"ok": True})

    async def ban(self, request: web.Request) -> web.Response:
        pid, data = int(request.match_info["id"]), await self._body(request)
        await self.s.admin.set_ban(request[SESSION_KEY].admin_id, await self._player_name(pid), bool(data.get("banned")))
        return _json({"ok": True})

    async def give_item(self, request: web.Request) -> web.Response:
        pid, data = int(request.match_info["id"]), await self._body(request)
        item = ITEMS.get(str(data.get("item", "")))
        if item is None:
            raise GameError("آیتم پیدا نشد.")
        qty = self._int(data, "qty", 1, 1000)
        await self.s.admin.give_item(request[SESSION_KEY].admin_id, await self._player_name(pid), item, qty)
        return _json({"ok": True})

    async def items(self, request: web.Request) -> web.Response:
        return _json([{"id": i.id, "label": f"{i.emoji} {i.name}"} for i in ITEMS.values()])

    # --- api: lists -----------------------------------------------------------------------------------------
    async def groups(self, request: web.Request) -> web.Response:
        async with self.s.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT g.chat_id, g.title, g.enabled, g.created_at, g.last_seen,"
                " (SELECT COUNT(*) FROM group_members m WHERE m.chat_id = g.chat_id) AS members"
                " FROM groups g ORDER BY g.last_seen DESC LIMIT 300")
        return _json([{"id": r["chat_id"], "title": r["title"] or "—", "enabled": bool(r["enabled"]),
                       "members": r["members"], "created": fmt(r["created_at"]), "seen": fmt(r["last_seen"])} for r in rows])

    async def orders(self, request: web.Request) -> web.Response:
        page = max(0, int(request.query.get("page", "0") or 0))
        async with self.s.ctx.db.read() as tx:
            total = await tx.scalar("SELECT COUNT(*) FROM orders", (), 0)
            rows = await tx.fetchall(
                "SELECT o.id, o.pack_id, o.amount, o.status, o.created_at, p.display_name AS name FROM orders o"
                " JOIN players p ON p.id = o.player_id ORDER BY o.id DESC LIMIT ? OFFSET ?", (PAGE, page * PAGE))
        return _json({"total": total, "page": page, "per": PAGE, "rows": [
            {"id": r["id"], "pack": r["pack_id"], "toman": r["amount"] // 10, "status": r["status"], "name": r["name"],
             "at": fmt(r["created_at"])} for r in rows]})

    async def audit(self, request: web.Request) -> web.Response:
        async with self.s.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT admin_id, action, detail, created_at FROM admin_log ORDER BY id DESC LIMIT 150")
        return _json([{"admin": r["admin_id"], "action": r["action"], "detail": r["detail"], "at": fmt(r["created_at"])}
                      for r in rows])

    async def broadcast(self, request: web.Request) -> web.Response:
        data = await self._body(request)
        text = str(data.get("text", "")).strip()
        if not 3 <= len(text) <= 1000:
            raise GameError("متن پیام باید بین ۳ تا ۱۰۰۰ حرف باشد.")
        if self.bot is None:
            raise GameError("ربات برای ارسال در دسترس نیست.")
        ids = await self.s.admin.group_ids()
        sent = failed = 0
        for chat_id in ids:
            try:
                await self.bot.send_message(chat_id, text)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.15)
        await self.s.admin.log_action(request[SESSION_KEY].admin_id, "broadcast", f"web sent={sent} failed={failed}")
        return _json({"sent": sent, "failed": failed})


def _player_row(r, now: int) -> dict[str, Any]:  # noqa: ANN001
    return {
        "id": r["id"], "uid": r["platform_user_id"], "name": r["display_name"], "username": r["username"] or "",
        "level": r["level"], "gold": r["gold"], "crystal": r["crystal"], "wins": r["wins"], "losses": r["losses"],
        "banned": bool(r["banned"]), "vip": r["vip_until"] > now, "rating": r["rating"], "created": fmt(r["created_at"]),
    }


def _login_page(message: str, extra: str = "") -> str:
    return (
        '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>ورود به پنل</title>'
        '<link rel="stylesheet" href="/static/style.css"></head><body class="login">'
        f'<div class="login-card"><div class="logo">⚔️</div><h1>قلمرو جاودان</h1><p>{html.escape(message)}</p>{extra}</div>'
        "</body></html>"
    )


def build_app(services: Services, auth: WebAuth, bot: Any = None, secure_cookie: bool = False) -> web.Application:
    panel = AdminWeb(services, auth, bot, secure_cookie)
    app = web.Application(middlewares=[panel.guard], client_max_size=64 * 1024)
    app.router.add_get("/", panel.index)
    app.router.add_get("/login", panel.login_page)
    app.router.add_post("/login", panel.login)
    app.router.add_static("/static", STATIC, follow_symlinks=False)
    api = [
        ("GET", "/api/me", panel.me), ("GET", "/api/stats", panel.stats), ("GET", "/api/players", panel.players),
        ("GET", "/api/players/{id:\\d+}", panel.player), ("POST", "/api/players/{id:\\d+}/give", panel.give),
        ("POST", "/api/players/{id:\\d+}/level", panel.set_level), ("POST", "/api/players/{id:\\d+}/ban", panel.ban),
        ("POST", "/api/players/{id:\\d+}/item", panel.give_item), ("GET", "/api/items", panel.items),
        ("GET", "/api/groups", panel.groups), ("GET", "/api/orders", panel.orders), ("GET", "/api/audit", panel.audit),
        ("POST", "/api/broadcast", panel.broadcast), ("POST", "/api/logout", panel.logout),
    ]
    for method, path, handler in api:
        app.router.add_route(method, path, handler)
    return app


async def start_web(services: Services, auth: WebAuth, bot: Any, host: str, port: int, secure_cookie: bool) -> web.AppRunner:
    runner = web.AppRunner(build_app(services, auth, bot, secure_cookie), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("web panel listening on %s:%s", host, port)
    return runner


__all__ = ["AdminWeb", "build_app", "find_item", "start_web"]
