"""Realm rule: a city per hero with buildings, people, an army, defences, raids and war reports.

Resources are produced lazily: every access first brings the city up to date from ``last_tick``, so no background
loop is needed. A raid is one transaction: troops leave, the battle is calculated here, loot and losses are
applied and the report is stored, all or nothing.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import clans as clan_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa, normalize
from ..data import city as d
from ..engine import siege
from ..models import Player
from .players import PlayerService

DAY = 24 * 3600


@dataclass
class Batch:
    id: int
    kind: str
    qty: int
    ready_at: int


@dataclass
class Build:
    id: int
    kind: str
    level: int
    ready_at: int


@dataclass
class City:
    id: int
    player_id: int
    name: str
    flag: str
    res: dict[str, float]
    pop: float
    happiness: float
    last_tick: int
    shield_until: int
    trophies: int
    created_at: int
    last_active: int
    att_day: int
    att_count: int
    levels: dict[str, int] = field(default_factory=dict)
    troops: dict[str, int] = field(default_factory=dict)
    traps: dict[str, int] = field(default_factory=dict)
    training: list[Batch] = field(default_factory=list)
    owner_name: str = ""
    owner_uid: int = 0
    clan: str = ""
    #: when the owner's bought 2x boost ends (it doubles what the city produces)
    boost_until: int = 0
    builds: list[Build] = field(default_factory=list)
    #: the automatic messages (hunger, full storage...) are switched on
    alerts: bool = True

    # --- derived numbers -------------------------------------------------------------------
    @property
    def castle(self) -> int:
        return self.levels.get("castle", 1)

    @property
    def slots_total(self) -> int:
        return d.slots_for(self.castle)

    @property
    def slots_used(self) -> int:
        planned = {b.kind for b in self.builds if self.levels.get(b.kind, 0) == 0}
        return sum(1 for b, lv in self.levels.items() if b != "castle" and lv > 0) + len(planned - {"castle"})

    @property
    def pop_cap(self) -> int:
        return d.population_cap(self.castle)

    @property
    def storage(self) -> int:
        return d.storage_cap(self.levels.get("warehouse", 0), self.castle)

    @property
    def army(self) -> int:
        return sum(self.troops.values())

    @property
    def in_training(self) -> int:
        return sum(b.qty for b in self.training)

    @property
    def space_used(self) -> int:
        used = sum(q * d.get_troop(k).cap for k, q in self.troops.items())
        return used + sum(b.qty * d.get_troop(b.kind).cap for b in self.training)

    @property
    def capacity(self) -> int:
        return d.army_capacity(self.levels)

    @property
    def recruitable(self) -> int:
        return max(0, int(self.pop * 0.5) - self.army - self.in_training)

    @property
    def workplaces(self) -> int:
        return sum(self.levels.get(b, 0) for b in d.ECON_IDS) * d.PEOPLE_PER_WORKPLACE_LEVEL

    @property
    def employed(self) -> int:
        return min(max(0, int(self.pop) - self.army), self.workplaces)

    @property
    def unemployed(self) -> int:
        return max(0, int(self.pop) - self.army - self.employed)

    @property
    def army_power(self) -> int:
        return sum(q * d.unit_power(d.get_troop(k)) for k, q in self.troops.items())

    @property
    def defense_power(self) -> int:
        return (
            self.army_power + self.levels.get("wall", 0) * 500 + self.levels.get("tower", 0) * 600
            + self.levels.get("hospital", 0) * 100 + sum(self.traps.values()) * 20
        )

    def shielded(self, now: int) -> bool:
        return self.shield_until > now

    def amount(self, res: str) -> int:
        return int(self.res[res])

    def rates(self, boost: float = 1.0) -> tuple[dict[str, float], float]:
        """Per-hour production of each resource and the food eaten per hour (``boost`` doubles production)."""
        mult = (0.5 if self.happiness < 30 else 1.0) * boost
        prod = {r: 0.0 for r in d.RES}
        for b, lv in self.levels.items():
            if b in d.PRODUCTION:
                res, per = d.PRODUCTION[b]
                prod[res] += per * lv * mult
        prod["gold"] += self.pop * d.TAX_PER_PERSON * mult
        eaten = self.pop * d.FOOD_PER_PERSON + (self.army + self.in_training) * d.FOOD_PER_SOLDIER
        return prod, eaten

    def snapshot(self) -> dict:
        return {"levels": dict(self.levels), "troops": dict(self.troops), "traps": dict(self.traps)}


@dataclass
class Alert:
    uid: int
    text: str


@dataclass
class Target:
    city: City
    #: the most each resource could be taken (already limited by the owner's inactivity)
    loot: dict[str, int]
    inactive_days: int


@dataclass
class AttackResult:
    attack_id: int
    stars: int
    destruction: float
    loot: dict[str, int]
    sent: dict[str, int]
    lost: dict[str, int]
    log: list[str]
    destroyed: list[str]
    castle_down: bool
    trophies: int
    shield: int
    defender_uid: int
    defender_city: str
    attacker_name: str
    xp: int = 0
    def_lost: dict[str, int] = field(default_factory=dict)


def clean_city_name(raw: str) -> str:
    name = normalize(raw)
    if not d.NAME_MIN <= len(name) <= d.NAME_MAX:
        raise GameError(f"نام شهر باید بین {fa(d.NAME_MIN)} تا {fa(d.NAME_MAX)} حرف باشد.")
    if any(ch in name for ch in "[]()*_`\n"):
        raise GameError("در نام شهر نشانه‌های ویژه نگذارید؛ فقط حرف، عدد و فاصله.")
    return name


def day_of(now: int) -> int:
    return (now + 12600) // 86400


class CityService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # --- loading and bringing up to date ----------------------------------------------------------
    async def _load_row(self, tx: Tx, row: Row) -> City:
        city = City(
            row["id"], row["player_id"], row["name"], row["flag"],
            {r: float(row[r]) for r in d.RES}, float(row["population"]), float(row["happiness"]), row["last_tick"],
            row["shield_until"], row["trophies"], row["created_at"], row["last_active"], row["att_day"], row["att_count"],
        )
        cid = city.id
        city.levels = {r["kind"]: r["level"] for r in await tx.fetchall("SELECT kind, level FROM city_buildings WHERE city_id = ?", (cid,))}
        city.troops = {r["kind"]: r["qty"] for r in await tx.fetchall("SELECT kind, qty FROM city_troops WHERE city_id = ? AND qty > 0", (cid,))}
        city.traps = {r["kind"]: r["qty"] for r in await tx.fetchall("SELECT kind, qty FROM city_traps WHERE city_id = ? AND qty > 0", (cid,))}
        city.training = [
            Batch(r["id"], r["kind"], r["qty"], r["ready_at"])
            for r in await tx.fetchall("SELECT * FROM city_training WHERE city_id = ? ORDER BY ready_at", (cid,))
        ]
        city.builds = [
            Build(r["id"], r["kind"], r["level"], r["ready_at"])
            for r in await tx.fetchall("SELECT * FROM city_builds WHERE city_id = ? ORDER BY ready_at", (cid,))
        ]
        city.alerts = bool(row["alerts"])
        owner = await tx.fetchone(
            "SELECT display_name, platform_user_id, boost_until FROM players WHERE id = ?", (city.player_id,)
        )
        if owner:
            city.owner_name, city.owner_uid, city.boost_until = owner["display_name"], owner["platform_user_id"], owner["boost_until"]
        clan = await tx.fetchone(
            "SELECT c.name FROM clan_members m JOIN clans c ON c.id = m.clan_id WHERE m.player_id = ?", (city.player_id,)
        )
        city.clan = clan["name"] if clan else ""
        return city

    async def _by_player(self, tx: Tx, player_id: int) -> City | None:
        row = await tx.fetchone("SELECT * FROM cities WHERE player_id = ?", (player_id,))
        return await self._load_row(tx, row) if row else None

    async def _by_id(self, tx: Tx, city_id: int) -> City | None:
        row = await tx.fetchone("SELECT * FROM cities WHERE id = ?", (city_id,))
        return await self._load_row(tx, row) if row else None

    async def _save(self, tx: Tx, c: City) -> None:
        await tx.execute(
            "UPDATE cities SET gold = ?, food = ?, wood = ?, stone = ?, iron = ?, population = ?, happiness = ?,"
            " last_tick = ?, shield_until = ?, trophies = ?, last_active = ?, att_day = ?, att_count = ? WHERE id = ?",
            (*[c.res[r] for r in d.RES], c.pop, c.happiness, c.last_tick, c.shield_until, c.trophies,
             c.last_active, c.att_day, c.att_count, c.id),
        )

    async def _tick(self, tx: Tx, c: City, now: int, *, owner_visit: bool = False) -> None:
        """Bring the city up to date: finished work, production, eating, growth and mood."""
        for work in [w for w in c.builds if w.ready_at <= now]:
            building = d.get_building(work.kind)
            await tx.execute(
                "INSERT INTO city_buildings (city_id, kind, level) VALUES (?, ?, ?)"
                " ON CONFLICT (city_id, kind) DO UPDATE SET level = excluded.level",
                (c.id, work.kind, work.level),
            )
            c.levels[work.kind] = work.level
            await tx.execute("DELETE FROM city_builds WHERE id = ?", (work.id,))
            c.builds.remove(work)
            await self._alert(
                tx, c.id, f"build:{work.id}", now,
                f"{building.emoji} {building.name} به سطح {fa(work.level)} رسید!\n\nسازندگان کارشان را تمام کردند و ساختمان آماده‌ی بهره‌برداری است.",
            )
        for batch in [b for b in c.training if b.ready_at <= now]:
            c.troops[batch.kind] = c.troops.get(batch.kind, 0) + batch.qty
            await tx.execute(
                "INSERT INTO city_troops (city_id, kind, qty) VALUES (?, ?, ?)"
                " ON CONFLICT (city_id, kind) DO UPDATE SET qty = qty + excluded.qty",
                (c.id, batch.kind, batch.qty),
            )
            await tx.execute("DELETE FROM city_training WHERE id = ?", (batch.id,))
            c.training.remove(batch)
            troop = d.get_troop(batch.kind)
            await self._alert(
                tx, c.id, f"train:{batch.id}", now,
                f"{troop.emoji} {fa(batch.qty)} {troop.name} آموزششان را تمام کردند و آماده‌ی نبردند!",
            )
        hours = min(max(0, now - c.last_tick), d.MAX_ELAPSED_HOURS * 3600) / 3600
        if hours > 0:
            cap = c.storage
            clock = now - hours * 3600
            while hours > 1e-9:
                dt = min(1.0, hours)
                hours -= dt
                boosted = max(0.0, min(dt * 3600, c.boost_until - clock))  # seconds of this step under the 2x boost
                prod, eaten = c.rates(1 + boosted / (dt * 3600))
                clock += dt * 3600
                starving = False
                before = dict(c.res)
                c.res["food"] += prod["food"] * dt - eaten * dt
                if c.res["food"] < 0:
                    c.res["food"], starving = 0.0, True
                for r in d.RES:
                    if r != "food":
                        c.res[r] += prod[r] * dt
                for r in d.RES:  # production stops at the storage limit, but bought or looted stock above it is kept
                    limit = cap * 2 if r == "gold" else cap
                    if c.res[r] > limit:
                        c.res[r] = float(max(limit, before[r]))
                if starving:
                    c.happiness = max(0.0, c.happiness - 6 * dt)
                    if c.happiness <= 0:
                        c.pop = max(50.0, c.pop * (1 - 0.02 * dt))
                else:
                    c.happiness = min(100.0, c.happiness + 2 * dt)
                    if c.happiness >= 40 and c.pop < c.pop_cap:
                        c.pop = min(float(c.pop_cap), c.pop + max(1.0, c.pop * 0.03) * dt)
        c.last_tick = now
        if owner_visit:
            c.last_active = now
        await self._save(tx, c)

    async def _alert(self, tx: Tx, city_id: int, key: str, now: int, text: str) -> None:
        await tx.execute(
            "INSERT OR IGNORE INTO city_alerts (city_id, key, text, created_at, sent) VALUES (?, ?, ?, ?, 0)",
            (city_id, key, text, now),
        )

    async def collect_alerts(self) -> list[Alert]:
        """Look over every recently active city and hand back the messages that are due (each is sent once)."""
        now = self.ctx.now()
        out: list[Alert] = []
        async with self.ctx.db.transaction() as tx:
            ids = [r["id"] for r in await tx.fetchall("SELECT id FROM cities WHERE last_active > ?", (now - 14 * DAY,))]
            for cid in ids:
                c = await self._by_id(tx, cid)
                if c is None:
                    continue
                await self._tick(tx, c, now)
                bucket = now // (12 * 3600)
                prod, eaten = c.rates()
                net = prod["food"] - eaten
                if c.res["food"] <= 0 or c.happiness < 30:
                    await self._alert(
                        tx, c.id, f"hunger:{bucket}", now,
                        f"🍞 {c.name} گرسنه است!\n\nانبار غذا خالی شده و رضایت مردم به {fa(round(c.happiness))}٪ رسیده؛ "
                        "اگر چاره‌ای نکنید تولید نصف می‌شود و شورش در راه است. مزرعه را ارتقا دهید یا بسته‌ی آذوقه بخرید.",
                    )
                elif net < 0 and c.res["food"] / -net < 3:
                    await self._alert(
                        tx, c.id, f"foodlow:{bucket}", now,
                        f"🌾 غذای {c.name} رو به پایان است!\n\nمصرف مردم و سربازان از تولید بیشتر است و آذوقه تا "
                        f"{fa(max(1, int(c.res['food'] / -net)))} ساعت دیگر تمام می‌شود.",
                    )
                limit = c.storage
                full = [r for r in d.RES if c.res[r] >= (limit * 2 if r == "gold" else limit) * 0.98]
                if full:
                    names = "، ".join(d.RES_INFO[r][1] for r in full)
                    await self._alert(
                        tx, c.id, f"full:{bucket}", now,
                        f"📦 انبار {c.name} پر شد!\n\n{names} به سقف ظرفیت رسیده و تولید بیشتر هدر می‌رود. "
                        "خرج کنید یا انبار را ارتقا دهید.",
                    )
                if 0 < c.shield_until <= now:
                    await self._alert(
                        tx, c.id, f"shield:{c.shield_until}", now,
                        f"🔰 سپر دفاعی {c.name} تمام شد!\n\nاز این لحظه دشمنان می‌توانند به شهر شما بتازند. "
                        "ارتش و دیوار را بسنجید یا سپر تازه بخرید.",
                    )
            rows = await tx.fetchall(
                "SELECT a.id, a.text, c.alerts AS on_, p.platform_user_id AS uid FROM city_alerts a"
                " JOIN cities c ON c.id = a.city_id JOIN players p ON p.id = c.player_id"
                " WHERE a.sent = 0 ORDER BY a.id LIMIT 200"
            )
            for r in rows:
                if r["on_"]:  # a muted city still has its queue emptied, it just hears nothing
                    out.append(Alert(r["uid"], r["text"]))
                await tx.execute("UPDATE city_alerts SET sent = 1 WHERE id = ?", (r["id"],))
        return out

    async def mine(self, player: Player, *, visit: bool = True) -> City | None:
        """The hero's city, brought up to date (``None`` when they have not founded one)."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._by_player(tx, player.id)
            if city is None:
                return None
            await self._tick(tx, city, now, owner_visit=visit)
            return city

    async def _need(self, tx: Tx, player: Player, now: int) -> City:
        city = await self._by_player(tx, player.id)
        if city is None:
            raise GameError("شما هنوز شهری ندارید. از «فرمانروایی» شهرتان را بنا کنید.")
        await self._tick(tx, city, now, owner_visit=True)
        return city

    # --- founding ------------------------------------------------------------------------------------
    async def found(self, player: Player, raw_name: str, flag: str) -> City:
        b, now = self.ctx.balance, self.ctx.now()
        name = clean_city_name(raw_name)
        if flag not in d.FLAG_EMOJIS:
            raise GameError("این پرچم وجود ندارد؛ یکی از پرچم‌ها را بردارید.")
        async with self.ctx.db.transaction() as tx:
            level = int(await tx.scalar("SELECT level FROM players WHERE id = ?", (player.id,), player.level))
            if level < b.city_min_level:
                raise GameError(f"برای بنای شهر باید به سطح {fa(b.city_min_level)} برسید؛ شما سطح {fa(level)} هستید.")
            if await tx.scalar("SELECT 1 FROM cities WHERE player_id = ?", (player.id,), 0):
                raise GameError("شما از پیش یک شهر دارید.")
            if await tx.scalar("SELECT 1 FROM cities WHERE name = ?", (name,), 0):
                raise GameError(f"شهری به نام «{name}» از پیش هست. نام دیگری برگزینید.")
            await wallet.apply(tx, player.id, gold=-b.city_found_gold, reason="city_found", now=now)
            res = d.START_RESOURCES
            city_id = await tx.execute(
                "INSERT INTO cities (player_id, name, flag, gold, food, wood, stone, iron, population, happiness,"
                " last_tick, shield_until, trophies, created_at, last_active, att_day, att_count)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 100, ?, ?, 0, ?, ?, 0, 0)",
                (player.id, name, flag, res["gold"], res["food"], res["wood"], res["stone"], res["iron"],
                 d.START_POPULATION, now, now + d.START_SHIELD, now, now),
            )
            for kind, lv in d.START_BUILDINGS.items():
                await tx.execute("INSERT INTO city_buildings (city_id, kind, level) VALUES (?, ?, ?)", (city_id, kind, lv))
            city = await self._by_id(tx, city_id)
            assert city is not None
            return city

    # --- treasury, buildings ----------------------------------------------------------------------------
    async def deposit(self, player: Player, amount: int) -> City:
        if amount <= 0:
            raise GameError("مقدار باید بیشتر از صفر باشد.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            await wallet.apply(tx, player.id, gold=-amount, reason="city_deposit", now=now)
            city.res["gold"] += amount
            await self._save(tx, city)
            return city

    def _pay(self, city: City, cost: dict[str, int]) -> None:
        short = [r for r, v in cost.items() if v > city.res[r]]
        if short:
            lines = [f"{d.RES_INFO[r][0]} {d.RES_INFO[r][1]}: دارید {fa(int(city.res[r]))} · لازم است {fa(cost[r])}" for r in short]
            raise GameError("منابع شهر کافی نیست:\n" + "\n".join(lines))
        for r, v in cost.items():
            city.res[r] -= v

    async def build(self, player: Player, kind: str) -> tuple[City, int, int]:
        """Start raising a building one level. Returns the city, the level it will reach and the seconds it takes."""
        try:
            b = d.get_building(kind)
        except KeyError:
            raise GameError("چنین ساختمانی در شهر نیست.") from None
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            level = city.levels.get(kind, 0)
            if city.builds:
                busy = d.get_building(city.builds[0].kind)
                raise GameError(f"سازندگان مشغول {busy.name} هستند؛ صبر کنید یا با کریستال کار را تمام کنید.")
            if level >= b.max_level:
                raise GameError(f"{b.name} به بالاترین سطح خود رسیده است.")
            if kind == "castle":
                if level >= d.MAX_CASTLE:
                    raise GameError("قلعه به بالاترین سطح رسیده است.")
            else:
                if city.castle < b.needs:
                    raise GameError(f"برای ساختن {b.name} قلعه باید به سطح {fa(b.needs)} برسد.")
                if level >= city.castle:
                    raise GameError(f"سطح {b.name} از سطح قلعه بالاتر نمی‌رود؛ اول قلعه را ارتقا دهید.")
                if level == 0 and city.slots_used >= city.slots_total:
                    raise GameError("جایگاه ساختمان خالی نیست؛ با ارتقای قلعه جایگاه‌های بیشتری باز می‌شود.")
            cost = d.build_cost(b, level)
            self._pay(city, {r: v for r, v in cost.items() if v})
            seconds = d.build_seconds(b, level)
            work_id = await tx.execute(
                "INSERT INTO city_builds (city_id, kind, level, ready_at) VALUES (?, ?, ?, ?)",
                (city.id, kind, level + 1, now + seconds),
            )
            city.builds.append(Build(work_id, kind, level + 1, now + seconds))
            await self._save(tx, city)
            return city, level + 1, seconds

    # --- crystals buy time ---------------------------------------------------------------------------------------
    def rush_price(self, city: City, now: int, what: str = "all", item_id: int = 0) -> int:
        works = [w.ready_at for w in city.builds] + [w.ready_at for w in city.training]
        if what == "build":
            works = [w.ready_at for w in city.builds if w.id == item_id]
        elif what == "train":
            works = [w.ready_at for w in city.training if w.id == item_id]
        return sum(d.rush_crystals(t - now) for t in works if t > now)

    async def rush(self, player: Player, what: str = "all", item_id: int = 0) -> tuple[City, int]:
        """Finish work at once for crystals: one construction, one training batch, or everything in the queue."""
        if what not in ("all", "build", "train"):
            raise GameError("چنین کاری در صف نیست.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            price = self.rush_price(city, now, what, item_id)
            if price == 0:
                raise GameError("کاری در صف نیست که بشود تسریعش کرد.")
            await wallet.apply(tx, player.id, crystal=-price, reason="city_rush", now=now)
            for work in city.builds:
                if what == "all" or (what == "build" and work.id == item_id):
                    work.ready_at = now
                    await tx.execute("UPDATE city_builds SET ready_at = ? WHERE id = ?", (now, work.id))
            for work in city.training:
                if what == "all" or (what == "train" and work.id == item_id):
                    work.ready_at = now
                    await tx.execute("UPDATE city_training SET ready_at = ? WHERE id = ?", (now, work.id))
            await self._tick(tx, city, now)
            return city, price

    # --- army ----------------------------------------------------------------------------------------------
    async def train(self, player: Player, kind: str, qty: int) -> tuple[City, Batch]:
        try:
            t = d.get_troop(kind)
        except KeyError:
            raise GameError("چنین نیرویی نیست.") from None
        if qty <= 0:
            raise GameError("تعداد باید بیشتر از صفر باشد.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            level = city.levels.get(t.building, 0)
            if level < t.needs:
                raise GameError(f"برای تربیت {t.name} باید {d.get_building(t.building).name} به سطح {fa(t.needs)} برسد.")
            if len(city.training) >= 5:
                raise GameError("صف آموزش پر است؛ تا تمام شدن یک دسته صبر کنید.")
            if qty > city.recruitable:
                raise GameError(f"مردم کافی برای سربازگیری نیست؛ فقط {fa(city.recruitable)} نفر آماده‌ی خدمت هستند.")
            if city.space_used + qty * t.cap > city.capacity:
                raise GameError(f"ظرفیت ارتش پر می‌شود ({fa(city.space_used)} از {fa(city.capacity)}). ساختمان‌های نظامی را ارتقا دهید.")
            g, f, w, i = t.cost
            self._pay(city, {r: v * qty for r, v in (("gold", g), ("food", f), ("wood", w), ("iron", i)) if v})
            seconds = max(30, round(qty * t.train_seconds / (1 + 0.1 * (level - 1))))
            batch_id = await tx.execute(
                "INSERT INTO city_training (city_id, kind, qty, ready_at) VALUES (?, ?, ?, ?)", (city.id, kind, qty, now + seconds)
            )
            batch = Batch(batch_id, kind, qty, now + seconds)
            city.training.append(batch)
            await self._save(tx, city)
            return city, batch

    async def buy_trap(self, player: Player, kind: str) -> City:
        try:
            trap = d.get_trap(kind)
        except KeyError:
            raise GameError("چنین تله‌ای نیست.") from None
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            if city.castle < 2:
                raise GameError("ساخت تله از قلعه‌ی سطح ۲ ممکن است.")
            have = city.traps.get(kind, 0)
            if have + d.TRAP_BATCH > d.trap_limit(city.castle):
                raise GameError(f"از هر تله تا {fa(d.trap_limit(city.castle))} بار می‌شود نگه داشت؛ قلعه را ارتقا دهید.")
            g, w, s, i = trap.cost
            self._pay(city, {r: v * d.TRAP_BATCH for r, v in (("gold", g), ("wood", w), ("stone", s), ("iron", i)) if v})
            await tx.execute(
                "INSERT INTO city_traps (city_id, kind, qty) VALUES (?, ?, ?)"
                " ON CONFLICT (city_id, kind) DO UPDATE SET qty = qty + excluded.qty",
                (city.id, kind, d.TRAP_BATCH),
            )
            city.traps[kind] = have + d.TRAP_BATCH
            await self._save(tx, city)
            return city

    async def set_alerts(self, player: Player, on: bool) -> City:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            await tx.execute("UPDATE cities SET alerts = ? WHERE id = ?", (int(on), city.id))
            city.alerts = on
            return city

    async def set_flag(self, player: Player, flag: str) -> City:
        if flag not in d.FLAG_EMOJIS:
            raise GameError("این پرچم وجود ندارد.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            await tx.execute("UPDATE cities SET flag = ? WHERE id = ?", (flag, city.id))
            city.flag = flag
            return city

    async def buy_shield(self, player: Player, hours: int) -> City:
        crystals = dict(d.SHIELD_OPTIONS).get(hours)
        if crystals is None:
            raise GameError("این سپر وجود ندارد.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            city = await self._need(tx, player, now)
            await wallet.apply(tx, player.id, crystal=-crystals, reason="city_shield", now=now)
            city.shield_until = max(now, city.shield_until) + hours * 3600
            await self._save(tx, city)
            return city

    # --- finding an enemy ------------------------------------------------------------------------------------
    def _loot_preview(self, target: City, now: int) -> tuple[dict[str, int], int]:
        idle_days = max(0, (now - target.last_active) // DAY)
        factor = 0.25 if idle_days > 7 else 0.5 if idle_days > 3 else 1.0
        return {r: int(target.res[r] * d.LOOT_CAP[r] * factor) for r in d.RES}, idle_days

    async def _search_row(self, tx: Tx, player_id: int) -> Row | None:
        return await tx.fetchone("SELECT * FROM city_search WHERE player_id = ?", (player_id,))

    async def search(self, player: Player) -> Target:
        """Pick a fitting city at random; the one shown last time is not offered again straight away."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            me = await self._need(tx, player, now)
            if me.army == 0:
                raise GameError("بدون سرباز که نمی‌شود لشکرکشی کرد! اول در «ارتش و سربازان» نیرو تربیت کنید.")
            self._count_today(me, now)
            if me.att_count >= d.DAILY_ATTACKS:
                raise GameError(f"سقف حمله‌ی امروز ({fa(d.DAILY_ATTACKS)}) تمام شد؛ فردا دوباره لشکرکشی کنید.")
            row = await self._search_row(tx, player.id)
            seen = json.loads(row["seen"]) if row else []
            mates = [r["player_id"] for r in await tx.fetchall(
                "SELECT m2.player_id FROM clan_members m1 JOIN clan_members m2 ON m2.clan_id = m1.clan_id"
                " WHERE m1.player_id = ?", (player.id,),
            )]
            recent = {r["defender_city"]: r["n"] for r in await tx.fetchall(
                "SELECT defender_city, COUNT(*) AS n FROM city_attacks WHERE attacker_city = ? AND created_at > ?"
                " GROUP BY defender_city", (me.id, now - DAY),
            )}
            ids = [r["id"] for r in await tx.fetchall(
                "SELECT id FROM cities WHERE id != ? AND shield_until <= ? ORDER BY RANDOM() LIMIT 40", (me.id, now)
            )]
            mine_power = max(1, me.army_power + me.defense_power)
            pool: list[tuple[float, City]] = []
            for cid in ids:
                other = await self._by_id(tx, cid)
                if other is None or other.player_id in mates or recent.get(other.id, 0) >= d.SAME_TARGET_PER_DAY:
                    continue
                if abs(other.castle - me.castle) > 4:
                    continue
                ratio = max(1, other.army_power + other.defense_power) / mine_power
                pool.append((abs(math.log(ratio)), other))
            if not pool:
                raise GameError("حریف مناسبی پیدا نشد؛ کمی بعد دوباره جستجو کنید.")
            pool.sort(key=lambda x: x[0])
            fresh = [p for p in pool if p[1].id not in seen[-1:]] or pool
            target = self.ctx.rng.choice([c for _, c in fresh[:5]])
            await self._tick(tx, target, now)
            seen = (seen + [target.id])[-20:]
            snapshot = json.dumps({"city": target.id, **target.snapshot(), "name": target.name})
            await tx.execute(
                "INSERT INTO city_search (player_id, target_id, snapshot, selection, seen, created_at, used)"
                " VALUES (?, ?, ?, '{}', ?, ?, 0)"
                " ON CONFLICT (player_id) DO UPDATE SET target_id = excluded.target_id, snapshot = excluded.snapshot,"
                " selection = '{}', seen = excluded.seen, created_at = excluded.created_at, used = 0",
                (player.id, target.id, snapshot, json.dumps(seen), now),
            )
            await self._save(tx, me)
            loot, idle = self._loot_preview(target, now)
            return Target(target, loot, idle)

    def _count_today(self, city: City, now: int) -> None:
        if city.att_day != day_of(now):
            city.att_day, city.att_count = day_of(now), 0

    async def current_target(self, player: Player) -> tuple[Target, dict[str, int]] | None:
        """The enemy found by the last search and the army picked for it so far."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await self._search_row(tx, player.id)
            if row is None or row["used"]:
                return None
            target = await self._by_id(tx, row["target_id"])
            if target is None:
                return None
            loot, idle = self._loot_preview(target, now)
            return Target(target, loot, idle), json.loads(row["selection"])

    async def adjust(self, player: Player, kind: str | None, delta: int, *, everyone: bool = False, clear: bool = False) -> dict[str, int]:
        """Change the army chosen for the march (nothing is spent until the final confirmation)."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            me = await self._need(tx, player, now)
            row = await self._search_row(tx, player.id)
            if row is None or row["used"]:
                raise GameError("اول یک حریف پیدا کنید.")
            chosen: dict[str, int] = {} if clear or everyone else json.loads(row["selection"])
            if everyone:
                chosen = dict(me.troops)
            elif kind is not None:
                if kind not in me.troops:
                    raise GameError("از این نیرو در شهر ندارید.")
                chosen[kind] = max(0, min(me.troops[kind], chosen.get(kind, 0) + delta))
                if not chosen[kind]:
                    chosen.pop(kind)
            await tx.execute("UPDATE city_search SET selection = ? WHERE player_id = ?", (json.dumps(chosen), player.id))
            return chosen

    # --- the raid ----------------------------------------------------------------------------------------------------
    async def attack(self, player: Player) -> AttackResult:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            me = await self._need(tx, player, now)
            row = await self._search_row(tx, player.id)
            if row is None or row["used"]:
                raise GameError("این حریف دیگر در دسترس نیست؛ دوباره جستجو کنید.")
            sent = {k: v for k, v in json.loads(row["selection"]).items() if v > 0}
            if not sent:
                raise GameError("هنوز سربازی برای لشکرکشی برنگزیده‌اید.")
            for kind, qty in sent.items():
                if me.troops.get(kind, 0) < qty:
                    raise GameError("بعضی نیروها دیگر در شهر نیستند؛ لشکر را دوباره بچینید.")
            self._count_today(me, now)
            if me.att_count >= d.DAILY_ATTACKS:
                raise GameError(f"سقف حمله‌ی امروز ({fa(d.DAILY_ATTACKS)}) تمام شد.")
            target = await self._by_id(tx, row["target_id"])
            if target is None:
                raise GameError("این شهر دیگر وجود ندارد؛ دوباره جستجو کنید.")
            await self._tick(tx, target, now)
            if target.shielded(now):
                raise GameError("شهر دشمن همین حالا سپر دفاعی گرفته است؛ دوباره جستجو کنید.")
            recent = int(await tx.scalar(
                "SELECT COUNT(*) FROM city_attacks WHERE attacker_city = ? AND defender_city = ? AND created_at > ?",
                (me.id, target.id, now - DAY), 0,
            ))
            if recent >= d.SAME_TARGET_PER_DAY:
                raise GameError("امروز بیش از حد به همین شهر حمله کرده‌اید؛ حریف دیگری بجویید.")
            units = sum(sent.values())
            supplies = units * 3
            if me.res["food"] < supplies:
                raise GameError(f"آذوقه‌ی سفر کافی نیست؛ {fa(supplies)} غذا لازم است و {fa(int(me.res['food']))} دارید.")
            snap = json.loads(row["snapshot"])
            defence = siege.Defence(snap["troops"], snap["traps"], snap["levels"], target.name)
            commander = min(0.15, player.level * 0.002)
            out = siege.simulate(
                sent, defence, self.ctx.rng, smithy=me.levels.get("smithy", 0), commander=commander,
                attacker_name=me.name, attacker_hospital=me.levels.get("hospital", 0),
            )
            # --- attacker: troops and supplies
            me.res["food"] -= supplies
            for kind, qty in sent.items():
                me.troops[kind] = me.troops.get(kind, 0) - qty + out.att_alive.get(kind, 0)
                await tx.execute("UPDATE city_troops SET qty = ? WHERE city_id = ? AND kind = ?", (me.troops[kind], me.id, kind))
            # --- loot
            loot = self._take_loot(target, out, now, me)
            # --- defender losses, traps, shield
            for kind, left in out.def_alive.items():
                live = target.troops.get(kind, 0)
                lost = out.def_start.get(kind, 0) - left
                target.troops[kind] = max(0, live - lost)
                await tx.execute("UPDATE city_troops SET qty = ? WHERE city_id = ? AND kind = ?", (target.troops[kind], target.id, kind))
            for kind, used in out.traps_used.items():
                target.traps[kind] = max(0, target.traps.get(kind, 0) - used)
                await tx.execute("UPDATE city_traps SET qty = ? WHERE city_id = ? AND kind = ?", (target.traps[kind], target.id, kind))
            shield = d.shield_for(out.destruction)
            if shield:
                target.shield_until = max(target.shield_until, now + shield)
            # --- trophies
            gain, defender_delta = self._trophies(me, target, out.stars)
            me.trophies = max(0, me.trophies + gain)
            target.trophies = max(0, target.trophies + defender_delta)
            me.att_count += 1
            if not await self._mark_used(tx, player.id, row["created_at"]):
                raise GameError("این حمله پیش‌تر انجام شده است.")
            await self._save(tx, me)
            await self._save(tx, target)
            # --- clan war points and experience for the hero
            xp = out.stars * 40
            if out.stars:
                await clan_repo.add_war_points(tx, player.id, out.stars * 8, now)
            if xp:
                await PlayerService(self.ctx).grant_xp(tx, player.id, xp)
            data = {
                "log": out.log, "sent": sent, "att_lost": out.att_lost, "def_lost": out.def_lost, "loot": loot,
                "destroyed": out.destroyed, "castle": out.castle_down, "traps": out.traps_used,
            }
            attack_id = await tx.execute(
                "INSERT INTO city_attacks (attacker_city, defender_city, attacker_pid, defender_pid, attacker_name,"
                " defender_name, stars, destruction, data, att_trophies, def_trophies, shield, created_at, seen)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (me.id, target.id, me.player_id, target.player_id, me.name, target.name, out.stars, out.destruction,
                 json.dumps(data, ensure_ascii=False), gain, defender_delta, shield, now),
            )
            return AttackResult(
                attack_id, out.stars, out.destruction, loot, sent, out.att_lost, out.log, out.destroyed, out.castle_down,
                gain, shield, target.owner_uid, target.name, me.name, xp, out.def_lost,
            )

    async def _mark_used(self, tx: Tx, player_id: int, created_at: int) -> bool:
        await tx.execute(
            "UPDATE city_search SET used = 1 WHERE player_id = ? AND used = 0 AND created_at = ?", (player_id, created_at)
        )
        return tx.rowcount == 1

    def _take_loot(self, target: City, out: siege.Outcome, now: int, me: City) -> dict[str, int]:
        """Take a limited share of each stock: more when the buildings that make or keep it were destroyed."""
        helper = {"gold": "market", "food": "farm", "wood": "lumber", "stone": "stone_mine", "iron": "iron_mine"}
        preview, _ = self._loot_preview(target, now)
        got: dict[str, int] = {}
        for r in d.RES:
            ratio = min(1.0, out.destruction * 1.2)
            if helper[r] in out.destroyed:
                ratio = min(1.0, ratio + 0.2)
            if "warehouse" in out.destroyed:
                ratio = min(1.0, ratio + 0.1)
            if out.stars == 0:
                ratio *= 0.5
            take = min(int(preview[r] * ratio), int(target.res[r]))
            room = int((me.storage * (2 if r == "gold" else 1)) - me.res[r])
            take = max(0, min(take, room))
            target.res[r] -= take
            me.res[r] += take
            got[r] = take
        return got

    def _trophies(self, me: City, target: City, stars: int) -> tuple[int, int]:
        if stars == 0:
            return -8, 6
        base = {1: 12, 2: 22, 3: 32}[stars]
        diff = max(-8, min(8, (target.trophies - me.trophies) // 50))
        win = max(5, base + diff)
        return win, -round(win * 0.8)

    # --- reports, ranking, map ---------------------------------------------------------------------------------------
    async def unseen_reports(self, player_id: int) -> int:
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar(
                "SELECT COUNT(*) FROM city_attacks WHERE defender_pid = ? AND seen = 0", (player_id,), 0
            ))

    async def reports(self, player: Player, limit: int = 8) -> list[Row]:
        async with self.ctx.db.read() as tx:
            return await tx.fetchall(
                "SELECT * FROM city_attacks WHERE attacker_pid = ? OR defender_pid = ? ORDER BY id DESC LIMIT ?",
                (player.id, player.id, limit),
            )

    async def report(self, player: Player, attack_id: int) -> Row:
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM city_attacks WHERE id = ?", (attack_id,))
            if row is None or player.id not in (row["attacker_pid"], row["defender_pid"]):
                raise GameError("این گزارش پیدا نشد.")
            if row["defender_pid"] == player.id and not row["seen"]:
                await tx.execute("UPDATE city_attacks SET seen = 1 WHERE id = ?", (attack_id,))
            return row

    async def revenge(self, player: Player, attack_id: int) -> Target:
        """Point the next march at the city that raided you."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            me = await self._need(tx, player, now)
            row = await tx.fetchone("SELECT * FROM city_attacks WHERE id = ?", (attack_id,))
            if row is None or row["defender_pid"] != player.id:
                raise GameError("انتقام فقط از حمله‌هایی است که به شهر شما شده.")
            if me.army == 0:
                raise GameError("بدون سرباز که نمی‌شود انتقام گرفت! اول نیرو تربیت کنید.")
            target = await self._by_id(tx, row["attacker_city"])
            if target is None:
                raise GameError("آن شهر دیگر وجود ندارد.")
            if target.shielded(now):
                raise GameError("شهر دشمن سپر دفاعی دارد و هنوز نمی‌شود به آن حمله کرد.")
            self._count_today(me, now)
            if me.att_count >= d.DAILY_ATTACKS:
                raise GameError("سقف حمله‌ی امروز تمام شد.")
            snapshot = json.dumps({"city": target.id, **target.snapshot(), "name": target.name})
            await tx.execute(
                "INSERT INTO city_search (player_id, target_id, snapshot, selection, seen, created_at, used)"
                " VALUES (?, ?, ?, '{}', '[]', ?, 0)"
                " ON CONFLICT (player_id) DO UPDATE SET target_id = excluded.target_id, snapshot = excluded.snapshot,"
                " selection = '{}', created_at = excluded.created_at, used = 0",
                (player.id, target.id, snapshot, now),
            )
            await self._save(tx, me)
            loot, idle = self._loot_preview(target, now)
            return Target(target, loot, idle)

    async def ranking(self, player: Player, limit: int = 10) -> tuple[list[City], int | None, City | None]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT id FROM cities ORDER BY trophies DESC, id LIMIT ?", (limit,))
            top = [c for c in [await self._by_id(tx, r["id"]) for r in rows] if c]
            mine = await self._by_player(tx, player.id)
            rank = None
            if mine is not None:
                rank = 1 + int(await tx.scalar("SELECT COUNT(*) FROM cities WHERE trophies > ?", (mine.trophies,), 0))
        return top, rank, mine

    async def neighbours(self, player: Player, limit: int = 8) -> list[City]:
        """Cities with a strength close to the hero's own (the «world map»)."""
        async with self.ctx.db.read() as tx:
            me = await self._by_player(tx, player.id)
            if me is None:
                return []
            ids = [r["id"] for r in await tx.fetchall("SELECT id FROM cities WHERE id != ? ORDER BY RANDOM() LIMIT 40", (me.id,))]
            cities = [c for c in [await self._by_id(tx, i) for i in ids] if c]
        mine = max(1, me.army_power + me.defense_power)
        cities.sort(key=lambda c: abs(math.log(max(1, c.army_power + c.defense_power) / mine)))
        return cities[:limit]

    async def city_count(self) -> int:
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT COUNT(*) FROM cities", (), 0))
