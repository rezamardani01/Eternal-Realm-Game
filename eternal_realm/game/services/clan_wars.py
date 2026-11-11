"""Wars between two clans (جنگ خاندان‌ها).

A leader or deputy challenges another clan and puts gold from the treasury on the table; the other side matches it
or declines. While the war runs every member has a few attacks: each one is an automatic fight against a member of
the enemy clan and conquers 0 to 3 stars of their keep. A clan's score is the best result on every enemy keep; when
the time is up the higher score takes the whole pot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Row, Tx
from ...db.repos import clan_wars as repo
from ...db.repos import clans as clan_repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import bold, duration, fa
from .. import notify
from ..engine import combat
from ..engine.combat import Battle, Fighter
from ..models import Player
from .characters import CharacterService
from .clans import capacity_for, level_for, role_power
from .inventory import InventoryService
from .pets import PetService
from .players import LevelUp, PlayerService

#: gold a clan may put on a war (taken from its treasury; the winner takes both stakes)
STAKES = (0, 500, 2_000, 5_000)
#: Khan points for everybody who fought, by how the war ended for their clan
KHAN_WIN, KHAN_DRAW, KHAN_LOSE = 15, 8, 5
#: points in the weekly clan league: per conquered star, and for winning the war
LEAGUE_STAR_POINTS, LEAGUE_WIN_POINTS = 4, 60
#: what the best fighter of the winning clan receives
HERO_PRIZE = "magic_chest"
MAX_STARS = 3


def stars_for(won: bool, hp_ratio: float) -> int:
    """A win is worth more the less it cost: 60% of the hit points left = 3 stars, 30% = 2, any win = 1."""
    if not won:
        return 0
    return 3 if hp_ratio >= 0.6 else 2 if hp_ratio >= 0.3 else 1


def star_text(stars: int) -> str:
    return "⭐" * stars + "☆" * (MAX_STARS - stars)


def score_of(attacks: list[Row], clan_id: int) -> int:
    """A clan's stars: the best attack on every enemy keep."""
    best: dict[int, int] = {}
    for a in attacks:
        if a["clan_id"] == clan_id:
            best[a["target_id"]] = max(best.get(a["target_id"], 0), a["stars"])
    return sum(best.values())


@dataclass
class Side:
    clan_id: int
    name: str
    stars: int = 0
    #: attacks made, and how many the whole clan has
    used: int = 0
    total: int = 0
    size: int = 0


@dataclass
class WarView:
    id: int
    #: pending, active, done
    status: str
    stake: int
    mine: Side
    enemy: Side
    seconds_left: int
    #: a challenge that waits for *our* answer
    incoming: bool = False
    #: the reader fights in this war, and how many attacks they still have
    fighter: bool = False
    attacks_left: int = 0
    #: for a finished war: won, lost or draw
    result: str = ""


@dataclass
class Hub:
    clan_id: int
    clan_name: str
    treasury: int
    can_manage: bool
    war: WarView | None
    last: WarView | None
    #: wins, losses, draws
    record: tuple[int, int, int]


@dataclass
class Rival:
    id: int
    name: str
    level: int
    size: int
    capacity: int
    power: int
    #: why this clan cannot be challenged right now ("" = it can)
    blocked: str = ""


@dataclass
class Target:
    player_id: int
    name: str
    level: int
    #: stars our clan already holds on this keep, and the reader's own attack on it (None = not attacked yet)
    best: int = 0
    mine: int | None = None


@dataclass
class Champion:
    name: str
    ours: bool
    stars: int
    attacks: int


@dataclass
class AttackResult:
    war: WarView
    attacker: str
    target: str
    stars: int
    won: bool
    draw: bool
    #: stars this attack added to the clan's score
    gained: int
    gold: int
    xp: int
    level_up: LevelUp | None
    hp: tuple[int, int] = (0, 1)
    foe_hp: tuple[int, int] = (0, 1)
    log: list[str] = field(default_factory=list)
    #: the war ended with this attack
    finished: bool = False


class ClanWarService:
    def __init__(
        self, ctx: AppContext, players: PlayerService, characters: CharacterService, inventory: InventoryService
    ) -> None:
        self.ctx = ctx
        self.players = players
        self.characters = characters
        self.inventory = inventory

    # --- helpers --------------------------------------------------------------------------------
    async def _mine(self, tx: Tx, player_id: int) -> tuple[Row, Row]:
        member = await clan_repo.membership(tx, player_id)
        if member is None:
            raise GameError("جنگ خاندان‌ها مخصوص اعضای خاندان است. «خاندان» را بنویسید و یکی بسازید یا به یکی بپیوندید.")
        clan = await clan_repo.get(tx, member["clan_id"])
        assert clan is not None
        return member, clan

    @staticmethod
    def _manager(member: Row) -> None:
        if role_power(member["role"]) < 2:
            raise GameError("اعلام جنگ و پاسخ به آن فقط کار مالک و قائم‌مقام است.")

    async def _managers(self, tx: Tx, clan_id: int) -> list[int]:
        return [m["player_id"] for m in await clan_repo.members(tx, clan_id) if role_power(m["role"]) >= 2]

    async def _everyone(self, tx: Tx, clan_id: int) -> list[int]:
        return [m["player_id"] for m in await clan_repo.members(tx, clan_id)]

    async def _view(self, tx: Tx, war: Row, clan_id: int, member: Row | None, now: int) -> WarView:
        ours_attacking = war["attacker_id"] == clan_id
        mine = Side(clan_id, war["attacker_name"] if ours_attacking else war["defender_name"])
        enemy = (
            Side(war["defender_id"], war["defender_name"]) if ours_attacking
            else Side(war["attacker_id"], war["attacker_name"])
        )
        view = WarView(
            war["id"], war["status"], war["stake"], mine, enemy, max(0, war["ends_at"] - now),
            incoming=war["status"] == "pending" and not ours_attacking,
        )
        if war["status"] == "pending":
            return view
        attacks = await repo.attacks(tx, war["id"])
        per = self.ctx.balance.clan_war_attacks
        for side in (mine, enemy):
            side.stars = score_of(attacks, side.clan_id)
            side.used = sum(1 for a in attacks if a["clan_id"] == side.clan_id)
            side.size = len(await repo.roster(tx, side.clan_id, war["starts_at"]))
            side.total = side.size * per
        if war["status"] == "active" and member is not None and member["joined_at"] <= war["starts_at"]:
            view.fighter = True
            view.attacks_left = max(0, per - sum(1 for a in attacks if a["attacker_id"] == member["player_id"]))
        if war["status"] == "done":
            view.result = "draw" if not war["winner_id"] else "won" if war["winner_id"] == clan_id else "lost"
        return view

    # --- endings --------------------------------------------------------------------------------
    async def sweep(self) -> None:
        """Close what is overdue: unanswered challenges and wars whose time is up (the notifier calls this)."""
        async with self.ctx.db.transaction() as tx:
            await self._sweep(tx, self.ctx.now())

    async def _sweep(self, tx: Tx, now: int) -> None:
        for war in await repo.due(tx, now):
            if war["status"] == "pending":
                await self._expire(tx, war, now)
            else:
                await self._settle(tx, war, now)

    async def _expire(self, tx: Tx, war: Row, now: int) -> None:
        if not await repo.close(tx, war["id"], "pending", "expired"):
            return
        await repo.pay_treasury(tx, war["attacker_id"], war["stake"])
        text = (
            f"⌛ {bold('اعلام جنگ بی‌پاسخ ماند')}\n\n"
            f"خاندان {war['defender_name']} به شیپور جنگ شما پاسخی نداد."
            + (f"\n🪙 {fa(war['stake'])} سکه‌ی گرو به خزانه برگشت." if war["stake"] else "")
        )
        for pid in await self._managers(tx, war["attacker_id"]):
            await notify.queue(tx, pid, f"cwar:{war['id']}:expired", text, now, "cwar")

    async def _settle(self, tx: Tx, war: Row, now: int, early: bool = False) -> None:
        attacks = await repo.attacks(tx, war["id"])
        sides = (war["attacker_id"], war["defender_id"])
        names = {war["attacker_id"]: war["attacker_name"], war["defender_id"]: war["defender_name"]}
        score = {cid: score_of(attacks, cid) for cid in sides}
        a, d = sides
        winner = a if score[a] > score[d] else d if score[d] > score[a] else 0
        if not await repo.close(tx, war["id"], "active", "done", winner, now if early else None):
            return
        b, stake = self.ctx.balance, war["stake"]
        if winner:
            await repo.pay_treasury(tx, winner, 2 * stake)
            await clan_repo.add_clan_points(tx, winner, LEAGUE_WIN_POINTS, now)
        else:
            for cid in sides:
                await repo.pay_treasury(tx, cid, stake)

        # everybody who drew a sword is paid; the best fighter of the winning clan gets the hero's chest
        tally: dict[int, tuple[int, int, str]] = {}  # player -> (clan, stars, name)
        for at in attacks:
            _, stars, _ = tally.get(at["attacker_id"], (0, 0, ""))
            tally[at["attacker_id"]] = (at["clan_id"], stars + at["stars"], at["attacker_name"])
        hero_id = max(
            (pid for pid, (cid, _, _) in tally.items() if cid == winner), key=lambda pid: tally[pid][1], default=None
        )
        draw_gold = (b.clan_war_win_gold + b.clan_war_lose_gold) // 2

        def share(cid: int) -> tuple[int, int]:
            return (
                (draw_gold, KHAN_DRAW) if not winner
                else (b.clan_war_win_gold, KHAN_WIN) if cid == winner else (b.clan_war_lose_gold, KHAN_LOSE)
            )

        # nothing is paid yet: every member of both clans finds a prize waiting behind the button of the result message
        # (those who fought get all of it, those who only stood behind the walls a quarter)
        prizes: dict[int, tuple[int, int, int, str, int]] = {}  # player -> (clan, gold, khan, chest, fought)
        for cid in sides:
            gold, khan = share(cid)
            for member in await repo.roster(tx, cid, war["starts_at"]):
                prizes[member["player_id"]] = (cid, gold // 4, khan // 4, "", 0)
        for pid, (cid, _, _) in tally.items():
            gold, khan = share(cid)
            prizes[pid] = (cid, gold, khan, HERO_PRIZE if pid == hero_id else "", 1)
        for pid, (cid, gold, khan, chest, fought) in prizes.items():
            if await player_repo.get(tx, pid) is None:
                continue
            await tx.execute(
                "INSERT OR IGNORE INTO clan_war_rewards (war_id, player_id, clan_id, gold, khan, chest, fought) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (war["id"], pid, cid, gold, khan, chest, fought),
            )

        hero_line = f"\n🏅 قهرمان جنگ: {tally[hero_id][2]} (یک صندوقچه جادویی گرفت)" if hero_id is not None else ""
        for cid in sides:
            other = d if cid == a else a
            board = f"⭐ {names[cid]}: {fa(score[cid])} ستاره\n⭐ {names[other]}: {fa(score[other])} ستاره"
            if not winner:
                text = (
                    f"🤝 {bold('جنگ خاندان‌ها مساوی شد')}\n\n{board}\n\n"
                    "هیچ پرچمی پایین نیامد."
                    + (f" 🪙 {fa(stake)} سکه‌ی گرو به خزانه برگشت." if stake else "")
                    + f"\n🎖️ جنگاوران: {fa(draw_gold)} سکه و {fa(KHAN_DRAW)} خان‌پوینت (بقیه‌ی اعضا یک‌چهارم)"
                )
            elif cid == winner:
                text = (
                    f"🏆 {bold('پیروزی در جنگ خاندان‌ها')}\n\n{board}\n\n"
                    f"پرچم خاندان {names[cid]} بر فراز دژ {names[other]} برافراشته شد!"
                    + (f"\n🪙 {fa(2 * stake)} سکه به خزانه رسید." if stake else "")
                    + f"\n🎖️ جنگاوران: {fa(b.clan_war_win_gold)} سکه و {fa(KHAN_WIN)} خان‌پوینت"
                    + hero_line
                )
            else:
                text = (
                    f"💔 {bold('شکست در جنگ خاندان‌ها')}\n\n{board}\n\n"
                    f"این بار خاندان {names[other]} دست بالا را داشت؛ زخم‌ها را ببندید و برای انتقام آماده شوید."
                    + (f"\n🪙 {fa(stake)} سکه‌ی گرو از دست رفت." if stake else "")
                    + f"\n🎖️ جنگاوران: {fa(b.clan_war_lose_gold)} سکه و {fa(KHAN_LOSE)} خان‌پوینت"
                )
            text += "\n\n🎁 جایزه‌ی هر عضو آماده است؛ دکمه‌ی زیر را بزنید."
            for pid in await self._everyone(tx, cid):
                has_prize = pid in prizes
                await notify.queue(
                    tx, pid, f"cwar:{war['id']}:end", text, now, "cwarclaim" if has_prize else "cwar", str(war["id"]) if has_prize else "",
                )

    async def claim_reward(self, player: Player, war_id: int) -> tuple[int, int, str]:
        """Collect the prize of a finished war once. Returns (gold, khan points, chest item id or '')."""
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM clan_war_rewards WHERE war_id = ? AND player_id = ?", (war_id, player.id))
            if row is None:
                raise GameError("برای شما در این جنگ جایزه‌ای نیست.")
            if row["claimed"]:
                raise GameError("جایزه‌ی این جنگ را قبلاً گرفته‌اید.")
            await tx.execute("UPDATE clan_war_rewards SET claimed = 1 WHERE war_id = ? AND player_id = ?", (war_id, player.id))
            if row["gold"]:
                await wallet.apply(tx, player.id, gold=row["gold"], reason="clan_war", now=now, ref=f"cwar:{war_id}:{player.id}")
            if row["khan"]:
                await tx.execute("UPDATE players SET khan_points = khan_points + ? WHERE id = ?", (row["khan"], player.id))
            if row["chest"]:
                await self.inventory.grant(tx, player.id, row["chest"], 1, origin="clan_war")
            return int(row["gold"]), int(row["khan"]), row["chest"]

    async def reward_status(self, player_id: int, war_id: int) -> Row | None:
        async with self.ctx.db.read() as tx:
            return await tx.fetchone("SELECT * FROM clan_war_rewards WHERE war_id = ? AND player_id = ?", (war_id, player_id))

    # --- reading --------------------------------------------------------------------------------
    async def hub(self, player: Player) -> Hub:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await self._sweep(tx, now)
            member, clan = await self._mine(tx, player.id)
            war = await repo.open_for(tx, clan["id"])
            past = await repo.history(tx, clan["id"], 1)
            return Hub(
                clan["id"], clan["name"], clan["treasury"], role_power(member["role"]) >= 2,
                await self._view(tx, war, clan["id"], member, now) if war else None,
                await self._view(tx, past[0], clan["id"], member, now) if past else None,
                await repo.record(tx, clan["id"]),
            )

    async def history(self, player: Player, limit: int = 8) -> list[WarView]:
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            member, clan = await self._mine(tx, player.id)
            return [await self._view(tx, w, clan["id"], member, now) for w in await repo.history(tx, clan["id"], limit)]

    async def _block_reason(self, tx: Tx, mine: Row, other: Row, busy: set[int], now: int) -> str:
        b = self.ctx.balance
        if other["id"] in busy:
            return "درگیر جنگی دیگر است"
        if await clan_repo.count_members(tx, other["id"]) < b.clan_war_min_members:
            return f"کمتر از {fa(b.clan_war_min_members)} عضو دارد"
        truce = await repo.last_between(tx, mine["id"], other["id"]) + b.clan_war_truce_hours * 3600 - now
        if truce > 0:
            return f"آتش‌بس تا {duration(truce)} دیگر"
        return ""

    async def rivals(self, player: Player, page: int, per: int = 6) -> tuple[list[Rival], bool]:
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            _, clan = await self._mine(tx, player.id)
            rows = [r for r in await clan_repo.listing(tx, 500, 0) if r["id"] != clan["id"]]
            busy = await repo.busy_ids(tx)
            out = []
            for r in rows[page * per : (page + 1) * per]:
                level = level_for(r["donated"])
                power = int(
                    await tx.scalar(
                        "SELECT COALESCE(SUM(p.level), 0) FROM clan_members m JOIN players p ON p.id = m.player_id"
                        " WHERE m.clan_id = ?",
                        (r["id"],),
                        0,
                    )
                )
                out.append(
                    Rival(
                        r["id"], r["name"], level, await clan_repo.count_members(tx, r["id"]), capacity_for(level),
                        power, await self._block_reason(tx, clan, r, busy, now),
                    )
                )
        return out, (page + 1) * per < len(rows)

    async def rival(self, player: Player, clan_id: int) -> tuple[Rival, int]:
        """One clan as a possible enemy, and the reader's own treasury."""
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            _, clan = await self._mine(tx, player.id)
            r = await clan_repo.get(tx, clan_id)
            if r is None or r["id"] == clan["id"]:
                raise GameError("این خاندان دیگر وجود ندارد.")
            level = level_for(r["donated"])
            reason = await self._block_reason(tx, clan, r, await repo.busy_ids(tx), now)
            size = await clan_repo.count_members(tx, r["id"])
            return Rival(r["id"], r["name"], level, size, capacity_for(level), 0, reason), clan["treasury"]

    # --- declaring and answering ----------------------------------------------------------------
    async def declare(self, player: Player, clan_id: int, stake: int) -> WarView:
        if stake not in STAKES:
            raise GameError("این مبلغ گرو مجاز نیست؛ دوباره از منو انتخاب کنید.")
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await self._sweep(tx, now)
            member, clan = await self._mine(tx, player.id)
            self._manager(member)
            other = await clan_repo.get(tx, clan_id)
            if other is None or other["id"] == clan["id"]:
                raise GameError("این خاندان دیگر وجود ندارد.")
            if await repo.open_for(tx, clan["id"]):
                raise GameError("خاندان شما همین حالا درگیر یک جنگ یا اعلام جنگ است؛ اول آن را به پایان برسانید.")
            if await clan_repo.count_members(tx, clan["id"]) < b.clan_war_min_members:
                raise GameError(f"برای جنگ دست‌کم {fa(b.clan_war_min_members)} عضو لازم است؛ اول یار جمع کنید.")
            reason = await self._block_reason(tx, clan, other, await repo.busy_ids(tx), now)
            if reason:
                raise GameError(f"به خاندان {other['name']} نمی‌شود اعلام جنگ کرد: {reason}.")
            if not await repo.take_treasury(tx, clan["id"], stake):
                raise GameError(
                    f"خزانه‌ی خاندان برای این گرو کافی نیست؛ {fa(stake)} سکه لازم است و خزانه {fa(clan['treasury'])} سکه دارد."
                )
            war_id = await repo.create(tx, clan, other, stake, now, now + b.clan_war_accept_hours * 3600)
            text = (
                f"📯 {bold('شیپور جنگ به صدا درآمد')}\n\n"
                f"خاندان {clan['name']} به خاندان شما اعلام جنگ کرده است.\n"
                f"🪙 گرو: {f'{fa(stake)} سکه از خزانه‌ی هر خاندان' if stake else 'بدون گرو؛ فقط برای افتخار'}\n"
                f"⏳ مهلت پاسخ: {duration(b.clan_war_accept_hours * 3600)}"
            )
            for pid in await self._managers(tx, other["id"]):
                await notify.queue(tx, pid, f"cwar:{war_id}:declared", text, now, "cwar")
            war = await repo.get(tx, war_id)
            assert war is not None
            return await self._view(tx, war, clan["id"], member, now)

    async def answer(self, player: Player, war_id: int, accept: bool) -> WarView | None:
        """The challenged clan accepts (the war starts at once) or declines; returns the running war, or None."""
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await self._sweep(tx, now)
            member, clan = await self._mine(tx, player.id)
            self._manager(member)
            war = await repo.get(tx, war_id)
            if war is None or war["status"] != "pending" or war["defender_id"] != clan["id"]:
                raise GameError("این اعلام جنگ دیگر معتبر نیست؛ پاسخ داده شده، پس گرفته شده یا مهلتش گذشته است.")
            if not accept:
                await repo.close(tx, war_id, "pending", "declined")
                await repo.pay_treasury(tx, war["attacker_id"], war["stake"])
                text = (
                    f"🕊️ {bold('اعلام جنگ رد شد')}\n\nخاندان {clan['name']} از نبرد با شما سر باز زد."
                    + (f"\n🪙 {fa(war['stake'])} سکه‌ی گرو به خزانه برگشت." if war["stake"] else "")
                )
                for pid in await self._managers(tx, war["attacker_id"]):
                    await notify.queue(tx, pid, f"cwar:{war_id}:declined", text, now, "cwar")
                return None
            for cid in (war["attacker_id"], war["defender_id"]):
                if await clan_repo.count_members(tx, cid) < b.clan_war_min_members:
                    raise GameError(f"هر دو خاندان باید دست‌کم {fa(b.clan_war_min_members)} عضو داشته باشند.")
            if not await repo.take_treasury(tx, clan["id"], war["stake"]):
                raise GameError(
                    f"برای پذیرفتن باید {fa(war['stake'])} سکه گرو بگذارید ولی خزانه {fa(clan['treasury'])} سکه دارد. "
                    "اعضا می‌توانند به خزانه کمک کنند."
                )
            await repo.begin(tx, war_id, now, now + b.clan_war_hours * 3600)
            for cid, foe in ((war["attacker_id"], war["defender_name"]), (war["defender_id"], war["attacker_name"])):
                text = (
                    f"⚔️ {bold('جنگ خاندان‌ها آغاز شد')}\n\n"
                    f"خاندان شما با خاندان {foe} وارد جنگ شد.\n"
                    f"🗡️ هر جنگاور {fa(b.clan_war_attacks)} حمله دارد و هر حمله تا {fa(MAX_STARS)} ستاره می‌آورد.\n"
                    f"⏳ زمان جنگ: {duration(b.clan_war_hours * 3600)}"
                )
                for pid in await self._everyone(tx, cid):
                    await notify.queue(tx, pid, f"cwar:{war_id}:start", text, now, "cwar")
            fresh = await repo.get(tx, war_id)
            assert fresh is not None
            member = await clan_repo.membership(tx, player.id)
            return await self._view(tx, fresh, clan["id"], member, now)

    async def withdraw(self, player: Player, war_id: int) -> None:
        """The challenger takes an unanswered challenge back."""
        async with self.ctx.db.transaction() as tx:
            member, clan = await self._mine(tx, player.id)
            self._manager(member)
            war = await repo.get(tx, war_id)
            if war is None or war["attacker_id"] != clan["id"] or not await repo.close(tx, war_id, "pending", "cancelled"):
                raise GameError("این اعلام جنگ دیگر قابل پس گرفتن نیست.")
            await repo.pay_treasury(tx, clan["id"], war["stake"])

    # --- fighting -------------------------------------------------------------------------------
    async def _active(self, tx: Tx, player_id: int, now: int) -> tuple[Row, Row, Row]:
        member, clan = await self._mine(tx, player_id)
        war = await repo.open_for(tx, clan["id"])
        if war is None or war["status"] != "active":
            raise GameError("خاندان شما الان در جنگ نیست.")
        return member, clan, war

    async def targets(self, player: Player) -> tuple[WarView, list[Target]]:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await self._sweep(tx, now)
            member, clan, war = await self._active(tx, player.id, now)
            view = await self._view(tx, war, clan["id"], member, now)
            attacks = [a for a in await repo.attacks(tx, war["id"]) if a["clan_id"] == clan["id"]]
            out = []
            for m in await repo.roster(tx, view.enemy.clan_id, war["starts_at"]):
                on = [a for a in attacks if a["target_id"] == m["player_id"]]
                own = next((a["stars"] for a in on if a["attacker_id"] == player.id), None)
                out.append(Target(m["player_id"], m["name"], m["level"], max((a["stars"] for a in on), default=0), own))
        return view, out

    async def _fighter(self, tx: Tx, p: Player) -> Fighter:
        stats = await self.characters.stats_in(tx, p)
        fighter = Fighter.for_player(p.id, p.name, p.char_class, stats, p.mention)
        striker = await PetService(self.ctx).striker_in(tx, p.id, stats.atk)
        if striker:
            fighter.pet_emoji, fighter.pet_name, fighter.pet_power = striker
        return fighter

    async def attack(self, player: Player, target_id: int) -> AttackResult:
        b, now = self.ctx.balance, self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            await self._sweep(tx, now)
            member, clan, war = await self._active(tx, player.id, now)
            if member["joined_at"] > war["starts_at"]:
                raise GameError("شما پس از آغاز این جنگ به خاندان پیوسته‌اید؛ در جنگ بعدی شمشیر می‌زنید.")
            enemy_id = war["defender_id"] if war["attacker_id"] == clan["id"] else war["attacker_id"]
            foe_member = await clan_repo.membership(tx, target_id)
            if foe_member is None or foe_member["clan_id"] != enemy_id or foe_member["joined_at"] > war["starts_at"]:
                raise GameError("این جنگاور دیگر در سپاه دشمن نیست؛ هدف دیگری انتخاب کنید.")
            attacks = await repo.attacks(tx, war["id"])
            own = [a for a in attacks if a["attacker_id"] == player.id]
            if len(own) >= b.clan_war_attacks:
                raise GameError(f"هر {fa(b.clan_war_attacks)} حمله‌ی خود را در این جنگ زده‌اید. حالا نوبت هم‌رزمانتان است!")
            if any(a["target_id"] == target_id for a in own):
                raise GameError("به این دژ یک بار حمله کرده‌اید؛ هدف دیگری انتخاب کنید.")
            before = score_of(attacks, clan["id"])
            held = max((a["stars"] for a in attacks if a["clan_id"] == clan["id"] and a["target_id"] == target_id), default=0)
            if held >= MAX_STARS:
                raise GameError("این دژ را هم‌رزمانتان کامل فتح کرده‌اند؛ حمله‌تان را خرج دژ دیگری کنید.")
            left = await player_repo.is_away(tx, player.id, now)
            if left:
                raise player_repo.away_error(left, None)

            me, foe = await player_repo.get(tx, player.id), await player_repo.get(tx, target_id)
            assert me is not None and foe is not None
            mine, theirs = await self._fighter(tx, me), await self._fighter(tx, foe)
            combat.level_field([[mine], [theirs]])
            battle = Battle.start(mine, theirs, b.clan_war_max_rounds, self.ctx.rng)
            log = combat.auto_fight(battle, self.ctx.rng)
            won = battle.winner == 0
            stars = stars_for(won, mine.hp_ratio)
            await repo.add_attack(tx, war["id"], clan["id"], me.id, me.name, foe.id, foe.name, stars, now)

            gold = stars * b.clan_war_star_gold
            xp = stars * b.clan_war_star_xp if stars else b.clan_war_star_xp // 4
            if gold:
                await wallet.apply(tx, me.id, gold=gold, reason="clan_war_attack", now=now)
            level_up = await self.players.grant_xp(tx, me.id, xp)
            await clan_repo.add_clan_points(tx, clan["id"], stars * LEAGUE_STAR_POINTS, now)

            # when every sword on both sides has struck there is nothing left to wait for
            attacks = await repo.attacks(tx, war["id"])
            per, finished = b.clan_war_attacks, True
            for cid in (war["attacker_id"], war["defender_id"]):
                roster = await repo.roster(tx, cid, war["starts_at"])
                done = sum(1 for a in attacks if a["clan_id"] == cid)
                finished = finished and done >= len(roster) * per
            if finished:
                await self._settle(tx, war, now, early=True)
            fresh = await repo.get(tx, war["id"])
            assert fresh is not None
            view = await self._view(tx, fresh, clan["id"], member, now)
            return AttackResult(
                view, me.name, foe.name, stars, won, battle.winner is None, score_of(attacks, clan["id"]) - before,
                gold, xp, level_up, (max(0, mine.hp), mine.max_hp), (max(0, theirs.hp), theirs.max_hp), log, finished,
            )

    async def champions(self, player: Player) -> tuple[WarView | None, list[Champion]]:
        """The fighters of the running war (or the last one), best first."""
        now = self.ctx.now()
        async with self.ctx.db.read() as tx:
            member, clan = await self._mine(tx, player.id)
            war = await repo.open_for(tx, clan["id"])
            if war is None or war["status"] != "active":
                past = await repo.history(tx, clan["id"], 1)
                war = past[0] if past else None
            if war is None:
                return None, []
            tally: dict[int, Champion] = {}
            for a in await repo.attacks(tx, war["id"]):
                one = tally.setdefault(a["attacker_id"], Champion(a["attacker_name"], a["clan_id"] == clan["id"], 0, 0))
                one.stars += a["stars"]
                one.attacks += 1
            view = await self._view(tx, war, clan["id"], member, now)
        return view, sorted(tally.values(), key=lambda c: (-c.stars, c.attacks))
