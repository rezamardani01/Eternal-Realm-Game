"""Operator tools. Every action is written to ``admin_log``."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import groups as group_repo
from ...db.repos import orders as order_repo
from ...db.repos import players as player_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.items import Item
from ..engine import progression
from ..models import Player
from .inventory import InventoryService


@dataclass
class Stats:
    players: int
    groups: int
    active_duels: int
    orders: int
    revenue_rial: int
    gold_in_circulation: int


class AdminService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    async def _log(self, tx, admin_id: int, action: str, detail: str) -> None:  # noqa: ANN001
        await tx.execute(
            "INSERT INTO admin_log (admin_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (admin_id, action, detail, self.ctx.now()),
        )

    async def _find(self, tx, name: str) -> Player:  # noqa: ANN001
        player = await player_repo.get_by_name(tx, name.strip())
        if player is None:
            raise GameError(f"بازیکنی با نام «{name.strip()}» پیدا نشد.")
        return player

    async def stats(self) -> Stats:
        async with self.ctx.db.read() as tx:
            order_row = await order_repo.stats(tx)
            return Stats(
                players=await player_repo.count(tx),
                groups=await group_repo.count_groups(tx),
                active_duels=int(await tx.scalar("SELECT COUNT(*) FROM duels WHERE status = 'active'", default=0)),
                orders=int(order_row["delivered"]) if order_row else 0,
                revenue_rial=int(order_row["revenue"]) if order_row else 0,
                gold_in_circulation=int(await tx.scalar("SELECT SUM(gold) FROM players", default=0)),
            )

    async def give_currency(self, admin_id: int, name: str, *, gold: int = 0, crystal: int = 0) -> Player:
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await wallet.apply(tx, player.id, gold=gold, crystal=crystal, reason="admin", now=self.ctx.now())
            await self._log(tx, admin_id, "give_currency", f"{player.name} gold={gold} crystal={crystal}")
            return player

    async def give_item(self, admin_id: int, name: str, item: Item, qty: int) -> Player:
        if not 1 <= qty <= 1000:
            raise GameError("تعداد باید بین ۱ تا ۱۰۰۰ باشد.")
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await self.inventory.grant(tx, player.id, item.id, qty)
            await self._log(tx, admin_id, "give_item", f"{player.name} {item.id} x{qty}")
            return player

    async def set_ban(self, admin_id: int, name: str, banned: bool) -> Player:
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await player_repo.set_banned(tx, player.id, banned)
            await self._log(tx, admin_id, "ban" if banned else "unban", player.name)
            return player

    async def set_level(self, admin_id: int, name: str, level: int) -> Player:
        if not 1 <= level <= self.ctx.balance.max_level:
            raise GameError(f"سطح باید بین ۱ تا {self.ctx.balance.max_level} باشد.")
        async with self.ctx.db.transaction() as tx:
            player = await self._find(tx, name)
            await player_repo.set_progress(tx, player.id, level, 0)
            await player_repo.set_energy(tx, player.id, progression.max_energy(level, self.ctx.balance), self.ctx.now())
            await self._log(tx, admin_id, "set_level", f"{player.name} -> {level}")
            return player

    async def group_ids(self) -> list[int]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall("SELECT chat_id FROM groups WHERE enabled = 1")
        return [r["chat_id"] for r in rows]

    async def log_action(self, admin_id: int, action: str, detail: str = "") -> None:
        async with self.ctx.db.transaction() as tx:
            await self._log(tx, admin_id, action, detail)

    # --- grants and removals by player id (used by the owner's reply commands and the web panel) -----------
    async def _by_id(self, tx, player_id: int) -> Player:  # noqa: ANN001
        player = await player_repo.get(tx, player_id)
        if player is None:
            raise GameError("بازیکن پیدا نشد.")
        return player

    async def grant_ticket(self, admin_id: int, player_id: int, give: bool = True) -> bool:
        """Give (or take back) this season's golden ticket. Returns whether anything changed."""
        from ...db.repos import season as season_repo
        from ..data.season import season_of

        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            player = await self._by_id(tx, player_id)
            if give:
                changed = await season_repo.grant_ticket(tx, player.id, now)
            else:
                await tx.execute(
                    "UPDATE season_progress SET premium = 0 WHERE player_id = ? AND season = ? AND premium = 1",
                    (player.id, season_of(now)),
                )
                changed = tx.rowcount == 1
            await self._log(tx, admin_id, "grant_ticket" if give else "revoke_ticket", f"{player.name} changed={changed}")
            return changed

    async def set_vip(self, admin_id: int, player_id: int, days: int) -> int:
        """Add ``days`` of VIP (negative removes that much; ``0`` days with ``clear`` is done by passing -3650)."""
        if not -3650 <= days <= 3650:
            raise GameError("تعداد روز باید بین ۳٬۶۵۰- تا ۳٬۶۵۰ باشد.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            player = await self._by_id(tx, player_id)
            base = max(player.vip_until, now)
            until = base + days * 86400
            until = 0 if until <= now else until
            await tx.execute("UPDATE players SET vip_until = ? WHERE id = ?", (until, player.id))
            await self._log(tx, admin_id, "set_vip", f"{player.name} days={days} until={until}")
            return until

    async def grant_pet(self, admin_id: int, player_id: int, pet_id: str, give: bool = True) -> bool:
        from ..data.pets import PETS
        from .pets import PetService

        if pet_id not in {p.id for p in PETS}:
            raise GameError("این حیوان خانگی وجود ندارد.")
        async with self.ctx.db.transaction() as tx:
            player = await self._by_id(tx, player_id)
            if give:
                changed = await PetService(self.ctx).grant(tx, player.id, pet_id)
            else:
                await tx.execute("DELETE FROM player_pets WHERE player_id = ? AND pet_id = ?", (player.id, pet_id))
                changed = tx.rowcount == 1
                left = await tx.fetchone("SELECT pet_id FROM player_pets WHERE player_id = ? LIMIT 1", (player.id,))
                if left is not None:
                    await tx.execute(
                        "UPDATE player_pets SET active = 1 WHERE player_id = ? AND pet_id = ?"
                        " AND NOT EXISTS (SELECT 1 FROM player_pets WHERE player_id = ? AND active = 1)",
                        (player.id, left["pet_id"], player.id),
                    )
            await self._log(tx, admin_id, "grant_pet" if give else "revoke_pet", f"{player.name} {pet_id} changed={changed}")
            return changed

    async def give_currency_id(self, admin_id: int, player_id: int, *, gold: int = 0, crystal: int = 0) -> Player:
        async with self.ctx.db.transaction() as tx:
            player = await self._by_id(tx, player_id)
            await wallet.apply(tx, player.id, gold=gold, crystal=crystal, reason="admin", now=self.ctx.now())
            await self._log(tx, admin_id, "give_currency", f"{player.name} gold={gold} crystal={crystal}")
            return player

    async def set_title(self, admin_id: int, player_id: int, title: str) -> None:
        title = title.strip()[:40]
        async with self.ctx.db.transaction() as tx:
            player = await self._by_id(tx, player_id)
            await tx.execute("UPDATE players SET title = ? WHERE id = ?", (title, player.id))
            await self._log(tx, admin_id, "set_title", f"{player.name} -> {title or '(none)'}")

    async def refill_energy(self, admin_id: int, player_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            player = await self._by_id(tx, player_id)
            await player_repo.set_energy(tx, player.id, progression.max_energy(player.level, self.ctx.balance), self.ctx.now())
            await self._log(tx, admin_id, "refill_energy", player.name)

    async def reset_cooldowns(self, admin_id: int, player_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            player = await self._by_id(tx, player_id)
            await tx.execute("DELETE FROM cooldowns WHERE player_id = ?", (player.id,))
            await tx.execute("DELETE FROM activity_usage WHERE player_id = ?", (player.id,))
            await self._log(tx, admin_id, "reset_cooldowns", player.name)

    async def set_group_enabled(self, admin_id: int, chat_id: int, enabled: bool) -> None:
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT title FROM groups WHERE chat_id = ?", (chat_id,))
            if row is None:
                raise GameError("گروه پیدا نشد.")
            await group_repo.set_enabled(tx, chat_id, enabled)
            await self._log(tx, admin_id, "group_on" if enabled else "group_off", row["title"] or str(chat_id))
