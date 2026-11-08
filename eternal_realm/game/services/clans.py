"""Clans (خاندان): a named band of players with ranks, a shared treasury and a level."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import clans as repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...db.repos.wallet import DuplicateOperation
from ...shared.errors import GameError
from ...shared.text import fa, normalize
from ..models import Player

NAME_MIN, NAME_MAX = 3, 16
#: role id -> (emoji, title, power); a higher power outranks a lower one
ROLES: dict[str, tuple[str, str, int]] = {
    "leader": ("👑", "رهبر", 3),
    "deputy": ("🛡️", "معاون", 2),
    "elder": ("🔰", "ریش‌سفید", 1),
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
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

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
                raise GameError("درهای این خاندان بسته است؛ فقط با دعوت رهبر یا معاون می‌شود وارد شد.")
            view = await self._view(tx, row)
            if view.size >= view.capacity:
                raise GameError(
                    f"خاندان پر است ({fa(view.size)} از {fa(view.capacity)}). "
                    "با پر شدن خزانه، سطح خاندان بالا می‌رود و جای تازه باز می‌شود."
                )
            await repo.add_member(tx, player.id, clan_id, "member", now)
            return await self._view(tx, row, "member")

    async def leave(self, player: Player) -> str:
        """Returns ``left`` or ``disbanded`` (the leader of a one-person clan closes it)."""
        async with self.ctx.db.transaction() as tx:
            member, clan = await self._mine(tx, player.id)
            if member["role"] == "leader":
                if await repo.count_members(tx, clan["id"]) > 1:
                    raise GameError(
                        "شما رهبر هستید و نمی‌توانید خاندان را وسط راه رها کنید. "
                        "اول رهبری را به یکی از اعضا بدهید (از بخش اعضا)."
                    )
                await repo.delete(tx, clan["id"])
                return "disbanded"
            await repo.remove_member(tx, player.id)
            return "left"

    async def disband(self, player: Player) -> None:
        async with self.ctx.db.transaction() as tx:
            member, clan = await self._mine(tx, player.id)
            if member["role"] != "leader":
                raise GameError("فقط رهبر می‌تواند خاندان را منحل کند.")
            await repo.delete(tx, clan["id"])

    # --- managing --------------------------------------------------------------------------------
    async def kick(self, actor: Player, target_id: int) -> str:
        async with self.ctx.db.transaction() as tx:
            me, _ = await self._mine(tx, actor.id)
            target = await self._target(tx, me, target_id)
            if role_power(me["role"]) < 2:
                raise GameError("اخراج اعضا کار رهبر و معاون است.")
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
                raise GameError("مقام دادن کار رهبر و معاون است.")
            if role_power(target["role"]) >= mine or role_power(role) >= mine:
                raise GameError(
                    "شما فقط می‌توانید به مقام‌های پایین‌تر از خودتان مقام بدهید. معاونت دادن فقط با رهبر است."
                )
            await repo.set_role(tx, target_id, role)
        return ROLES[role][1]

    async def transfer(self, actor: Player, target_id: int) -> str:
        async with self.ctx.db.transaction() as tx:
            me, clan = await self._mine(tx, actor.id)
            target = await self._target(tx, me, target_id)
            if me["role"] != "leader":
                raise GameError("فقط رهبر می‌تواند رهبری را به دیگری بدهد.")
            await repo.set_role(tx, target_id, "leader")
            await repo.set_role(tx, actor.id, "deputy")
            await repo.set_leader(tx, clan["id"], target["player_id"])
            new = await player_repo.get(tx, target_id)
            return new.name if new else "-"

    async def set_open(self, actor: Player, value: bool) -> None:
        async with self.ctx.db.transaction() as tx:
            me, clan = await self._mine(tx, actor.id)
            if role_power(me["role"]) < 2:
                raise GameError("باز و بسته کردن درِ خاندان کار رهبر و معاون است.")
            await repo.set_open(tx, clan["id"], value)

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
        except DuplicateOperation as exc:
            raise GameError("این جایزه را قبلاً گرفته‌اید.") from exc
        return view.prize
