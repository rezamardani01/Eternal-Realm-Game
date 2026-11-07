"""Manual backup: ``python scripts/backup.py [config.toml]``. Safe while the bot is running."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eternal_realm.bot.maintenance import make_backup  # noqa: E402
from eternal_realm.config import load_settings  # noqa: E402
from eternal_realm.db.database import Database  # noqa: E402


async def main(config: str) -> int:
    db = Database(load_settings(config).db_path)
    await db.connect()
    try:
        path = await make_backup(db)
    finally:
        await db.close()
    with sqlite3.connect(path) as conn:
        verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"backup: {path} (integrity: {verdict})")
    return 0 if verdict == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "config.toml")))
