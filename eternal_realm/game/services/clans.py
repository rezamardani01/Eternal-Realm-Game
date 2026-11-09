"""Clans (خاندان): a named band of players with ranks, a shared treasury and a level."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import clan_wars as war_repo
from ...db.repos import clans as repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...db.repos.wallet import DuplicateOperation
from ...shared.errors import GameError
from ...shared.text import fa, normalize
from ..data.khan_shop import WAR_BOOST_HOURS, WAR_CRYSTALS, WAR_POINTS, Offer, day_of, get_offer, offers_for
from ..models import Player
from .inventory import InventoryService

NAME_MIN, NAME_MAX = 3, 16
#: role id -> (emoji, title, power); a higher power outranks a lower one
ROLES: dict[str, tuple[str, str, int]] = {
    "leader": ("👑", "مالک", 3),
    "deputy": ("🛡️", "قائم‌مقام", 2),
    "elder": ("🔰", "پیشکسوت", 1),
    "member": ("👤", "عضو", 0),
}
DONATION_STEPS = (100, 500, 1_000, 5_000)


def role_power(role: str) -> int:
    return ROLES[role][2]


def level_for(donated: int) -> int:
    """Clan level grows with everything its members ever gave: 1000 -> 2, 4000 -> 3, 9000 -> 4..."""
    level = 1
    while donated >= 1000 * level * level:
        level += 1
    return level


def capacity_for(level: int) -> int:
    return min(40, 8 + 4 * (level - 1))


@dataclass
class ClanView:
    id: int
    name: str
    leader_id: int
    leader: str
    leader_mention: str
    open: bool
    treasury: int
    donated: int
    size: int
    power: int
    level: int
    capacity: int
    my_role: str | None = None
    #: the clan's picture (a Bale file id), empty when it has none
    photo: str = ""
    #: gold a member pays the clan to leave (0 = none)
    exit_fine: int = 0
    #: the lowest level that may join
    min_level: int = 1


def clean_clan_name(raw: str) -> str:
    name = normalize(raw)
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise GameError(
            f"نام خاندان باید بین {fa(NAME_MIN)} تا {fa(NAME_MAX)} حرف باشد. مثال: «ساخت خاندان شیرهای شمال»"
        )
    if any(ch in name for ch in "[]()*_`\n"):
        raise GameError("در نام خاندان نشانه‌های ویژه نگذارید؛ فقط حرف، عدد و فاصله.")
    return name


WAR_PRIZES = (800, 500, 300)


@dataclass
class WarStanding:
    name: str
    points: int
    mine: bool


@dataclass
class WarView:
    week_rows: list[WarStanding]
    seconds_left: int
    #: gold the player's clan won last week and the player can still collect (0 = nothing)
    prize: int = 0
    last_place: int = 0


class ClanService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    # --- reading --------------------------------------------------------------------------------
    async def _view(self, tx: Tx, row: Row, my_role: str | None = None) -> ClanView:
        size = await repo.count_members(tx, row["id"])
        lead = await player_repo.get(tx, row["leader_id"])
        power = int(
            await tx.scalar(
                "SELECT COALESCE(SUM(p.level), 0) FROM clan_members m JOIN players p ON p.id = m.player_id"
                " WHERE m.clan_id = ?",
                (row["id"],),
                0,
            )
        )
        level = level_for(row["donated"])
        return ClanView(
            row["id"], row["name"], row["leader_id"], lead.name if lead else "-", lead.mention if lead else "-", bool(row["open"]),
            row["treasury"], row["donated"], size, power, level, capacity_for(level), my_role,
            row["photo"], row["exit_fine"], row["min_level"],
        )

    async def of(self, player_id: int) -> ClanView | None:
        async with self.ctx.db.read() as tx:
            member = await repo.membership(tx, player_id)
            if member is None:
                return None
            row = await repo.get(tx, member["clan_id"])
            assert row is not None
            return await self._view(tx, row, member["role"])

    async def get(self, clan_id: int) -> ClanView | None:
        async with self.ctx.db.read() as tx:
            row = await repo.get(tx, clan_id)
            return await self._view(tx, row) if row else None

    async def members(self, clan_id: int) -> list[Row]:
        async with self.ctx.db.read() as tx:
            return await repo.members(tx, clan_id)

    async def listing(self, page: int, per: int = 6) -> tuple[list[ClanView], bool]:
        async with self.ctx.db.read() as tx:
            rows = await repo.listing(tx, per + 1, page * per)
            views = [await self._view(tx, r) for r in rows[:per]]
        return views, len(rows) > per

    # --- helpers --------------------------------------------------------------------------------
    async def _mine(self, tx: Tx, player_id: int) -> tuple[Row, Row]:
        member = await repo.membership(tx, player_id)
        if member is None:
            raise GameError("شما عضو هیچ خاندانی نیستید. «خاندان» را بنویسید و یکی را بسازید یا به یکی بپیوندید.")
        clan = await repo.get(tx, member["clan_id"])
        assert clan is not None
        return member, clan

    async def _target(self, tx: Tx, actor: Row, target_id: int) -> Row:
        target = await repo.membership(tx, target_id)
        if target is None or target["clan_id"] != actor["clan_id"]:
            raise GameError("این فرمانده دیگر عضو خاندان شما نیست.")
        return target

    # --- joining and leaving ---------------------------------------------------------------------
    async def create(self, player: Player, raw_name: str) -> ClanView:
        name = clean_clan_name(raw_name)
        price, now = self.ctx.balance.clan_create_gold, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            if await repo.membership(tx, player.id):
                raise GameError("شما همین حالا عضو یک خاندان هستید. اول از آن خارج شوید.")
            if await repo.by_name(tx, name):
                raise GameError(f"خاندانی به نام «{name}» از قبل هست. یک نام تازه انتخاب کنید.")
            await wallet.apply(tx, player.id, gold=-price, reason="clan_create", now=now)
            clan_id = await repo.create(tx, name, player.id, now)
            row = await repo.get(tx, clan_id)
            assert row is not None
            return await self._view(tx, row, "leader")

    async def join(self, player: Player, clan_id: int, *, invited: bool = False) -> ClanView:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            if await repo.membership(tx, player.id):
                raise GameError("شما همین حالا عضو یک خاندان هستید. اول از آن خارج شوید.")
            row = await repo.get(tx, clan_id)
            if row is None:
                raise GameError("این خاندان دیگر وجود ندارد.")
            if not row["open"] and not invited:
                raise GameError("درهای این خاندان بسته است؛ فقط با دعوت مالک یا قائم‌مقام می‌شود وارد شد.")
            level = int(await tx.scalar("SELECT level FROM players WHERE id = ?", (player.id,), player.level))
            if level < row["min_level"]:
                raise GameError(
                    f"این خاندان فقط قهرمان‌های سطح {fa(row['min_level'])} به بالا را می‌پذیرد؛ شما سطح {fa(level)} هستید. "
                    "کمی قوی‌تر شوید و برگردید!"
                )
            view = await self._view(tx, row)
            if view.size >= view.capacity:
                raise GameError(
                    f"خاندان پر است ({fa(view.size)} از {fa(view.capacity)}). "
                    "با پر شدن خزانه، سطح خاندان بالا می‌رود و جای تازه باز می‌شود."
                )
            await repo.add_member(tx, player.id, clan_id, "member", now)
            return await self._view(tx, row, "member")

    async def leave(self, player: Player) -> str:
        """Returns ``left`` or ``disbanded`` (the leader of a one-person clan closes it). A member pays the clan's fine."""
        async with self.ctx.db.transaction() as tx:
            member, clan = await self._mine(tx, player.id)
            if member["role"] == "leader":
                if await repo.count_members(tx, clan["id"]) > 1:
                    raise GameError(
                        "شما مالک هستید و نمی‌توانید خاندان را وسط راه رها کنید. "
                        "اول مالکیت را به یکی از اعضا بدهید (از بخش اعضا)."
                    )
                await self._close(tx, clan["id"])
                return "disbanded"
            fine = clan["exit_fine"]
            if fine:
                await wallet.apply(tx, player.id, gold=-fine, reason="clan_fine", now=self.ctx.now())
                await tx.execute("UPDATE clans SET treasury = treasury + ? WHERE id = ?", (fine, clan["id"]))
            await repo.remove_member(tx, player.id)
            return "left"

    async def disband(self, player: Player) -> None:
        async with self.ctx.db.transaction() as tx:
            member, clan = await self._mine(tx, player.id)
            if member["role"] != "leader":
                raise GameError("فقط مالک می‌تواند خاندان را منحل کند.")
            await self._close(tx, clan["id"])

    @staticmethod
    async def _close(tx: Tx, clan_id: int) -> None:
        """Delete a clan; never in the middle of a war (an unanswered challenge is withdrawn)."""
        if not await war_repo.release_clan(tx, clan_id):
            raise GameError("خاندان وسط جنگ است؛ تا پایان جنگ نمی‌شود آن را بست.")
        await repo.delete(tx, clan_id)

    # --- managing --------------------------------------------------------------------------------
    async def kick(self, actor: Player, target_id: int) -> str:
        async with self.ctx.db.transaction() as tx:
            me, _ = await self._mine(tx, actor.id)
            target = await self._target(tx, me, target_id)
            if role_power(me["role"]) < 2:
                raise GameError("اخراج اعضا کار مالک و قائم‌مقام است.")
            if role_power(target["role"]) >= role_power(me["role"]):
                raise GameError("نمی‌توانید کسی را که هم‌مقام یا بالاتر از شماست اخراج کنید.")
            await repo.remove_member(tx, target_id)
            gone = await player_repo.get(tx, target_id)
            return gone.name if gone else "-"

    async def set_role(self, actor: Player, target_id: int, role: str) -> str:
        if role not in ROLES or role == "leader":
            raise GameError("این مقام وجود ندارد.")
        async with self.ctx.db.transaction() as tx:
            me, _ = await self._mine(tx, actor.id)
            target = await self._target(tx, me, target_id)
            mine = role_power(me["role"])
            if mine < 2:
                raise GameError("مقام دادن کار مالک و قائم‌مقام است.")
            if role_power(target["role"]) >= mine or role_power(role) >= mine:
                raise GameError(
                    "شما فقط می‌توانید به مقام‌های پایین‌تر از خودتان مقام بدهید. قائم‌مقامت دادن فقط با مالک است."
                )
            await repo.set_role(tx, target_id, role)
        return ROLES[role][1]

    async def transfer(self, actor: Player, target_id: int) -> str:
        async with self.ctx.db.transaction() as tx:
            me, clan = await self._mine(tx, actor.id)
            target = await self._target(tx, me, target_id)
            if me["role"] != "leader":
                raise GameError("فقط مالک می‌تواند مالکیت را به دیگری بدهد.")
            if target_id == actor.id:
                raise GameError("شما همین حالا مالک خاندان هستید.")
            await repo.set_role(tx, target_id, "leader")
            await repo.set_role(tx, actor.id, "deputy")
            await repo.set_leader(tx, clan["id"], target["player_id"])
            new = await player_repo.get(tx, target_id)
            return new.name if new else "-"

    async def set_open(self, actor: Player, value: bool) -> None:
        async with self.ctx.db.transaction() as tx:
            me, clan = await self._mine(tx, actor.id)
            if role_power(me["role"]) < 2:
                raise GameError("باز و بسته کردن درِ خاندان کار مالک و قائم‌مقام است.")
            await repo.set_open(tx, clan["id"], value)

    # --- the leader's settings -------------------------------------------------------------------
    async def _as_leader(self, tx: Tx, actor: Player) -> Row:
        member, clan = await self._mine(tx, actor.id)
        if member["role"] != "leader":
            raise GameError("این تنظیم فقط دست مالک خاندان است.")
        return clan

    async def set_fine(self, actor: Player, amount: int) -> int:
        limit = self.ctx.balance.clan_fine_max
        amount = max(0, min(limit, amount))
        async with self.ctx.db.transaction() as tx:
            clan = await self._as_leader(tx, actor)
            await tx.execute("UPDATE clans SET exit_fine = ? WHERE id = ?", (amount, clan["id"]))
        return amount

    async def set_min_level(self, actor: Player, level: int) -> int:
        level = max(1, min(self.ctx.balance.clan_min_level_max, level))
        async with self.ctx.db.transaction() as tx:
            clan = await self._as_leader(tx, actor)
            await tx.execute("UPDATE clans SET min_level = ? WHERE id = ?", (level, clan["id"]))
        return level

    async def set_photo(self, actor: Player, file_id: str) -> int:
        """Put (or replace) the clan picture; it costs gold every time. Returns the price paid."""
        if not file_id:
            raise GameError("عکسی دریافت نشد؛ دوباره بفرستید.")
        price = self.ctx.balance.clan_photo_gold
        async with self.ctx.db.transaction() as tx:
            clan = await self._as_leader(tx, actor)
            await wallet.apply(tx, actor.id, gold=-price, reason="clan_photo", now=self.ctx.now())
            await tx.execute("UPDATE clans SET photo = ? WHERE id = ?", (file_id, clan["id"]))
        return price

    async def remove_photo(self, actor: Player) -> None:
        async with self.ctx.db.transaction() as tx:
            clan = await self._as_leader(tx, actor)
            if not clan["photo"]:
                raise GameError("خاندان شما عکسی ندارد.")
            await tx.execute("UPDATE clans SET photo = '' WHERE id = ?", (clan["id"],))

    # --- the clan shop (Khan points) -------------------------------------------------------------
    async def khan_points(self, player_id: int) -> int:
        async with self.ctx.db.read() as tx:
            return int(await tx.scalar("SELECT khan_points FROM players WHERE id = ?", (player_id,), 0))

    async def shop(self, player: Player) -> tuple[list[tuple[Offer, bool]], int]:
        """Today's goods with a «bought already» flag, and the player's Khan points."""
        day = day_of(self.ctx.now())
        async with self.ctx.db.read() as tx:
            if await repo.membership(tx, player.id) is None:
                raise GameError("فروشگاه خاندان مخصوص اعضای خاندان است.")
            bought = {
                r["offer"] for r in await tx.fetchall(
                    "SELECT offer FROM khan_purchases WHERE player_id = ? AND day = ?", (player.id, day)
                )
            }
            points = int(await tx.scalar("SELECT khan_points FROM players WHERE id = ?", (player.id,), 0))
        return [(o, o.id in bought) for o in offers_for(day)], points

    async def buy(self, player: Player, offer_id: str) -> Offer:
        day = day_of(self.ctx.now())
        try:
            offer = get_offer(offer_id)
        except KeyError:
            raise GameError("این کالا وجود ندارد.") from None
        if offer not in offers_for(day):
            raise GameError("این کالا امروز در فروشگاه نیست؛ فهرست را تازه کنید.")
        async with self.ctx.db.transaction() as tx:
            if await repo.membership(tx, player.id) is None:
                raise GameError("فروشگاه خاندان مخصوص اعضای خاندان است.")
            await tx.execute(
                "INSERT OR IGNORE INTO khan_purchases (player_id, day, offer) VALUES (?, ?, ?)", (player.id, day, offer.id)
            )
            if tx.rowcount == 0:
                raise GameError("این کالا را امروز خریده‌اید؛ فردا موجود می‌شود یا کالای دیگری بیاید.")
            await tx.execute(
                "UPDATE players SET khan_points = khan_points - ? WHERE id = ? AND khan_points >= ?",
                (offer.price, player.id, offer.price),
            )
            if tx.rowcount == 0:
                have = int(await tx.scalar("SELECT khan_points FROM players WHERE id = ?", (player.id,), 0))
                raise GameError(f"خان‌پوینت کافی نیست؛ {fa(offer.price)} لازم است و شما {fa(have)} دارید.")
            if offer.kind == "item":
                await self.inventory.grant(tx, player.id, offer.ref, offer.qty, origin="khan_shop")
            else:
                await wallet.apply(
                    tx, player.id, gold=offer.qty if offer.kind == "gold" else 0,
                    crystal=offer.qty if offer.kind == "crystal" else 0, reason="khan_shop", now=self.ctx.now(),
                )
        return offer

    async def donate(self, player: Player, amount: int) -> ClanView:
        if amount <= 0:
            raise GameError("مقدار کمک باید بیشتر از صفر باشد.")
        async with self.ctx.db.transaction() as tx:
            member, clan = await self._mine(tx, player.id)
            await wallet.apply(tx, player.id, gold=-amount, reason="clan_donate", now=self.ctx.now())
            await repo.donate(tx, clan["id"], player.id, amount)
            fresh = await repo.get(tx, clan["id"])
            assert fresh is not None
            return await self._view(tx, fresh, member["role"])

    async def war(self, player: Player) -> WarView:
        now = self.ctx.now()
        week = repo.week_of(now)
        async with self.ctx.db.read() as tx:
            member = await repo.membership(tx, player.id)
            mine = member["clan_id"] if member else None
            rows = await repo.war_board(tx, week, 10)
            last = await repo.war_board(tx, week - 1, 3)
        standings = [WarStanding(r["name"], r["points"], r["clan_id"] == mine) for r in rows]
        left = (week + 1) * repo.WEEK - (now + 12600 + 2 * 86400)
        prize = place = 0
        if member is not None and member["joined_at"] < week * repo.WEEK - 12600 - 2 * 86400:
            for index, r in enumerate(last):
                if r["clan_id"] == mine:
                    place, prize = index + 1, WAR_PRIZES[index]
        view = WarView(standings, left, prize, place)
        if prize:
            async with self.ctx.db.read() as tx:
                done = await tx.fetchone("SELECT 1 FROM transactions WHERE ref = ?", (f"clanwar:{week - 1}:{player.id}",))
            if done:
                view.prize = 0
        return view

    async def claim_war(self, player: Player) -> int:
        view = await self.war(player)
        if not view.prize:
            raise GameError("جایزه‌ای برای گرفتن نیست. خاندان شما هفته‌ی پیش در سه‌ی اول نبود، یا جایزه را گرفته‌اید.")
        week = repo.week_of(self.ctx.now())
        try:
            async with self.ctx.db.transaction() as tx:
                await wallet.apply(
                    tx, player.id, gold=view.prize, reason="clan_war_prize", now=self.ctx.now(),
                    ref=f"clanwar:{week - 1}:{player.id}",
                )
                await tx.execute(
                    "UPDATE players SET khan_points = khan_points + ? WHERE id = ?",
                    (WAR_POINTS[view.last_place - 1], player.id),
                )
                await wallet.apply(
                    tx, player.id, crystal=WAR_CRYSTALS[view.last_place - 1], reason="clan_war_crystals",
                    now=self.ctx.now(), ref=f"clanwar:{week - 1}:{player.id}:crystal",
                )
                await tx.execute(
                    "UPDATE players SET boost_until = MAX(boost_until, ?) + ? WHERE id = ?",
                    (self.ctx.now(), WAR_BOOST_HOURS * 3600, player.id),
                )
        except DuplicateOperation as exc:
            raise GameError("این جایزه را قبلاً گرفته‌اید.") from exc
        return view.prize
