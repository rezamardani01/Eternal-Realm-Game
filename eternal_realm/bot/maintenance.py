"""Background upkeep: a daily database backup that keeps the newest few copies."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from ..db.database import Database

log = logging.getLogger("eternal_realm.backup")

KEEP = 7
DAY = 24 * 3600


def prune(folder: Path, keep: int = KEEP) -> list[Path]:
    """Delete all but the newest ``keep`` ``game-*.db`` files; returns what was removed."""
    files = sorted(folder.glob("game-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = files[keep:]
    for old in removed:
        old.unlink(missing_ok=True)
    return removed


async def make_backup(db: Database, folder: Path = Path("backups")) -> Path:
    target = folder / f"game-{time.strftime('%Y%m%d-%H%M%S')}.db"
    target.unlink(missing_ok=True)  # two backups within one second replace each other
    path = await db.backup(target)
    prune(folder)
    return path


async def backup_loop(db: Database, interval: float = DAY) -> None:
    while True:
        try:
            log.info("backup written to %s", await make_backup(db))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("backup failed")
        await asyncio.sleep(interval)
