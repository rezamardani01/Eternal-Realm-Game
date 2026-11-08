"""Plain data objects returned by repositories."""

from __future__ import annotations

from dataclasses import dataclass

from ..db.database import Row
from .data.classes import CLASSES, CharacterClass
from .data.races import RACES, Race


@dataclass
class Player:
    id: int
    platform_user_id: int
    username: str | None
    name: str
    race_id: str
    class_id: str
    level: int
    xp: int
    energy: int
    energy_at: int
    gold: int
    crystal: int
    wins: int
    losses: int
    daily_at: int
    daily_streak: int
    banned: bool
    created_at: int
    class2_id: str = ""
    awakened: bool = False
    honor: str = ""

    @classmethod
    def from_row(cls, row: Row) -> Player:
        return cls(
            id=row["id"],
            platform_user_id=row["platform_user_id"],
            username=row["username"],
            name=row["display_name"],
            race_id=row["race"],
            class_id=row["class"],
            level=row["level"],
            xp=row["xp"],
            energy=row["energy"],
            energy_at=row["energy_at"],
            gold=row["gold"],
            crystal=row["crystal"],
            wins=row["wins"],
            losses=row["losses"],
            daily_at=row["daily_at"],
            daily_streak=row["daily_streak"],
            banned=bool(row["banned"]),
            created_at=row["created_at"],
            class2_id=row["class2"],
            awakened=bool(row["awakened"]),
            honor=row["title"],
        )

    @property
    def race(self) -> Race:
        return RACES[self.race_id]

    @property
    def char_class(self) -> CharacterClass:
        return CLASSES[self.class_id]

    @property
    def class2(self) -> CharacterClass | None:
        return CLASSES[self.class2_id] if self.class2_id else None

    @property
    def mention(self) -> str:
        """Bale mention of this player; used in group messages so the person gets pinged."""
        return f"[{self.name}](uid:{self.platform_user_id})"

    @property
    def title(self) -> str:
        return f"{self.char_class.emoji} {self.name}"
