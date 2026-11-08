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
    # 3: inventory (stackable items), gear (individual pieces) and activity cooldowns
    """
    CREATE TABLE inventory (
        player_id INTEGER NOT NULL REFERENCES players (id),
        item_id   TEXT    NOT NULL,
        qty       INTEGER NOT NULL CHECK (qty >= 0),
        PRIMARY KEY (player_id, item_id)
    );

    CREATE TABLE gear (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id  INTEGER NOT NULL REFERENCES players (id),
        item_id    TEXT    NOT NULL,
        upgrade    INTEGER NOT NULL DEFAULT 0 CHECK (upgrade >= 0),
        slot       TEXT,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX idx_gear_player ON gear (player_id);
    CREATE UNIQUE INDEX idx_gear_equipped ON gear (player_id, slot) WHERE slot IS NOT NULL;

    CREATE TABLE cooldowns (
        player_id INTEGER NOT NULL REFERENCES players (id),
        key       TEXT    NOT NULL,
        until     INTEGER NOT NULL,
        PRIMARY KEY (player_id, key)
    );
    """,
    # 4: duels between players
    """
    CREATE TABLE duels (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id       INTEGER NOT NULL,
        message_id    INTEGER,
        challenger_id INTEGER NOT NULL REFERENCES players (id),
        target_id     INTEGER NOT NULL REFERENCES players (id),
        status        TEXT    NOT NULL
                      CHECK (status IN ('pending', 'active', 'finished', 'declined', 'expired')),
        state         TEXT,
        winner_id     INTEGER REFERENCES players (id),
        created_at    INTEGER NOT NULL,
        updated_at    INTEGER NOT NULL,
        expires_at    INTEGER NOT NULL
    );
    CREATE INDEX idx_duels_challenger ON duels (challenger_id, status);
    CREATE INDEX idx_duels_target ON duels (target_id, status);
    CREATE INDEX idx_duels_expiry ON duels (status, expires_at);
    """,
    # 5: player market. Listed gear stays in `gear` but is flagged and hidden from its owner.
    """
    ALTER TABLE gear ADD COLUMN listed INTEGER NOT NULL DEFAULT 0;

    CREATE TABLE market_listings (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id  INTEGER NOT NULL REFERENCES players (id),
        item_id    TEXT    NOT NULL,
        qty        INTEGER NOT NULL CHECK (qty > 0),
        gear_id    INTEGER REFERENCES gear (id),
        price      INTEGER NOT NULL CHECK (price > 0),
        status     TEXT    NOT NULL CHECK (status IN ('active', 'sold', 'cancelled')),
        buyer_id   INTEGER REFERENCES players (id),
        created_at INTEGER NOT NULL,
        closed_at  INTEGER
    );
    CREATE INDEX idx_market_active ON market_listings (status, item_id, price);
    CREATE INDEX idx_market_seller ON market_listings (seller_id, status);
    """,
    # 6: real-money orders paid through the Bale wallet. No card data is ever stored.
    """
    CREATE TABLE orders (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id    INTEGER NOT NULL REFERENCES players (id),
        pack_id      TEXT    NOT NULL,
        amount       INTEGER NOT NULL CHECK (amount > 0),
        status       TEXT    NOT NULL
                     CHECK (status IN ('pending', 'paid', 'delivered', 'failed', 'refunded')),
        payload      TEXT    NOT NULL UNIQUE,
        charge_id    TEXT UNIQUE,
        created_at   INTEGER NOT NULL,
        paid_at      INTEGER,
        delivered_at INTEGER
    );
    CREATE INDEX idx_orders_player ON orders (player_id, status);
    CREATE INDEX idx_orders_pending ON orders (status, created_at);
    """,
    # 7: audit trail of everything administrators do
    """
    CREATE TABLE admin_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id   INTEGER NOT NULL,
        action     TEXT    NOT NULL,
        detail     TEXT    NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL
    );
    """,
    # 8: group bosses and every player's share of the damage
    """
    CREATE TABLE bosses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     INTEGER NOT NULL,
        message_id  INTEGER,
        boss_type   TEXT    NOT NULL,
        level       INTEGER NOT NULL,
        max_hp      INTEGER NOT NULL,
        hp          INTEGER NOT NULL CHECK (hp >= 0),
        status      TEXT    NOT NULL CHECK (status IN ('active', 'defeated', 'expired')),
        summoner_id INTEGER NOT NULL REFERENCES players (id),
        created_at  INTEGER NOT NULL,
        expires_at  INTEGER NOT NULL,
        ended_at    INTEGER
    );
    CREATE INDEX idx_bosses_chat ON bosses (chat_id, status, created_at);

    CREATE TABLE boss_hits (
        boss_id   INTEGER NOT NULL REFERENCES bosses (id),
        player_id INTEGER NOT NULL REFERENCES players (id),
        damage    INTEGER NOT NULL DEFAULT 0,
        hits      INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (boss_id, player_id)
    );
    """,
    # 9: boss fights became automatic: a sign-up phase, a stored simulation state and per-fighter health
    """
    ALTER TABLE bosses ADD COLUMN phase TEXT NOT NULL DEFAULT 'fighting';
    ALTER TABLE bosses ADD COLUMN recruit_until INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE bosses ADD COLUMN next_round_at INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE bosses ADD COLUMN last_report_at INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE bosses ADD COLUMN state TEXT NOT NULL DEFAULT '{}';
    ALTER TABLE boss_hits ADD COLUMN hp INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE boss_hits ADD COLUMN max_hp INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE boss_hits ADD COLUMN alive INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE boss_hits ADD COLUMN absorbed INTEGER NOT NULL DEFAULT 0;
    """,
    # 10: how often each activity was used today (drives the stepped cooldowns)
    """
    CREATE TABLE activity_usage (
        player_id INTEGER NOT NULL REFERENCES players (id),
        key       TEXT    NOT NULL,
        day       INTEGER NOT NULL,
        uses      INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, key)
    );
    """,
    # 11: events the bot starts in groups by itself
    """
    ALTER TABLE groups ADD COLUMN next_event_at INTEGER NOT NULL DEFAULT 0;

    CREATE TABLE group_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id    INTEGER NOT NULL,
        kind       TEXT    NOT NULL,
        message_id INTEGER,
        status     TEXT    NOT NULL CHECK (status IN ('active', 'done', 'expired')),
        state      TEXT    NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    );
    CREATE INDEX idx_group_events_chat ON group_events (chat_id, status, kind);
    """,
    # 12: clans with roles and a shared treasury
    """
    CREATE TABLE clans (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        leader_id  INTEGER NOT NULL REFERENCES players (id),
        open       INTEGER NOT NULL DEFAULT 1,
        treasury   INTEGER NOT NULL DEFAULT 0,
        donated    INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    );

    CREATE TABLE clan_members (
        player_id INTEGER PRIMARY KEY REFERENCES players (id),
        clan_id   INTEGER NOT NULL REFERENCES clans (id),
        role      TEXT    NOT NULL CHECK (role IN ('leader', 'deputy', 'elder', 'member')),
        donated   INTEGER NOT NULL DEFAULT 0,
        joined_at INTEGER NOT NULL
    );
    CREATE INDEX idx_clan_members_clan ON clan_members (clan_id);
    """,
    # 13: ranked duel rating and the weekly clan war
    """
    ALTER TABLE players ADD COLUMN rating INTEGER NOT NULL DEFAULT 1000;

    CREATE TABLE clan_war (
        week    INTEGER NOT NULL,
        clan_id INTEGER NOT NULL REFERENCES clans (id),
        points  INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (week, clan_id)
    );
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
