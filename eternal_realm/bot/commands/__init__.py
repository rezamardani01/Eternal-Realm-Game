"""Importing this package registers every command with the registry."""

from . import basic, inventory  # noqa: F401
from .registry import REGISTRY
from .router import router

__all__ = ["REGISTRY", "router"]
