"""Importing this package registers every command with the registry."""

from . import activities, basic, duel, economy, inventory, market, shop  # noqa: F401
from .registry import REGISTRY
from .router import router

__all__ = ["REGISTRY", "router"]
