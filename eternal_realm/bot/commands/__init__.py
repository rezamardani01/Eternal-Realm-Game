"""Importing this package registers every command with the registry."""

from . import activities, basic, chests, duel, economy, group_admin, inventory, market, rankings, shop  # noqa: F401
from .registry import REGISTRY
from .router import router

__all__ = ["REGISTRY", "router"]
