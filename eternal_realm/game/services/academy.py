"""The academy: which lessons a hero has learned, noticing new ones from what they really do, and paying for them.

Progress lives in ``solo_progress`` under ``acad:`` keys (``acad:on``, ``acad:done:<lesson>``, ``acad:skip:<lesson>``,
``acad:chap:<n>``, ``acad:grad``). A lesson is learned when the hero opens one of its screens, sends one of its
commands, or when its ``check`` finds the deed in the database; each lesson, chapter and the graduation pay once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import titles, wallet
from ..data import academy as data
from ...shared.errors import GameError
from ..models import Player
from .inventory import InventoryService
from .players import LevelUp, PlayerService

#: what each ``check`` looks for (``?`` is the player's id)
CHECKS: dict[str, str] = {
    "academy_fight": "SELECT 1 FROM solo_fights WHERE player_id = ? AND kind = 'academy' AND status = 'won'",
    "story": "SELECT 1 FROM solo_progress WHERE player_id = ? AND key = 'story' AND n >= 1",
    "arena": "SELECT 1 FROM solo_fights WHERE player_id = ? AND kind = 'arena' AND status IN ('won', 'lost')",
    "sold": "SELECT 1 FROM transactions WHERE player_id = ? AND reason IN ('shop_sell', 'market_sell')",
    "wheel": "SELECT 1 FROM wheel_log WHERE player_id = ?",
    "dungeon": "SELECT 1 FROM solo_fights WHERE player_id = ? AND kind = 'dungeon'",
    "maze": "SELECT 1 FROM solo_progress WHERE player_id = ? AND key = 'maze:best' AND n >= 1",
    "tower": "SELECT 1 FROM solo_progress WHERE player_id = ? AND key = 'tower:best' AND n >= 1",
    "quest": "SELECT 1 FROM player_quests WHERE player_id = ?",
    "expedition": "SELECT 1 FROM transactions WHERE player_id = ? AND reason = 'expedition'"
    " UNION SELECT 1 FROM expeditions WHERE player_id = ?",
    "clan": "SELECT 1 FROM clan_members WHERE player_id = ?",
    "group": "SELECT 1 FROM group_members WHERE player_id = ?",
    "duel": "SELECT 1 FROM deed_counts WHERE player_id = ? AND deed IN ('duel', 'duel_win') AND n > 0",
    "boss": "SELECT 1 FROM deed_counts WHERE player_id = ? AND deed IN ('boss', 'boss_win') AND n > 0",
    "city": "SELECT 1 FROM cities WHERE player_id = ?",
    "build": "SELECT 1 FROM city_builds b JOIN cities c ON c.id = b.city_id WHERE c.player_id = ?"
    " UNION SELECT 1 FROM city_buildings b JOIN cities c ON c.id = b.city_id WHERE c.player_id = ? AND b.level >= 2",
    "troops": "SELECT 1 FROM city_troops t JOIN cities c ON c.id = t.city_id WHERE c.player_id = ? AND t.qty > 0",
}


@dataclass
class Completion:
    """One lesson just learned, and whatever finishing it brought with it."""

    lesson: data.Lesson
    gold: int
    xp: int
    level_up: LevelUp | None = None
    #: the chapter this lesson finished (its chest was paid)
    chapter: data.Chapter | None = None
    graduated: bool = False


@dataclass
class AcademyState:
    started: bool
    done: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    graduated: bool = False

    def _passed(self, lesson: data.Lesson) -> bool:
        """Learned, or (a lesson that may wait) put off: the lessons after it may open."""
        return lesson.id in self.done or (lesson.skippable and lesson.id in self.skipped)

    @property
    def current(self) -> data.Lesson | None:
        """The next lesson to learn: the first one neither learned nor put off."""
        return next((x for x in data.LESSONS if not self._passed(x)), None)

    @property
    def next_open(self) -> data.Lesson | None:
        """The first lesson not learned yet, put off or not (the way back to a skipped one)."""
        return next((x for x in data.LESSONS if x.id not in self.done), None)

    def unlocked(self, lesson: data.Lesson) -> bool:
        """A lesson opens once every lesson before it is learned (or, for those that may wait, put off)."""
        for earlier in data.LESSONS:
            if earlier.id == lesson.id:
                return True
            if not self._passed(earlier):
                return False
        return False

    def open_lessons(self) -> list[data.Lesson]:
        """The lessons that can be learned right now: the current one and the ones put off before it."""
        return [x for x in data.LESSONS if x.id not in self.done and self.unlocked(x)]

    def chapter_done(self, number: int) -> int:
        return sum(1 for x in data.lessons_of(number) if x.id in self.done)


class AcademyService:
    def __init__(self, ctx: AppContext, players: PlayerService, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.players = players
        self.inventory = inventory

    # --- reading ------------------------------------------------------------------------------------------------------------
    async def _state(self, tx: Tx, player_id: int) -> AcademyState:
        rows = await tx.fetchall("SELECT key FROM solo_progress WHERE player_id = ? AND key LIKE 'acad:%'", (player_id,))
        keys = {r["key"] for r in rows}
        return AcademyState(
            started="acad:on" in keys,
            done={k.removeprefix("acad:done:") for k in keys if k.startswith("acad:done:")},
            skipped={k.removeprefix("acad:skip:") for k in keys if k.startswith("acad:skip:")},
            graduated="acad:grad" in keys,
        )

    async def state(self, player_id: int) -> AcademyState:
        async with self.ctx.db.read() as tx:
            return await self._state(tx, player_id)

    async def _fact(self, tx: Tx, player_id: int, lesson: data.Lesson) -> bool:
        """Whether the database already shows the lesson's deed."""
        check = lesson.check
        if not check:
            return False
        if check.startswith("deed:"):
            sql, args = "SELECT 1 FROM deed_counts WHERE player_id = ? AND deed = ? AND n > 0", (player_id, check[5:])
        elif check.startswith("ledger:"):
            sql, args = "SELECT 1 FROM transactions WHERE player_id = ? AND reason = ? LIMIT 1", (player_id, check[7:])
        else:
            sql = CHECKS[check]
            args = (player_id,) * sql.count("?")
        return bool(await tx.scalar(sql, args, 0))

    # --- learning -----------------------------------------------------------------------------------------------------------
    async def start(self, player_id: int) -> None:
        async with self.ctx.db.transaction() as tx:
            await self._mark(tx, player_id, "acad:on")

    async def _mark(self, tx: Tx, player_id: int, key: str) -> bool:
        await tx.execute("INSERT OR IGNORE INTO solo_progress (player_id, key, n) VALUES (?, ?, 1)", (player_id, key))
        return tx.rowcount > 0

    async def _complete(self, tx: Tx, player_id: int, lesson: data.Lesson, state: AcademyState) -> Completion | None:
        if not await self._mark(tx, player_id, f"acad:done:{lesson.id}"):
            return None
        state.done.add(lesson.id)
        now = self.ctx.now()
        await wallet.apply(tx, player_id, gold=lesson.gold, reason="academy", now=now, ref=f"academy:{player_id}:{lesson.id}")
        done = Completion(lesson, lesson.gold, lesson.xp, await self.players.grant_xp(tx, player_id, lesson.xp))
        chapter = data.CHAPTER_BY_NUMBER[lesson.chapter]
        if state.chapter_done(chapter.number) == len(data.lessons_of(chapter.number)) and await self._mark(
            tx, player_id, f"acad:chap:{chapter.number}"
        ):
            await self.inventory.grant(tx, player_id, chapter.chest, 1, origin="academy")
            done.chapter = chapter
        if len(state.done) == len(data.LESSONS) and await self._mark(tx, player_id, "acad:grad"):
            await wallet.apply(tx, player_id, crystal=data.GRADUATION_CRYSTAL, reason="academy", now=now, ref=f"academy:{player_id}:grad")
            await self.inventory.grant(tx, player_id, data.GRADUATION_CHEST, 1, origin="academy")
            await titles.award(tx, player_id, "academy", data.GRADUATION_TITLE, now)
            state.graduated = done.graduated = True
        return done

    async def _learn_open(self, tx: Tx, player_id: int, state: AcademyState, screen: str, command: str) -> list[Completion]:
        """Learn the open lessons the hero just did; finishing one opens the next, which is looked at too."""
        out: list[Completion] = []
        for _ in range(len(data.LESSONS)):
            learned = None
            for lesson in state.open_lessons():
                if (screen and screen in lesson.visit) or (command and command in lesson.commands) or await self._fact(tx, player_id, lesson):
                    learned = await self._complete(tx, player_id, lesson, state)
                    break
            if learned is None:
                break
            out.append(learned)
        return out

    async def after(self, player: Player, *, screen: str = "", command: str = "") -> list[Completion]:
        """Called after the hero did something: the lessons it taught, if the hero is in the academy.

        Only open lessons are learned: a locked lesson waits for the ones before it, even if the hero already did it
        (it is ticked as soon as it opens).
        """
        async with self.ctx.db.transaction() as tx:
            state = await self._state(tx, player.id)
            if not state.started or state.graduated:
                return []
            return await self._learn_open(tx, player.id, state, screen, command)

    async def sync(self, player: Player) -> list[Completion]:
        """Opening the academy (it starts here too): the open lessons whose deed is already done are learned, in order."""
        async with self.ctx.db.transaction() as tx:
            await self._mark(tx, player.id, "acad:on")
            state = await self._state(tx, player.id)
            return await self._learn_open(tx, player.id, state, "", "")

    async def check(self, player: Player, lesson_id: str) -> Completion | None:
        """«I did it, check»: the lesson's deed, looked up now (a locked lesson cannot be learned yet)."""
        lesson = data.LESSON_BY_ID[lesson_id]
        async with self.ctx.db.transaction() as tx:
            state = await self._state(tx, player.id)
            if lesson.id in state.done or not state.unlocked(lesson) or not await self._fact(tx, player.id, lesson):
                return None
            return await self._complete(tx, player.id, lesson, state)

    async def skip(self, player_id: int, lesson_id: str) -> None:
        """Put off a lesson that may wait (it needs a group, or a level the hero may not have yet); learned later."""
        lesson = data.LESSON_BY_ID[lesson_id]
        async with self.ctx.db.transaction() as tx:
            state = await self._state(tx, player_id)
            if not lesson.skippable:
                raise GameError("این درس را نمی‌شود رد کرد؛ کارش را انجام بده تا درس بعدی باز شود 🙂")
            if not state.unlocked(lesson):
                raise GameError("این درس هنوز قفل است؛ اول درس‌های قبلی را تمام کن.")
            await self._mark(tx, player_id, "acad:on")
            await self._mark(tx, player_id, f"acad:skip:{lesson.id}")
