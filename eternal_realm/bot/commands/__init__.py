"""Importing this package registers every command with the registry."""

from . import activities, admin, basic, duel, economy, group_admin, panels  # noqa: F401
from .registry import REGISTRY
from .router import router

__all__ = ["REGISTRY", "router"]
