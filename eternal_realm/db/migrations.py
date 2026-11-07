"""Versioned schema migrations tracked through ``PRAGMA user_version``.

Append a new script to ``MIGRATIONS`` to change the schema; never edit an applied one.
Statements are split on ``;`` so scripts must not contain semicolons inside literals.
"""

from __future__ import annotations

import aiosqlite

MIGRATIONS: list[str] = [
    # 1: players and the wallet ledger
    """
    CREATE TABLE players (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_user_id  INTEGER NOT NULL UNIQUE,
        username          TEXT,
        display_name      TEXT    NOT NULL COLLATE NOCASE UNIQUE,
        race              TEXT    NOT NULL,
        class             TEXT    NOT NULL,
        level             INTEGER NOT NULL DEFAULT 1 CHECK (level >= 1),
        xp                INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
        energy            INTEGER NOT NULL DEFAULT 0 CHECK (energy >= 0),
        energy_at         INTEGER NOT NULL,
        gold              INTEGER NOT NULL DEFAULT 0 CHECK (gold >= 0),
        crystal           INTEGER NOT NULL DEFAULT 0 CHECK (crystal >= 0),
        wins              INTEGER NOT NULL DEFAULT 0,
        losses            INTEGER NOT NULL DEFAULT 0,
        daily_at          INTEGER NOT NULL DEFAULT 0,
        daily_streak      INTEGER NOT NULL DEFAULT 0,
        banned            INTEGER NOT NULL DEFAULT 0,
        created_at        INTEGER NOT NULL
    );
    CREATE INDEX idx_players_level ON players (level DESC, xp DESC);

    CREATE TABLE transactions (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id     INTEGER NOT NULL REFERENCES players (id),
        gold_delta    INTEGER NOT NULL DEFAULT 0,
        crystal_delta INTEGER NOT NULL DEFAULT 0,
        reason        TEXT    NOT NULL,
        ref           TEXT UNIQUE,
        created_at    INTEGER NOT NULL
    );
    CREATE INDEX idx_transactions_player ON transactions (player_id, created_at);
    CREATE INDEX idx_transactions_reason ON transactions (reason, player_id, created_at);
    """,
    # 2: Bale groups the bot plays in, and per-group activity of each player
    """
    CREATE TABLE groups (
        chat_id      INTEGER PRIMARY KEY,
        title        TEXT    NOT NULL DEFAULT '',
        enabled      INTEGER NOT NULL DEFAULT 1,
        disabled_cmds TEXT   NOT NULL DEFAULT '',
        created_at   INTEGER NOT NULL,
        last_seen    INTEGER NOT NULL
    );

    CREATE TABLE group_members (
        chat_id     INTEGER NOT NULL REFERENCES groups (chat_id),
        player_id   INTEGER NOT NULL REFERENCES players (id),
        points      INTEGER NOT NULL DEFAULT 0,
        last_active INTEGER NOT NULL,
        PRIMARY KEY (chat_id, player_id)
    );
    CREATE INDEX idx_group_members_rank ON group_members (chat_id, points DESC);
    """,
]


async def apply_migrations(conn: aiosqlite.Connection) -> int:
    cursor = await conn.execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()
    current = int(row[0]) if row else 0
    for version, script in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        await conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in _statements(script):
                await conn.execute(statement)
            await conn.execute(f"PRAGMA user_version = {version}")
        except BaseException:
            await conn.execute("ROLLBACK")
            raise
        await conn.execute("COMMIT")
        current = version
    return current


def _statements(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]
