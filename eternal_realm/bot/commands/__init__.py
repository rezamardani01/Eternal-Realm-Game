"""Importing this package registers every command with the registry."""

from . import activities, admin, basic, boss, clans, duel, economy, events, gdungeon, gifts, adminpanel, group_admin, owner, panels, teambattle  # noqa: F401
from .registry import REGISTRY
from .router import router

__all__ = ["REGISTRY", "router"]
