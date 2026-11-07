"""Bale groups the bot plays in: registration, per-group switches and activity points."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.repos import groups as repo


@dataclass(frozen=True)
class GroupInfo:
    chat_id: int
    title: str
    enabled: bool
    disabled_commands: frozenset[str]


class GroupService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def touch(self, chat_id: int, title: str | None) -> GroupInfo:
        """Register the group on first sight and return its current switches."""
        async with self.ctx.db.transaction() as tx:
            await repo.touch(tx, chat_id, title or "", self.ctx.now())
            row = await repo.get(tx, chat_id)
        assert row is not None
        return _info(row)

    async def get(self, chat_id: int) -> GroupInfo | None:
        async with self.ctx.db.read() as tx:
            row = await repo.get(tx, chat_id)
        return _info(row) if row else None

    async def set_enabled(self, chat_id: int, enabled: bool) -> None:
        async with self.ctx.db.transaction() as tx:
            await repo.set_enabled(tx, chat_id, enabled)

    async def set_command(self, chat_id: int, name: str, enabled: bool) -> None:
        async with self.ctx.db.transaction() as tx:
            row = await repo.get(tx, chat_id)
            if row is None:
                return
            names = set(_info(row).disabled_commands)
            names.discard(name) if enabled else names.add(name)
            await repo.set_disabled_commands(tx, chat_id, names)

    async def add_points(self, chat_id: int, player_id: int, points: int = 1) -> None:
        async with self.ctx.db.transaction() as tx:
            await repo.add_points(tx, chat_id, player_id, points, self.ctx.now())

    async def top(self, chat_id: int, limit: int = 10):  # noqa: ANN201
        async with self.ctx.db.read() as tx:
            return await repo.top_members(tx, chat_id, limit)


def _info(row) -> GroupInfo:  # noqa: ANN001
    disabled = frozenset(n for n in row["disabled_cmds"].split(",") if n)
    return GroupInfo(row["chat_id"], row["title"], bool(row["enabled"]), disabled)
