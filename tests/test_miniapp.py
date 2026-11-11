"""The mini app's API: who may call it, and that every answer comes from the same services the bot uses."""

import json
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from eternal_realm.bot import app as _bot_app  # noqa: F401 - registers every panel screen
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.web import auth, server

TOKEN = "123456:TEST"


def signed(user_id: int, age: int = 0, token: str = TOKEN) -> str:
    return auth.sign({"auth_date": str(int(time.time()) - age), "query_id": "q", "user": json.dumps({"id": user_id, "username": f"u{user_id}"})}, token)


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token=TOKEN, owner_id=999), clock=clock, rng=rng))


@pytest.fixture
async def client(services):
    async with TestClient(TestServer(server.create_app(services, None))) as c:
        yield c


async def hero(services, db, uid=1, level=12):
    p = await services.players.register(uid, f"u{uid}", f"قهرمان{uid}", "elf", "archer")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, energy = 300, wheel_spins = 2 WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=20_000, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def get(client, path, uid=1, **headers):
    response = await client.get(f"/api/{path}", headers={"X-Init-Data": signed(uid), **headers})
    return await response.json()


async def post(client, path, payload, uid=1):
    response = await client.post(f"/api/{path}", json=payload, headers={"X-Init-Data": signed(uid)})
    return await response.json()


# --- who is asking ---------------------------------------------------------------------------------------------------
def test_init_data_is_checked_by_signature_and_age():
    now = int(time.time())
    user = auth.validate(signed(42), TOKEN, now)
    assert user.id == 42 and user.username == "u42"
    with pytest.raises(auth.AuthError):
        auth.validate(signed(42, token="another:token"), TOKEN, now)  # signed with somebody else's token
    with pytest.raises(auth.AuthError):
        auth.validate(signed(42).replace("u42", "u43"), TOKEN, now)  # tampered with after signing
    with pytest.raises(auth.AuthError):
        auth.validate(signed(42, age=3 * 86400), TOKEN, now)  # too old
    with pytest.raises(auth.AuthError):
        auth.validate("", TOKEN, now)


async def test_the_api_refuses_callers_without_valid_init_data(client, services, db):
    await hero(services, db)
    assert (await client.get("/api/me")).status == 401
    assert (await client.get("/api/me", headers={"X-Init-Data": "user=%7B%22id%22%3A1%7D&hash=00"})).status == 401
    # the preview's plain user id is accepted only when the preview switch is on, which it never is here
    assert (await client.get("/api/me", headers={"X-Dev-User": "1"})).status == 401
    assert (await get(client, "me"))["ok"] is True


async def test_a_caller_without_a_hero_is_sent_to_create_one(client, services):
    answer = await get(client, "me", uid=77)
    assert answer["ok"] is False and answer["needs_hero"] is True
    options = await get(client, "onboarding", uid=77)
    assert options["races"] and options["classes"]
    made = await post(client, "register", {"name": "نگار", "race": "fairy", "class": "mage"}, uid=77)
    assert made["ok"] and made["player"]["name"] == "نگار"
    assert (await post(client, "register", {"name": "دوباره", "race": "elf", "class": "mage"}, uid=77))["ok"] is False
    assert (await services.players.require(77)).name == "نگار"


# --- reading and the panel bridge ----------------------------------------------------------------------------------------
async def test_the_pages_read_real_data(client, services, db):
    await hero(services, db)
    me = await get(client, "me")
    assert me["player"]["level"] == 12 and me["player"]["gold"] >= 20_000 and len(me["missions"]) >= 3 and me["is_admin"] is False
    page = await get(client, "hero")
    assert {s["id"] for s in page["slots"]} >= {"weapon", "armor", "boots"}
    cards = (await get(client, "adventure"))["activities"]
    assert cards[0]["id"] == "hunt" and any(c["id"] == "fishing" for c in cards)
    assert (await get(client, "clan"))["clan"] is None
    assert (await get(client, "market"))["listings"] == []


async def test_every_bot_screen_is_reachable_through_the_bridge_and_buttons_carry_their_target(client, services, db):
    await hero(services, db)
    shown = (await post(client, "screen", {"s": "trip"}))["shown"]
    assert "سفر قهرمان" in shown["text"]
    targets = {button.get("s") for row in shown["rows"] for button in row}
    assert {"story", "maze", "tower"} <= targets
    premium = (await post(client, "screen", {"s": "prem", "a": "coins"}))["shown"]
    assert any(button.get("buy", {}).get("kind") == "cash" for row in premium["rows"] for button in row)
    assert (await post(client, "screen", {"s": "no_such_screen"}))["ok"] is False
    assert (await post(client, "screen", {"s": "adm"}))["ok"] is False  # the admin panel is for admins only
    toast_only = await post(client, "screen", {"s": "stat", "a": "atk"})
    assert toast_only["shown"]["text"] is None and toast_only["shown"]["toast"]


async def test_a_game_error_comes_back_as_a_friendly_answer_not_a_crash(client, services, db):
    await hero(services, db)
    answer = await post(client, "screen", {"s": "clancreate", "a": "x"})
    assert answer["ok"] is False and answer["error"]


async def test_the_market_price_prompt_is_described_for_the_page(client, services, db):
    p = await hero(services, db)
    async with db.transaction() as tx:
        await services.inventory.grant(tx, p.id, "iron_ore", 10)
    shown = (await post(client, "screen", {"s": "listask", "a": "s", "b": "iron_ore.4"}))["shown"]
    assert shown["prompt"]["form"] == "listing" and shown["prompt"]["kind"] == "s" and shown["prompt"]["ref"] == "iron_ore.4"
    done = await post(client, "screen", {"s": "lconfirm", "a": "s", "b": "iron_ore.4~300"})
    assert done["ok"] and len(await services.market.mine(p)) == 1


# --- acting -------------------------------------------------------------------------------------------------------------------
async def test_an_activity_and_a_hunt_pay_through_the_same_services(client, services, db):
    p = await hero(services, db)
    fished = (await post(client, "act", {"id": "fishing"}))["result"]
    assert fished["kind"] == "activity" and fished["energy"] < 300
    assert (await post(client, "act", {"id": "fishing"}))["ok"] is False  # the same waiting time as in the bot
    hunted = (await post(client, "act", {"id": "hunt"}))["result"]
    assert hunted["kind"] == "hunt" and hunted["hp"][1] > 0
    assert (await post(client, "act", {"id": "nope"}))["ok"] is False
    assert (await services.players.require(1)).energy < 300 and p


async def test_the_wheel_spins_on_the_server_and_tells_the_page_the_prize(client, services, db):
    await hero(services, db)
    state = await get(client, "wheel")
    assert state["spins"] == 2 and state["free"] is True and len(state["slices"]) >= 10
    spun = await post(client, "wheel", {"free": False})
    assert spun["prize"]["label"] and spun["left"] == 1
    await post(client, "wheel", {"free": True})
    assert (await post(client, "wheel", {"free": True}))["ok"] is False  # one free spin a day


async def test_the_hero_path_lists_a_hundred_tiers_and_claims_once(client, services, db):
    p = await hero(services, db)
    async with db.transaction() as tx:
        from eternal_realm.db.repos import season as season_repo

        for _ in range(60):
            await season_repo.add_points(tx, p.id, "boss", services.ctx.now())
    path = await get(client, "path")
    assert len(path["track"]) == 100 and path["tier"] >= 3 and path["premium"] is False
    assert (await post(client, "path", {"track": "free", "tier": 1}))["claimed"] == 1
    assert (await post(client, "path", {"track": "free", "tier": 1}))["ok"] is False
    assert (await post(client, "path", {"track": "ticket", "tier": 1}))["ok"] is False  # no ticket
    assert (await post(client, "path", {"all": True}))["claimed"] >= 1
    assert (await get(client, "path"))["track"][0]["free_claimed"] is True


async def test_the_treasury_lists_every_shelf_with_prices_from_the_packs(client, services, db):
    await hero(services, db)
    shop = await get(client, "treasury")
    shelves = {s["id"]: s["packs"] for s in shop["shelves"]}
    assert {"vip", "coins", "crystals", "rare"} <= set(shelves)
    assert all(pack["toman"] > 0 for packs in shelves.values() for pack in packs)
    assert any(pack["items"] and pack["items"][0]["item"]["id"] == "dragon_scale" for pack in shelves["rare"])
    assert shop["vip"]["active"] is False and len(shop["vip"]["perks"]) == 4
    assert all(0 < deal["percent"] < 100 and deal["toman"] < deal["full_toman"] for deal in shop["deals"])


async def test_the_daily_gift_shows_a_week_and_opens_once_a_day(client, services, db, clock):
    await hero(services, db)
    week = await get(client, "daily")
    assert week["ready"] is True and len(week["days"]) == 7 and week["days"][0]["state"] == "today"
    assert week["days"][6]["chest"] is not None  # the seventh day is a chest
    gold = (await services.players.require(1)).gold
    won = await post(client, "daily", {})
    assert won["gold"] > 0 and won["streak"] == 1 and (await services.players.require(1)).gold == gold + won["gold"]
    assert (await post(client, "daily", {}))["ok"] is False
    after = await get(client, "daily")
    assert after["ready"] is False and after["days"][0]["state"] == "claimed" and after["days"][1]["state"] == "next" and after["next_in"] > 0


async def test_the_leaderboards_name_race_class_and_my_place(client, services, db):
    await hero(services, db)
    await hero(services, db, uid=2, level=30)
    board = await get(client, "leaders?board=level")
    assert [e["rank"] for e in board["entries"]] == [1, 2] and board["entries"][0]["level"] == 30
    assert board["entries"][1]["me"] is True and board["my_position"] == 2
    assert board["entries"][0]["race"] == "elf" and board["entries"][0]["class"] == "archer"
    assert {b["id"] for b in board["boards"]} >= {"level", "rich", "path", "bosses"} and board["brackets"]
    assert (await get(client, "leaders?board=level&bracket=b1"))["entries"][0]["me"] is True  # only heroes up to level 20
    assert (await get(client, "leaders?board=path"))["brackets"] == []
    assert (await get(client, "leaders?board=nope"))["ok"] is False
    assert (await get(client, "leaders?board=clans"))["entries"] == []
    await post(client, "screen", {"s": "clancreate", "a": "شیرها"})
    clans = await get(client, "leaders?board=clans")
    assert clans["entries"][0]["name"] == "شیرها" and clans["entries"][0]["me"] is True and clans["my_position"] == 1


async def test_the_exchange_trades_through_the_same_service(client, services, db):
    await hero(services, db)
    state = await get(client, "exchange")
    assert state["rate"] > 0 and state["left_today"] > 0
    before = await services.players.require(1)
    bought = await post(client, "exchange", {"side": "buy", "amount": 2})
    after = await services.players.require(1)
    assert after.crystal == before.crystal + 2 and after.gold == before.gold - bought["gold"]
    sold = await post(client, "exchange", {"side": "sell", "amount": 1})
    assert sold["gold"] < bought["gold"] and (await services.players.require(1)).crystal == after.crystal - 1
    assert (await post(client, "exchange", {"side": "sell", "amount": 10_000}))["ok"] is False
    assert (await post(client, "exchange", {"side": "gift", "amount": 1}))["ok"] is False


async def test_the_forge_lists_needs_and_makes_a_piece_only_when_ready(client, services, db):
    p = await hero(services, db)
    recipes = (await get(client, "forge"))["recipes"]
    assert recipes and all(r["needs"] and r["result"]["name"] for r in recipes)
    first = recipes[0]
    assert first["ready"] is False and (await post(client, "forge", {"id": first["id"]}))["ok"] is False
    from eternal_realm.game.data.recipes import get_recipe

    recipe = get_recipe(first["id"])
    async with db.transaction() as tx:
        if recipe.base:
            await services.inventory.grant(tx, p.id, recipe.base, 1)
        for item_id, qty in recipe.materials.items():
            await services.inventory.grant(tx, p.id, item_id, qty)
    ready = next(r for r in (await get(client, "forge"))["recipes"] if r["id"] == first["id"])
    assert ready["ready"] is True and all(n["have"] >= n["need"] for n in ready["needs"])
    made = await post(client, "forge", {"id": first["id"]})
    assert made["item"]["id"] == recipe.result and made["stats"]


async def test_chests_are_bought_and_opened_through_the_chest_service(client, services, db):
    await hero(services, db)
    shelf = (await get(client, "chests"))["chests"]
    buyable = next(c for c in shelf if c["price"] and c["price"]["currency"] == "gold")
    assert buyable["owned"] == 0 and (await post(client, "chests", {"open": buyable["item"]["id"]}))["ok"] is False
    assert (await post(client, "chests", {"buy": buyable["item"]["id"]}))["bought"] == buyable["item"]["id"]
    assert next(c for c in (await get(client, "chests"))["chests"] if c["item"]["id"] == buyable["item"]["id"])["owned"] == 1
    opened = await post(client, "chests", {"open": buyable["item"]["id"]})
    assert opened["ok"] and (opened["gold"] or opened["crystal"] or opened["item"])
    assert (await post(client, "chests", {"open": "iron_ore"}))["ok"] is False


async def test_the_quest_board_lists_today_and_the_week(client, services, db):
    await hero(services, db)
    board = await get(client, "missions")
    assert len(board["missions"]) >= 3 and all(m["target"] > 0 for m in board["missions"])
    assert [p["days"] for p in board["week"]["prizes"]] == [3, 5, 7] and board["week"]["left"] > 0


async def test_the_bot_menu_opens_the_mini_app_from_its_first_row(db, clock, rng):
    from eternal_realm.web import bridge

    for url, shown_first in (("https://play.example.com", True), ("", False)):
        services = Services.build(AppContext(db, Settings(token=TOKEN, owner_id=999, miniapp_url=url), clock=clock, rng=rng))
        p = await services.players.find(5) or await services.players.register(5, "u5", "قهرمان", "elf", "archer")
        first = (await bridge.run(services, p, "home"))["rows"][0][0]
        assert (first["text"] == "🎮 باز کردن مینی اپ") is shown_first


async def test_a_fight_is_played_move_by_move(client, services, db):
    await hero(services, db, level=20)
    assert (await get(client, "fight"))["fight"] is None
    await post(client, "screen", {"s": "arenago", "a": "easy"})
    fight = (await get(client, "fight"))["fight"]
    assert fight["hero"]["hp"] > 0 and fight["foe"]["hp"] > 0 and fight["skill"]["name"]
    answer = None
    for _ in range(60):
        answer = await post(client, "fight", {"action": "attack"})
        assert answer["ok"]
        if answer["fight"] is None:
            break
    assert answer["fight"] is None and answer["shown"]["text"]  # it ended with a result screen
    assert (await post(client, "fight", {"action": "dance"}))["ok"] is False


async def test_paying_needs_the_bot_and_nothing_is_delivered_by_the_page(client, services, db):
    p = await hero(services, db)
    answer = await post(client, "buy", {"kind": "cash", "id": "coins_s"})
    assert answer["ok"] is False  # the test server has no bot: no invoice, and no goods either
    assert (await services.players.require(1)).gold == p.gold


async def test_one_user_cannot_flood_the_api(client, services, db):
    await hero(services, db)
    codes = [(await client.get("/api/adventure", headers={"X-Init-Data": signed(1)})).status for _ in range(server.RATE_MAX + 5)]
    assert codes[0] == 200 and codes[-1] == 429
