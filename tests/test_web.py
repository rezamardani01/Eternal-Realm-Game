import pytest
from aiohttp.test_utils import TestClient, TestServer

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.web.auth import LINK_TTL, MAX_FAILURES, SESSION_TTL, WebAuth
from eternal_realm.web.server import COOKIE, build_app

from .harness import Harness


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))

        class Sent:
            message_id = 77

        return Sent()


@pytest.fixture
def services(db, clock, rng):
    s = Settings(token="t", owner_id=1, web_enabled=True, web_url="http://example.test:8080")
    return Services.build(AppContext(db, s, clock=clock, rng=rng))


@pytest.fixture
def auth(clock):
    return WebAuth(clock=lambda: clock.now_value() if hasattr(clock, "now_value") else clock())


@pytest.fixture
async def client(services, auth):
    bot = FakeBot()
    app = build_app(services, auth, bot)
    async with TestClient(TestServer(app)) as c:
        c.bot = bot
        yield c


async def sign_in(client, auth, admin_id=1):
    token = auth.issue_link_token(admin_id)
    page = await client.get(f"/login?token={token}")
    assert page.status == 200 and "ورود به پنل مدیریت" in await page.text()
    resp = await client.post("/login", data={"token": token}, allow_redirects=False)
    assert resp.status == 302
    me = await (await client.get("/api/me")).json()
    return me["csrf"]


async def hero(services, db, uid, name, level=5, gold=0):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


# --- sign-in ------------------------------------------------------------------------------------------------
async def test_api_needs_a_session(client):
    for path in ("/api/me", "/api/stats", "/api/players", "/api/groups", "/api/orders", "/api/audit"):
        assert (await client.get(path)).status == 401
    assert (await client.post("/api/broadcast", json={"text": "hello"})).status == 401
    index = await client.get("/")
    assert "پنل وب" in await index.text()  # the login hint, not the dashboard


async def test_a_link_works_once_and_can_be_refused(client, auth):
    token = auth.issue_link_token(1)
    ok = await client.post("/login", data={"token": token}, allow_redirects=False)
    assert ok.status == 302 and COOKIE in ok.cookies
    again = await client.post("/login", data={"token": token}, allow_redirects=False)
    assert again.status == 403
    bad = await client.get("/login?token=nonsense")
    assert bad.status == 403


async def test_viewing_the_link_does_not_use_it_up(client, auth):
    token = auth.issue_link_token(1)
    for _ in range(3):  # link-preview robots may open the address several times
        assert (await client.get(f"/login?token={token}")).status == 200
    assert (await client.post("/login", data={"token": token}, allow_redirects=False)).status == 302


def test_links_expire_and_a_new_one_cancels_the_old(clock):
    now = [1000.0]
    auth = WebAuth(clock=lambda: now[0])
    old = auth.issue_link_token(7)
    fresh = auth.issue_link_token(7)
    assert not auth.peek(old) and auth.peek(fresh)
    now[0] += LINK_TTL + 1
    assert auth.redeem(fresh, "1.1.1.1") is None
    token = auth.issue_link_token(7)
    sid = auth.redeem(token, "1.1.1.1")
    assert auth.session(sid) is not None
    now[0] += SESSION_TTL + 1
    assert auth.session(sid) is None


def test_guessing_links_locks_the_address_out():
    auth = WebAuth(clock=lambda: 1000.0)
    for _ in range(MAX_FAILURES):
        assert auth.redeem("wrong", "9.9.9.9") is None
    good = auth.issue_link_token(1)
    assert auth.redeem(good, "9.9.9.9") is None  # even a real link is refused while locked out
    assert auth.redeem(good, "8.8.8.8") is not None  # other addresses are unaffected


async def test_changes_need_the_csrf_header(client, auth, services, db):
    p = await hero(services, db, 5, "آرش")
    csrf = await sign_in(client, auth)
    url = f"/api/players/{p.id}/give"
    assert (await client.post(url, json={"gold": 10})).status == 403
    assert (await client.post(url, json={"gold": 10}, headers={"X-CSRF-Token": "wrong"})).status == 403
    ok = await client.post(url, json={"gold": 10}, headers={"X-CSRF-Token": csrf})
    assert ok.status == 200


async def test_security_headers_and_logout(client, auth):
    csrf = await sign_in(client, auth)
    resp = await client.get("/api/me")
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Frame-Options"] == "DENY" and resp.headers["Cache-Control"] == "no-store"
    await client.post("/api/logout", headers={"X-CSRF-Token": csrf})
    assert (await client.get("/api/me")).status == 401


# --- the panel itself -------------------------------------------------------------------------------------------
async def test_dashboard_and_lists(client, auth, services, db):
    await hero(services, db, 6, "سارا", level=9, gold=100)
    await hero(services, db, 7, "رها")
    await sign_in(client, auth)
    stats = await (await client.get("/api/stats")).json()
    assert stats["players"] == 2 and len(stats["series"]["new"]) == 14 and stats["new_today"] == 2
    found = await (await client.get("/api/players?q=سارا")).json()
    assert [r["name"] for r in found["rows"]] == ["سارا"] and found["total"] == 1
    assert (await (await client.get("/api/players?q=%25")).json())["total"] == 0  # LIKE wildcards are escaped
    detail = await (await client.get(f"/api/players/{found['rows'][0]['id']}")).json()
    assert detail["level"] == 9 and detail["history"]
    assert (await client.get("/api/players/99999")).status == 400
    assert (await client.get("/api/groups")).status == 200 and (await client.get("/api/orders")).status == 200
    assert await (await client.get("/api/clans")).json() == []
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO clans (id, name, leader_id, created_at) VALUES (1, 'شیران', ?, 1)", (found["rows"][0]["id"],))
        await tx.execute("INSERT INTO clan_members (player_id, clan_id, role, joined_at) VALUES (?, 1, 'leader', 1)", (found["rows"][0]["id"],))
    clans = await (await client.get("/api/clans")).json()
    assert clans[0]["name"] == "شیران" and clans[0]["members"] == 1 and clans[0]["leader"] == "سارا"


async def test_admin_actions_change_the_game_and_are_logged(client, auth, services, db):
    p = await hero(services, db, 8, "نگار", gold=0)
    csrf = await sign_in(client, auth, admin_id=1)
    h = {"X-CSRF-Token": csrf}
    base = f"/api/players/{p.id}"
    gold_before = (await services.players.require(8)).gold
    assert (await client.post(f"{base}/give", json={"gold": 500, "crystal": 3}, headers=h)).status == 200
    after = await services.players.require(8)
    assert after.gold == gold_before + 500 and after.crystal >= 3
    assert (await client.post(f"{base}/level", json={"level": 12}, headers=h)).status == 200
    assert (await services.players.require(8)).level == 12
    assert (await client.post(f"{base}/ban", json={"banned": True}, headers=h)).status == 200
    assert (await services.players.require(8)).banned
    assert (await client.post(f"{base}/item", json={"item": "iron_ore", "qty": 4}, headers=h)).status == 200
    audit = await (await client.get("/api/audit")).json()
    assert {"give_currency", "set_level", "ban", "give_item"} <= {r["action"] for r in audit}
    assert all(r["admin"] == 1 for r in audit)


async def test_bad_input_is_rejected_not_executed(client, auth, services, db):
    p = await hero(services, db, 9, "پویا", gold=0)
    csrf = await sign_in(client, auth)
    h = {"X-CSRF-Token": csrf}
    base = f"/api/players/{p.id}"
    before = (await services.players.require(9)).gold
    for body in ({"gold": "abc"}, {"gold": 10**12}, {"gold": 1.5}, {"gold": True}, {}, []):
        assert (await client.post(f"{base}/give", json=body, headers=h)).status == 400
    assert (await client.post(f"{base}/level", json={"level": 0}, headers=h)).status == 400
    assert (await client.post(f"{base}/item", json={"item": "nope", "qty": 1}, headers=h)).status == 400
    assert (await client.post(f"{base}/item", json={"item": "iron_ore", "qty": 10**6}, headers=h)).status == 400
    assert (await client.post(f"{base}/give", data="not json", headers=h)).status == 400
    assert (await services.players.require(9)).gold == before


async def test_broadcast_reaches_active_groups(client, auth, services, db):
    await services.groups.touch(-100, "گروه یک")
    await services.groups.touch(-200, "گروه دو")
    csrf = await sign_in(client, auth)
    h = {"X-CSRF-Token": csrf}
    assert (await client.post("/api/broadcast", json={"text": "hi"}, headers=h)).status == 400
    ok = await (await client.post("/api/broadcast", json={"text": "سلام به همه"}, headers=h)).json()
    assert ok == {"sent": 2, "failed": 0}
    assert {c for c, _ in client.bot.sent} == {-100, -200}


async def test_the_static_page_has_no_inline_script_or_style():
    from pathlib import Path

    page = Path("eternal_realm/web/static/index.html").read_text(encoding="utf-8")
    assert "<script>" not in page and "style=" not in page  # the CSP forbids both
    js = Path("eternal_realm/web/static/app.js").read_text(encoding="utf-8")
    assert js.count("innerHTML") == 1 and "d.innerHTML = '<linearGradient" in js  # only the fixed chart gradients


# --- the bot command ---------------------------------------------------------------------------------------------------
async def test_bot_sends_a_login_link_only_to_admins_in_private(services, db):
    h = Harness(services)
    await hero(services, db, 1, "ارباب")
    await hero(services, db, 2, "عادی")
    await h.say(2, "پنل وب")
    assert not h.session.sent("sendMessage")  # silent for non-admins
    await h.say(1, "پنل وب")
    text = h.session.sent("sendMessage")[-1]["text"]
    assert "http://example.test:8080/login?token=" in text
    token = text.split("token=")[1].split()[0]
    assert services.web_auth.peek(token)
    await h.say(1, "پنل وب", group=True)  # never in a group
    assert len(h.session.sent("sendMessage")) == 1


async def test_panel_controls_for_vip_ticket_pet_title_and_shortcuts(client, auth, services, db):
    p = await hero(services, db, 30, "کیان")
    csrf = await sign_in(client, auth)
    h = {"X-CSRF-Token": csrf}
    base = f"/api/players/{p.id}"
    assert (await client.post(f"{base}/vip", json={"days": 30}, headers=h)).status == 200
    assert (await services.players.require(30)).vip_until == services.ctx.now() + 30 * 86400
    detail = await (await client.get(base)).json()
    assert detail["vip_until"] and detail["ticket"] is False
    assert (await client.post(f"{base}/vip", json={"clear": True}, headers=h)).status == 200
    assert (await services.players.require(30)).vip_until == 0
    assert (await client.post(f"{base}/vip", json={"days": 99999}, headers=h)).status == 400

    assert (await (await client.post(f"{base}/ticket", json={"give": True}, headers=h)).json())["changed"] is True
    assert (await (await client.get(base)).json())["ticket"] is True
    assert (await (await client.post(f"{base}/ticket", json={"give": False}, headers=h)).json())["changed"] is True

    assert (await client.post(f"{base}/pet", json={"pet": "fox", "give": True}, headers=h)).status == 200
    assert await services.pets.owned(p.id) == {"fox": True}
    assert (await client.post(f"{base}/pet", json={"pet": "nope", "give": True}, headers=h)).status == 400
    assert (await client.post(f"{base}/pet", json={"pet": "fox", "give": False}, headers=h)).status == 200
    assert await services.pets.owned(p.id) == {}

    assert (await client.post(f"{base}/title", json={"title": "قهرمان بزرگ"}, headers=h)).status == 200
    assert (await services.players.require(30)).honor == "قهرمان بزرگ"
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 1 WHERE id = ?", (p.id,))
        await tx.execute("INSERT INTO cooldowns (player_id, key, until) VALUES (?, 'hunt', 9999999999)", (p.id,))
    assert (await client.post(f"{base}/energy", json={}, headers=h)).status == 200
    assert (await client.post(f"{base}/cooldowns", json={}, headers=h)).status == 200
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM cooldowns WHERE player_id = ?", (p.id,), 0) == 0
    audit = {r["action"] for r in await (await client.get("/api/audit")).json()}
    assert {"set_vip", "grant_ticket", "revoke_ticket", "grant_pet", "revoke_pet", "set_title", "refill_energy", "reset_cooldowns"} <= audit


async def test_group_controls_and_event_creation(client, auth, services, db):
    for uid in (40, 41, 42):
        await hero(services, db, uid, f"عضو{uid}", level=6)
    await services.groups.touch(-300, "گروه سیصد")
    async with db.transaction() as tx:
        for pid in (1, 2, 3):
            await tx.execute("INSERT INTO group_members (chat_id, player_id, points, last_active) VALUES (-300, ?, 0, ?)",
                             (pid, services.ctx.now()))
    csrf = await sign_in(client, auth)
    h = {"X-CSRF-Token": csrf}
    assert (await client.post("/api/groups/-300/toggle", json={"enabled": False}, headers=h)).status == 200
    assert not (await (await client.get("/api/groups")).json())[0]["enabled"]
    assert (await client.post("/api/groups/-999/toggle", json={"enabled": True}, headers=h)).status == 400
    assert (await client.post("/api/groups/-300/message", json={"text": "سلام گروه"}, headers=h)).status == 200
    assert (-300, "سلام گروه") in client.bot.sent
    assert (await client.post("/api/groups/-300/event", json={"kind": "bogus"}, headers=h)).status == 400
    ok = await client.post("/api/groups/-300/event", json={"kind": "merchant"}, headers=h)
    assert ok.status == 200 and (await ok.json())["kind"] == "merchant"


async def test_membership_settings_api(client, auth, services):
    csrf = await sign_in(client, auth)
    h = {"X-CSRF-Token": csrf}
    assert await (await client.get("/api/membership")).json() == {"enabled": False, "channels": []}
    bad = await client.post("/api/membership", json={"enabled": True, "channels": []}, headers=h)
    assert bad.status == 400
    good = await client.post("/api/membership", json={"enabled": True, "channels": [
        {"chat": "@mychannel", "title": "کانال ما", "link": "https://ble.ir/join/x"}]}, headers=h)
    assert good.status == 200
    saved = await (await client.get("/api/membership")).json()
    assert saved["enabled"] and saved["channels"][0]["chat"] == "@mychannel"
    assert (await client.post("/api/membership", json={"enabled": True, "channels": ["x"]}, headers=h)).status == 400
    assert (await client.post("/api/membership/probe", json={"chat": "bad chat"}, headers=h)).status == 400
