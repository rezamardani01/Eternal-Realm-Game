"""Importing this package registers every command with the registry."""

from . import activities, admin, basic, boss, clans, duel, economy, events, gdungeon, gifts, adminpanel, group_admin, owner, panels, teambattle  # noqa: F401
from .registry import PRIVATE_ONLY, REGISTRY
from .router import router

for _name in PRIVATE_ONLY:
    REGISTRY._commands[_name].group = False

__all__ = ["REGISTRY", "router"]
