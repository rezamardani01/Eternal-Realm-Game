"""Story quests: where each player stands in each tale, and the once-only rewards at its end."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ..data.quests import QUESTS, Choice, Quest, Reward, Step, get_quest
from ..models import Player
from .inventory import InventoryService
from .players import PlayerService


@dataclass
class QuestView:
    quest: Quest
    step_id: str
    step: Step
    flags: set[str]
    done: bool
    #: (index in the step, choice) for every choice the player may take now
    options: list[tuple[int, Choice]] = field(default_factory=list)
    reward: Reward | None = None
    level_up: int | None = None


class QuestService:
    def __init__(self, ctx: AppContext, players: PlayerService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory

    async def _row(self, tx, player_id: int, quest_id: str):  # noqa: ANN001, ANN202
        return await tx.fetchone(
            "SELECT step, flags, done FROM player_quests WHERE player_id = ? AND quest_id = ?", (player_id, quest_id)
        )

    @staticmethod
    def _build(quest: Quest, step_id: str, flags: set[str], done: bool) -> QuestView:
        step = quest.steps[step_id]
        options = [(i, c) for i, c in enumerate(step.choices) if not c.requires or c.requires in flags]
        return QuestView(quest, step_id, step, flags, done, options)

    async def status(self, player: Player) -> list[tuple[Quest, str]]:
        """Every quest with ``new`` / ``running`` / ``done`` / ``locked``."""
        out = []
        async with self.ctx.db.read() as tx:
            for quest in QUESTS:
                row = await self._row(tx, player.id, quest.id)
                if player.level < quest.level_req:
                    out.append((quest, "locked"))
                elif row is None:
                    out.append((quest, "new"))
                else:
                    out.append((quest, "done" if row["done"] else "running"))
        return out

    async def view(self, player: Player, quest_id: str) -> QuestView:
        quest = get_quest(quest_id)
        if player.level < quest.level_req:
            raise GameError(f"این داستان از سطح {quest.level_req} باز می‌شود. شما سطح {player.level} هستید؛ کمی ماجراجویی کنید!")
        async with self.ctx.db.read() as tx:
            row = await self._row(tx, player.id, quest_id)
        if row is None:
            return self._build(quest, "start", set(), False)
        return self._build(quest, row["step"], set(filter(None, row["flags"].split(","))), bool(row["done"]))

    async def choose(self, player: Player, quest_id: str, index: int) -> QuestView:
        quest = get_quest(quest_id)
        if player.level < quest.level_req:
            raise GameError("این داستان هنوز برای شما باز نشده است.")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await self._row(tx, player.id, quest_id)
            if row is not None and row["done"]:
                raise GameError("این داستان را تا پایان رفته‌اید. هر داستان یک بار پاداش می‌دهد.")
            step_id = row["step"] if row else "start"
            flags = set(filter(None, row["flags"].split(","))) if row else set()
            step = quest.steps[step_id]
            if not 0 <= index < len(step.choices):
                raise GameError("این گزینه دیگر وجود ندارد؛ داستان را دوباره باز کنید.")
            choice = step.choices[index]
            if choice.requires and choice.requires not in flags:
                raise GameError("این راه برای شما بسته است؛ در مراحل قبل چیزی را که لازم بود به دست نیاوردید.")
            if choice.flag:
                flags.add(choice.flag)
            nxt = quest.steps[choice.next]
            done = nxt.reward is not None
            await tx.execute(
                "INSERT INTO player_quests (player_id, quest_id, step, flags, done, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (player_id, quest_id) DO UPDATE SET step = excluded.step, flags = excluded.flags,"
                " done = excluded.done, updated_at = excluded.updated_at",
                (player.id, quest_id, choice.next, ",".join(sorted(flags)), int(done), now),
            )
            view = self._build(quest, choice.next, flags, done)
            if nxt.reward is not None:
                view.reward = nxt.reward
                from ...db.repos import season as season_repo

                await season_repo.add_points(tx, player.id, "quest", now)
                await wallet.apply(
                    tx, player.id, gold=nxt.reward.gold, crystal=nxt.reward.crystal, reason=f"quest:{quest_id}",
                    now=now, ref=f"quest:{quest_id}:{player.id}",
                )
                for item_id, qty in nxt.reward.items:
                    await self.inventory.grant(tx, player.id, item_id, qty)
                if nxt.reward.xp:
                    up = await self.players.grant_xp(tx, player.id, nxt.reward.xp)
                    view.level_up = up.new_level if up else None
            return view
