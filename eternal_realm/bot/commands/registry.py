"""One registry for every text command, Persian keywords and ``/slash`` commands alike.

Handlers never parse text themselves: they declare names and aliases with ``@command`` and the
central resolver in :mod:`.router` does the matching.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...shared.text import normalize

if TYPE_CHECKING:
    from .context import CommandContext

Handler = Callable[["CommandContext"], Awaitable[None]]


@dataclass
class Command:
    name: str
    aliases: tuple[str, ...]
    handler: Handler
    description: str
    category: str = "عمومی"
    #: needs a registered character
    needs_player: bool = True
    #: allowed in private chat / in groups
    private: bool = True
    group: bool = True
    #: group admins may switch it off with «غیرفعال <دستور>»
    toggleable: bool = False
    #: accepts trailing words; otherwise the message must be exactly the keyword, so ordinary
    #: chat like «ماهی خیلی خوبه» never triggers a command
    takes_args: bool = False
    #: works even when the group switched the game off (admin tools)
    always_on: bool = False
    #: activity points added to the player's standing in the group on success
    points: int = 1
    default_aliases: tuple[str, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        self.default_aliases = self.aliases


@dataclass(frozen=True)
class Match:
    command: Command
    args: list[str]
    raw_args: str


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._index: dict[str, Command] = {}
        self._max_words = 1

    def command(
        self, name: str, aliases: list[str], description: str, **options: object
    ) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            self.add(Command(name, tuple(aliases), handler, description, **options))  # type: ignore[arg-type]
            return handler

        return register

    def add(self, command: Command) -> None:
        if command.name in self._commands:
            raise ValueError(f"duplicate command {command.name}")
        self._commands[command.name] = command
        self._reindex()

    def configure(self, overrides: dict[str, tuple[str, ...]]) -> None:
        """Replace aliases from ``config.toml`` (unknown names are ignored)."""
        for command in self._commands.values():
            command.aliases = overrides.get(command.name, command.default_aliases)
        self._reindex()

    def _reindex(self) -> None:
        self._index.clear()
        for command in self._commands.values():
            for alias in command.aliases:
                key = normalize(alias.lstrip("/")).lower()
                if key in self._index and self._index[key] is not command:
                    raise ValueError(f"alias {alias!r} used by two commands")
                self._index[key] = command
        self._max_words = max((k.count(" ") + 1 for k in self._index), default=1)

    def all(self) -> list[Command]:
        return list(self._commands.values())

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def find_by_alias(self, word: str) -> Command | None:
        return self._index.get(normalize(word).lstrip("/").lower())

    def resolve(self, text: str) -> Match | None:
        """Match ``text`` against the longest known alias at its start."""
        body = normalize(text)
        if not body:
            return None
        slash = body.startswith("/")
        if slash:
            body = body[1:]
        words = body.split(" ")
        words[0] = words[0].split("@", 1)[0]  # /fish@my_bot
        for count in range(min(self._max_words, len(words)), 0, -1):
            candidate = " ".join(words[:count]).lower()
            command = self._index.get(candidate)
            if command is None:
                continue
            if candidate.isascii() and not slash:
                continue  # English aliases only work as /commands
            rest = words[count:]
            if rest and not command.takes_args:
                continue
            return Match(command, rest, " ".join(rest))
        return None


REGISTRY = CommandRegistry()
command = REGISTRY.command
