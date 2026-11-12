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
class Withdrawal:
    """A member's request for gold out of the clan treasury."""

    id: int
    clan_id: int
    clan_name: str
    player_id: int
    player_name: str
    player_level: int
    #: Bale ids to message: the member who asked and the clan's owner
    member_user_id: int
    leader_user_id: int
    amount: int
    status: str
    created_at: int
    treasury: int = 0
    #: the owner's own withdrawal: no one to ask, paid at once
    instant: bool = False
    #: the member left the clan before the answer, so nothing was paid
    left: bool = False


#: how long a withdrawal request waits for the owner's answer before it lapses
WITHDRAW_TTL = 3 * 86400


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

    # --- withdrawals from the treasury: a member asks, the owner answers ---------------------------------------
    _WITHDRAWAL_SQL = (
        "SELECT w.id, w.clan_id, w.player_id, w.amount, w.status, w.created_at, c.name AS clan_name, c.treasury AS treasury,"
        " p.display_name AS pname, p.level AS plevel, p.platform_user_id AS puid,"
        " (SELECT pl.platform_user_id FROM clan_members m JOIN players pl ON pl.id = m.player_id"
        "  WHERE m.clan_id = w.clan_id AND m.role = 'leader') AS luid"
        " FROM clan_withdrawals w JOIN clans c ON c.id = w.clan_id JOIN players p ON p.id = w.player_id"
    )

    @staticmethod
    def _as_withdrawal(row: Row, **extra: bool) -> Withdrawal:
        return Withdrawal(
            row["id"], row["clan_id"], row["clan_name"], row["player_id"], row["pname"], row["plevel"], row["puid"],
            row["luid"] or 0, row["amount"], row["status"], row["created_at"], row["treasury"], **extra,
        )

    async def _withdrawal(self, tx: Tx, withdrawal_id: int, **extra: bool) -> Withdrawal | None:
        row = await tx.fetchone(self._WITHDRAWAL_SQL + " WHERE w.id = ?", (withdrawal_id,))
        return self._as_withdrawal(row, **extra) if row else None

    async def withdrawal(self, withdrawal_id: int) -> Withdrawal | None:
        async with self.ctx.db.read() as tx:
            return await self._withdrawal(tx, withdrawal_id)

    async def my_withdrawal(self, player: Player) -> Withdrawal | None:
        """The member's open request, if the owner has not answered it yet."""
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone(
                self._WITHDRAWAL_SQL + " WHERE w.player_id = ? AND w.status = 'pending' AND w.created_at > ?"
                " ORDER BY w.id DESC LIMIT 1", (player.id, self.ctx.now() - WITHDRAW_TTL),
            )
            return self._as_withdrawal(row) if row else None

    async def pending_withdrawals(self, leader: Player) -> list[Withdrawal]:
        """The requests waiting for this clan's owner (those of members who left, or that lapsed, are not shown)."""
        async with self.ctx.db.read() as tx:
            member = await repo.membership(tx, leader.id)
            if member is None or member["role"] != "leader":
                return []
            rows = await tx.fetchall(
                self._WITHDRAWAL_SQL + " JOIN clan_members cm ON cm.player_id = w.player_id AND cm.clan_id = w.clan_id"
                " WHERE w.clan_id = ? AND w.status = 'pending' AND w.created_at > ? ORDER BY w.id",
                (member["clan_id"], self.ctx.now() - WITHDRAW_TTL),
            )
            return [self._as_withdrawal(r) for r in rows]

    async def request_withdrawal(self, player: Player, amount: int) -> Withdrawal:
        """Ask the owner for ``amount`` gold from the treasury (the owner's own request is paid at once)."""
        if amount <= 0:
            raise GameError("مقدار برداشت باید بیشتر از صفر باشد.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            member, clan = await self._mine(tx, player.id)
            if amount > clan["treasury"]:
                raise GameError(f"خزانه‌ی خاندان فقط {fa(clan['treasury'])} سکه دارد؛ مقدار کمتری بنویسید.")
            leader = member["role"] == "leader"
            if not leader and await tx.scalar(
                "SELECT 1 FROM clan_withdrawals WHERE player_id = ? AND clan_id = ? AND status = 'pending' AND created_at > ?",
                (player.id, clan["id"], now - WITHDRAW_TTL), 0,
            ):
                raise GameError("یک درخواست برداشت بی‌پاسخ دارید؛ منتظر جواب مالک بمانید یا آن را لغو کنید.")
            withdrawal_id = await tx.execute(
                "INSERT INTO clan_withdrawals (clan_id, player_id, amount, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                (clan["id"], player.id, amount, now),
            )
            if leader:
                await self._pay_withdrawal(tx, withdrawal_id, now)
            made = await self._withdrawal(tx, withdrawal_id, instant=leader)
            assert made is not None
            return made

    async def _pay_withdrawal(self, tx: Tx, withdrawal_id: int, now: int) -> None:
        """Approve a pending request: the status flip is the gate that makes it pay exactly once."""
        row = await tx.fetchone("SELECT clan_id, player_id, amount FROM clan_withdrawals WHERE id = ?", (withdrawal_id,))
        assert row is not None
        await tx.execute(
            "UPDATE clan_withdrawals SET status = 'approved', decided_at = ? WHERE id = ? AND status = 'pending'", (now, withdrawal_id)
        )
        if tx.rowcount != 1:
            raise GameError("این درخواست قبلاً جواب داده شده است.")
        await tx.execute(
            "UPDATE clans SET treasury = treasury - ? WHERE id = ? AND treasury >= ?", (row["amount"], row["clan_id"], row["amount"])
        )
        if tx.rowcount != 1:  # the treasury was spent meanwhile: nothing changes (the transaction is undone)
            clan = await repo.get(tx, row["clan_id"])
            have = clan["treasury"] if clan else 0
            raise GameError(f"خزانه‌ی خاندان الان فقط {fa(have)} سکه دارد؛ برای این برداشت کافی نیست.")
        await wallet.apply(tx, row["player_id"], gold=row["amount"], reason="clan_withdraw", now=now, ref=f"clanwd:{withdrawal_id}")

    async def decide_withdrawal(self, actor: Player, withdrawal_id: int, approve: bool) -> Withdrawal:
        """The owner's answer. Approved: gold leaves the treasury and reaches the member. Rejected: nothing moves."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            made = await self._withdrawal(tx, withdrawal_id)
            if made is None:
                raise GameError("این درخواست پیدا نشد.")
            member, clan = await self._mine(tx, actor.id)
            if member["role"] != "leader" or clan["id"] != made.clan_id:
                raise GameError("فقط مالک این خاندان می‌تواند به درخواست برداشت جواب بدهد.")
            if made.status != "pending":
                raise GameError("این درخواست قبلاً جواب داده شده است.")
            if now - made.created_at > WITHDRAW_TTL:
                raise GameError("این درخواست قدیمی شده و دیگر معتبر نیست؛ از عضو بخواهید دوباره بنویسد.")
            asker = await repo.membership(tx, made.player_id)
            if asker is None or asker["clan_id"] != made.clan_id:  # left the clan since: nothing to pay
                await tx.execute("UPDATE clan_withdrawals SET status = 'cancelled', decided_at = ? WHERE id = ?", (now, withdrawal_id))
                gone = await self._withdrawal(tx, withdrawal_id, left=True)
                assert gone is not None
                return gone
            if approve:
                await self._pay_withdrawal(tx, withdrawal_id, now)
            else:
                await tx.execute("UPDATE clan_withdrawals SET status = 'rejected', decided_at = ? WHERE id = ?", (now, withdrawal_id))
            done = await self._withdrawal(tx, withdrawal_id)
            assert done is not None
            return done

    async def cancel_withdrawal(self, player: Player, withdrawal_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "UPDATE clan_withdrawals SET status = 'cancelled', decided_at = ? WHERE id = ? AND player_id = ? AND status = 'pending'",
                (self.ctx.now(), withdrawal_id, player.id),
            )
            if tx.rowcount != 1:
                raise GameError("درخواست بی‌پاسخی برای لغو کردن نیست.")

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
