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
    # 14: every gear piece remembers where it came from and who owned it
    """
    ALTER TABLE gear ADD COLUMN origin TEXT NOT NULL DEFAULT '';
    """,
    # 15: story quests
    """
    CREATE TABLE player_quests (
        player_id  INTEGER NOT NULL REFERENCES players (id),
        quest_id   TEXT    NOT NULL,
        step       TEXT    NOT NULL,
        flags      TEXT    NOT NULL DEFAULT '',
        done       INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (player_id, quest_id)
    );
    """,
    # 16: a second class and the awakening of hidden power
    """
    ALTER TABLE players ADD COLUMN class2 TEXT NOT NULL DEFAULT '';
    ALTER TABLE players ADD COLUMN awakened INTEGER NOT NULL DEFAULT 0;
    """,
    # 17: the card collection
    """
    ALTER TABLE players ADD COLUMN title TEXT NOT NULL DEFAULT '';

    CREATE TABLE player_cards (
        player_id INTEGER NOT NULL REFERENCES players (id),
        card_id   TEXT    NOT NULL,
        qty       INTEGER NOT NULL DEFAULT 1,
        first_at  INTEGER NOT NULL,
        PRIMARY KEY (player_id, card_id)
    );

    CREATE TABLE card_rewards (
        player_id  INTEGER NOT NULL REFERENCES players (id),
        set_id     TEXT    NOT NULL,
        claimed_at INTEGER NOT NULL,
        PRIMARY KEY (player_id, set_id)
    );
    """,
    # 18: companion pets
    """
    CREATE TABLE player_pets (
        player_id INTEGER NOT NULL REFERENCES players (id),
        pet_id    TEXT    NOT NULL,
        active    INTEGER NOT NULL DEFAULT 0,
        got_at    INTEGER NOT NULL,
        PRIMARY KEY (player_id, pet_id)
    );
    """,
    # 19: a hero's current dungeon run
    """
    CREATE TABLE player_dungeon (
        player_id  INTEGER PRIMARY KEY REFERENCES players (id),
        stage      INTEGER NOT NULL,
        hp         INTEGER NOT NULL,
        max_hp     INTEGER NOT NULL,
        gold       INTEGER NOT NULL DEFAULT 0,
        xp         INTEGER NOT NULL DEFAULT 0,
        loot       TEXT    NOT NULL DEFAULT '{}',
        started_at INTEGER NOT NULL
    );
    """,
    # 20: the hero-path ticket (season pass)
    """
    CREATE TABLE season_progress (
        player_id INTEGER NOT NULL REFERENCES players (id),
        season    INTEGER NOT NULL,
        points    INTEGER NOT NULL DEFAULT 0,
        premium   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, season)
    );

    CREATE TABLE season_claims (
        player_id  INTEGER NOT NULL REFERENCES players (id),
        season     INTEGER NOT NULL,
        track      TEXT    NOT NULL,
        tier       INTEGER NOT NULL,
        claimed_at INTEGER NOT NULL,
        PRIMARY KEY (player_id, season, track, tier)
    );
    """,
    # 21: personal offers (what was sent, and who switched them off)
    """
    ALTER TABLE players ADD COLUMN offers_off INTEGER NOT NULL DEFAULT 0;

    CREATE TABLE offers_log (
        player_id INTEGER NOT NULL REFERENCES players (id),
        rule_id   TEXT    NOT NULL,
        sent_at   INTEGER NOT NULL
    );
    CREATE INDEX idx_offers_log ON offers_log (player_id, sent_at);
    """,
    # 22: personal daily missions
    """
    CREATE TABLE daily_missions (
        player_id INTEGER NOT NULL REFERENCES players (id),
        day       INTEGER NOT NULL,
        slot      INTEGER NOT NULL,
        kind_id   TEXT    NOT NULL,
        deed      TEXT    NOT NULL,
        target    INTEGER NOT NULL,
        progress  INTEGER NOT NULL DEFAULT 0,
        claimed   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, day, slot)
    );
    """,
    # 23: cards for sale between players
    """
    CREATE TABLE card_listings (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id  INTEGER NOT NULL REFERENCES players (id),
        card_id    TEXT    NOT NULL,
        price      INTEGER NOT NULL CHECK (price > 0),
        status     TEXT    NOT NULL CHECK (status IN ('active', 'sold', 'cancelled')),
        buyer_id   INTEGER,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX idx_card_listings_active ON card_listings (status, card_id, price);
    """,
    # 24: a weapon grows closer to its wielder the more it is used
    """
    ALTER TABLE gear ADD COLUMN bond_uses INTEGER NOT NULL DEFAULT 0;
    """,
    # 25: the last path tier a player was told about
    """
    ALTER TABLE season_progress ADD COLUMN notified INTEGER NOT NULL DEFAULT 0;
    """,
    # 26: VIP subscription (comfort only: never combat strength)
    """
    ALTER TABLE players ADD COLUMN vip_until INTEGER NOT NULL DEFAULT 0;
    """,
    # 27: group dungeon lobbies
    """
    CREATE TABLE gdungeons (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     INTEGER NOT NULL,
        message_id  INTEGER,
        summoner_id INTEGER NOT NULL REFERENCES players (id),
        status      TEXT    NOT NULL CHECK (status IN ('recruiting', 'done')),
        created_at  INTEGER NOT NULL,
        expires_at  INTEGER NOT NULL
    );
    CREATE INDEX idx_gdungeons_chat ON gdungeons (chat_id, status);

    CREATE TABLE gdungeon_members (
        dungeon_id INTEGER NOT NULL REFERENCES gdungeons (id),
        player_id  INTEGER NOT NULL REFERENCES players (id),
        PRIMARY KEY (dungeon_id, player_id)
    );
    """,
    # 28: weekly contests
    """
    CREATE TABLE weekly_stats (
        week      INTEGER NOT NULL,
        contest   TEXT    NOT NULL,
        player_id INTEGER NOT NULL REFERENCES players (id),
        count     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (week, contest, player_id)
    );
    """,
    # 29: blessings and curses
    """
    CREATE TABLE player_effects (
        player_id INTEGER NOT NULL REFERENCES players (id),
        effect_id TEXT    NOT NULL,
        until     INTEGER NOT NULL,
        PRIMARY KEY (player_id, effect_id)
    );
    """,
    # 30: pets can be upgraded with crystals
    """
    ALTER TABLE player_pets ADD COLUMN level INTEGER NOT NULL DEFAULT 1;
    """,
    # 31: settings the admin panel can change (forced channel membership...)
    """
    CREATE TABLE app_settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 32: the card market is gone: cards on sale go back to their owners
    """
    INSERT INTO player_cards (player_id, card_id, qty, first_at)
    SELECT seller_id, card_id, 1, CAST(strftime('%s', 'now') AS INTEGER) FROM card_listings WHERE status = 'active'
    ON CONFLICT (player_id, card_id) DO UPDATE SET qty = qty + 1;
    UPDATE card_listings SET status = 'cancelled' WHERE status = 'active';
    """,
    # 33: invited friends and the owner's gift boxes
    """
    CREATE TABLE referrals (
        invited_id  INTEGER PRIMARY KEY REFERENCES players (id),
        referrer_id INTEGER NOT NULL REFERENCES players (id),
        created_at  INTEGER NOT NULL
    );
    CREATE INDEX idx_referrals_referrer ON referrals (referrer_id, created_at);
    CREATE TABLE gift_boxes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id  INTEGER NOT NULL REFERENCES players (id),
        pack_id    TEXT    NOT NULL,
        created_at INTEGER NOT NULL,
        opened_at  INTEGER
    );
    """,
    # 34: bet duels (stakes are locked until the duel ends)
    """
    CREATE TABLE bet_duels (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id       INTEGER NOT NULL,
        message_id    INTEGER,
        challenger_id INTEGER NOT NULL REFERENCES players (id),
        accepter_id   INTEGER REFERENCES players (id),
        kind          TEXT    NOT NULL CHECK (kind IN ('gold', 'crystal', 'item')),
        item_id       TEXT    NOT NULL DEFAULT '',
        amount        INTEGER NOT NULL CHECK (amount > 0),
        status        TEXT    NOT NULL CHECK (status IN ('open', 'active', 'done', 'cancelled', 'expired')),
        duel_id       INTEGER,
        created_at    INTEGER NOT NULL,
        expires_at    INTEGER NOT NULL
    );
    CREATE INDEX idx_bet_duels_status ON bet_duels (status, expires_at);
    CREATE INDEX idx_bet_duels_duel ON bet_duels (duel_id);
    """,
    # 35: bet duels over a gear piece: the opponent pays its value in coins/crystals or puts up the same piece
    """
    CREATE TABLE bet_duels_new (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id       INTEGER NOT NULL,
        message_id    INTEGER,
        challenger_id INTEGER NOT NULL REFERENCES players (id),
        accepter_id   INTEGER REFERENCES players (id),
        kind          TEXT    NOT NULL CHECK (kind IN ('gold', 'crystal', 'item', 'gear')),
        item_id       TEXT    NOT NULL DEFAULT '',
        amount        INTEGER NOT NULL CHECK (amount > 0),
        status        TEXT    NOT NULL CHECK (status IN ('open', 'active', 'done', 'cancelled', 'expired')),
        duel_id       INTEGER,
        created_at    INTEGER NOT NULL,
        expires_at    INTEGER NOT NULL,
        gear_id       INTEGER,
        gear_upgrade  INTEGER NOT NULL DEFAULT 0,
        pay_kind      TEXT    NOT NULL DEFAULT '',
        pay_amount    INTEGER NOT NULL DEFAULT 0,
        pay_gear_id   INTEGER
    );
    INSERT INTO bet_duels_new (id, chat_id, message_id, challenger_id, accepter_id, kind, item_id, amount, status, duel_id, created_at, expires_at)
    SELECT id, chat_id, message_id, challenger_id, accepter_id, kind, item_id, amount, status, duel_id, created_at, expires_at FROM bet_duels;
    DROP TABLE bet_duels;
    ALTER TABLE bet_duels_new RENAME TO bet_duels;
    CREATE INDEX idx_bet_duels_status ON bet_duels (status, expires_at);
    CREATE INDEX idx_bet_duels_duel ON bet_duels (duel_id);
    """,
    # 36: the 2x reward boost (bought in 24/48/72 hour packs)
    """
    ALTER TABLE players ADD COLUMN boost_until INTEGER NOT NULL DEFAULT 0;
    """,
    # 37: achievements (how often each deed was done, and which steps were paid)
    """
    CREATE TABLE deed_counts (
        player_id INTEGER NOT NULL REFERENCES players (id),
        deed      TEXT    NOT NULL,
        n         INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, deed)
    );
    CREATE TABLE achievement_claims (
        player_id  INTEGER NOT NULL REFERENCES players (id),
        family     TEXT    NOT NULL,
        step       INTEGER NOT NULL,
        claimed_at INTEGER NOT NULL,
        PRIMARY KEY (player_id, family, step)
    );
    """,
    # 38: team battles (a lobby with seats, then the fight)
    """
    CREATE TABLE team_battles (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id    INTEGER NOT NULL,
        message_id INTEGER,
        creator_id INTEGER NOT NULL REFERENCES players (id),
        status     TEXT    NOT NULL,
        state      TEXT    NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    );
    CREATE INDEX idx_team_battles_open ON team_battles (status, expires_at);
    CREATE TABLE team_battle_members (
        battle_id INTEGER NOT NULL REFERENCES team_battles (id),
        player_id INTEGER NOT NULL REFERENCES players (id),
        team      INTEGER NOT NULL,
        seat      INTEGER NOT NULL,
        paid_at   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (battle_id, player_id),
        UNIQUE (battle_id, team, seat)
    );
    CREATE INDEX idx_team_members_player ON team_battle_members (player_id, paid_at);
    """,
    # 39: clan photo, betrayal fine, minimum level, Khan points and their shop
    """
    ALTER TABLE clans ADD COLUMN photo TEXT NOT NULL DEFAULT '';
    ALTER TABLE clans ADD COLUMN exit_fine INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE clans ADD COLUMN min_level INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE players ADD COLUMN khan_points INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE khan_purchases (
        player_id INTEGER NOT NULL REFERENCES players (id),
        day       INTEGER NOT NULL,
        offer     TEXT    NOT NULL,
        PRIMARY KEY (player_id, day, offer)
    );
    """,
    # 40: heroes the creator threw out of a team battle
    """
    CREATE TABLE team_battle_bans (
        battle_id INTEGER NOT NULL REFERENCES team_battles (id),
        player_id INTEGER NOT NULL REFERENCES players (id),
        PRIMARY KEY (battle_id, player_id)
    );
    """,
    # 41: the exchange centre's trades (and the fees the bot kept)
    """
    CREATE TABLE exchange_log (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id INTEGER NOT NULL REFERENCES players (id),
        direction TEXT    NOT NULL,
        crystals  INTEGER NOT NULL,
        gold      INTEGER NOT NULL,
        fee       INTEGER NOT NULL,
        at        INTEGER NOT NULL
    );
    CREATE INDEX idx_exchange_player ON exchange_log (player_id, direction, at);
    """,
    # 42: wheel of fortune spins and what they paid
    """
    ALTER TABLE players ADD COLUMN wheel_spins INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE wheel_log (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id INTEGER NOT NULL REFERENCES players (id),
        slice     TEXT    NOT NULL,
        at        INTEGER NOT NULL
    );
    """,
    # 43: cities (realm rule): buildings, army, defences, raids and their reports
    """
    CREATE TABLE cities (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id    INTEGER NOT NULL UNIQUE REFERENCES players (id),
        name         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        flag         TEXT    NOT NULL,
        gold         REAL    NOT NULL,
        food         REAL    NOT NULL,
        wood         REAL    NOT NULL,
        stone        REAL    NOT NULL,
        iron         REAL    NOT NULL,
        population   REAL    NOT NULL,
        happiness    REAL    NOT NULL,
        last_tick    INTEGER NOT NULL,
        shield_until INTEGER NOT NULL DEFAULT 0,
        trophies     INTEGER NOT NULL DEFAULT 0,
        created_at   INTEGER NOT NULL,
        last_active  INTEGER NOT NULL,
        att_day      INTEGER NOT NULL DEFAULT 0,
        att_count    INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_cities_trophies ON cities (trophies DESC);
    CREATE INDEX idx_cities_shield ON cities (shield_until);
    CREATE TABLE city_buildings (
        city_id INTEGER NOT NULL REFERENCES cities (id),
        kind    TEXT    NOT NULL,
        level   INTEGER NOT NULL,
        PRIMARY KEY (city_id, kind)
    );
    CREATE TABLE city_troops (
        city_id INTEGER NOT NULL REFERENCES cities (id),
        kind    TEXT    NOT NULL,
        qty     INTEGER NOT NULL CHECK (qty >= 0),
        PRIMARY KEY (city_id, kind)
    );
    CREATE TABLE city_traps (
        city_id INTEGER NOT NULL REFERENCES cities (id),
        kind    TEXT    NOT NULL,
        qty     INTEGER NOT NULL CHECK (qty >= 0),
        PRIMARY KEY (city_id, kind)
    );
    CREATE TABLE city_training (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        city_id  INTEGER NOT NULL REFERENCES cities (id),
        kind     TEXT    NOT NULL,
        qty      INTEGER NOT NULL,
        ready_at INTEGER NOT NULL
    );
    CREATE INDEX idx_city_training_city ON city_training (city_id, ready_at);
    CREATE TABLE city_search (
        player_id  INTEGER PRIMARY KEY REFERENCES players (id),
        target_id  INTEGER NOT NULL,
        snapshot   TEXT    NOT NULL,
        selection  TEXT    NOT NULL DEFAULT '{}',
        seen       TEXT    NOT NULL DEFAULT '[]',
        created_at INTEGER NOT NULL,
        used       INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE city_attacks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        attacker_city INTEGER NOT NULL,
        defender_city INTEGER NOT NULL,
        attacker_pid  INTEGER NOT NULL,
        defender_pid  INTEGER NOT NULL,
        attacker_name TEXT    NOT NULL,
        defender_name TEXT    NOT NULL,
        stars         INTEGER NOT NULL,
        destruction   REAL    NOT NULL,
        data          TEXT    NOT NULL,
        att_trophies  INTEGER NOT NULL,
        def_trophies  INTEGER NOT NULL,
        shield        INTEGER NOT NULL,
        created_at    INTEGER NOT NULL,
        seen          INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_city_attacks_att ON city_attacks (attacker_pid, id);
    CREATE INDEX idx_city_attacks_def ON city_attacks (defender_pid, seen, id);
    CREATE INDEX idx_city_attacks_pair ON city_attacks (attacker_city, defender_city, created_at);
    """,
    # 44: messages the realm sends on its own (hunger, full storage, finished training, ended shields)
    """
    CREATE TABLE city_alerts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        city_id    INTEGER NOT NULL REFERENCES cities (id),
        key        TEXT    NOT NULL,
        text       TEXT    NOT NULL,
        created_at INTEGER NOT NULL,
        sent       INTEGER NOT NULL DEFAULT 0,
        UNIQUE (city_id, key)
    );
    CREATE INDEX idx_city_alerts_unsent ON city_alerts (sent, id);
    """,
    # 45: timed construction (rushed with crystals) and the alert switch
    """
    ALTER TABLE cities ADD COLUMN alerts INTEGER NOT NULL DEFAULT 1;
    CREATE TABLE city_builds (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        city_id  INTEGER NOT NULL REFERENCES cities (id),
        kind     TEXT    NOT NULL,
        level    INTEGER NOT NULL,
        ready_at INTEGER NOT NULL
    );
    CREATE INDEX idx_city_builds_city ON city_builds (city_id, ready_at);
    """,
    # 46: treasury packs bought as a gift for another hero (and how many of them)
    """
    ALTER TABLE orders ADD COLUMN gift_to INTEGER REFERENCES players (id);
    ALTER TABLE orders ADD COLUMN qty INTEGER NOT NULL DEFAULT 1;
    """,
    # 47: the free daily spin of the wheel
    """
    ALTER TABLE players ADD COLUMN free_spin_day INTEGER NOT NULL DEFAULT 0;
    """,
    # 48: the heroes' own messages (queued, keyed, sent once) and the city treasury withdrawal limit
    """
    CREATE TABLE player_alerts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id  INTEGER NOT NULL REFERENCES players (id),
        key        TEXT    NOT NULL,
        text       TEXT    NOT NULL,
        screen     TEXT    NOT NULL DEFAULT '',
        arg        TEXT    NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        sent       INTEGER NOT NULL DEFAULT 0,
        UNIQUE (player_id, key)
    );
    CREATE INDEX idx_player_alerts_unsent ON player_alerts (sent, id);
    ALTER TABLE cities ADD COLUMN withdraw_day INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE cities ADD COLUMN withdrawn INTEGER NOT NULL DEFAULT 0;
    """,
    # 49: solo play (the fight in progress, story/dungeon/boss progress and daily counters)
    """
    CREATE TABLE solo_fights (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id  INTEGER NOT NULL REFERENCES players (id),
        kind       TEXT    NOT NULL,
        status     TEXT    NOT NULL,
        state      TEXT    NOT NULL,
        info       TEXT    NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE INDEX idx_solo_fights_player ON solo_fights (player_id, status);
    CREATE TABLE solo_progress (
        player_id INTEGER NOT NULL REFERENCES players (id),
        key       TEXT    NOT NULL,
        n         INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, key)
    );
    CREATE TABLE solo_daily (
        player_id INTEGER NOT NULL REFERENCES players (id),
        day       INTEGER NOT NULL,
        key       TEXT    NOT NULL,
        n         INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, day, key)
    );
    """,
    # 50: the eternal maze (one run in progress per hero)
    """
    CREATE TABLE maze_runs (
        player_id INTEGER PRIMARY KEY REFERENCES players (id),
        floor     INTEGER NOT NULL,
        hp        REAL    NOT NULL,
        buffs     TEXT    NOT NULL,
        gold      INTEGER NOT NULL DEFAULT 0,
        xp        INTEGER NOT NULL DEFAULT 0,
        options   TEXT    NOT NULL,
        started   INTEGER NOT NULL
    );
    """,
    # 51: expeditions (the hero away for hours)
    """
    CREATE TABLE expeditions (
        player_id  INTEGER PRIMARY KEY REFERENCES players (id),
        kind       TEXT    NOT NULL,
        started_at INTEGER NOT NULL,
        ends_at    INTEGER NOT NULL,
        hours      INTEGER NOT NULL
    );
    """,
    # 52: the living world (region darkness, world events and each hero's share)
    """
    CREATE TABLE world_regions (
        id       TEXT PRIMARY KEY,
        darkness REAL    NOT NULL,
        calc     INTEGER NOT NULL
    );
    CREATE TABLE world_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        kind       TEXT    NOT NULL,
        region     TEXT    NOT NULL,
        foe        TEXT    NOT NULL,
        max_points INTEGER NOT NULL,
        points     INTEGER NOT NULL DEFAULT 0,
        starts_at  INTEGER NOT NULL,
        ends_at    INTEGER NOT NULL,
        status     TEXT    NOT NULL
    );
    CREATE INDEX idx_world_events_status ON world_events (status, id);
    CREATE TABLE world_contrib (
        event_id  INTEGER NOT NULL REFERENCES world_events (id),
        player_id INTEGER NOT NULL REFERENCES players (id),
        points    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (event_id, player_id)
    );
    """,
    # 53: declared wars between two clans (the clan names are copied, a clan may be gone when the war is read later)
    """
    CREATE TABLE clan_wars (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        attacker_id   INTEGER NOT NULL,
        defender_id   INTEGER NOT NULL,
        attacker_name TEXT    NOT NULL,
        defender_name TEXT    NOT NULL,
        stake         INTEGER NOT NULL DEFAULT 0,
        status        TEXT    NOT NULL,
        winner_id     INTEGER NOT NULL DEFAULT 0,
        created_at    INTEGER NOT NULL,
        starts_at     INTEGER NOT NULL DEFAULT 0,
        ends_at       INTEGER NOT NULL
    );
    CREATE INDEX idx_clan_wars_status ON clan_wars (status, ends_at);
    CREATE TABLE clan_war_attacks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        war_id        INTEGER NOT NULL REFERENCES clan_wars (id),
        clan_id       INTEGER NOT NULL,
        attacker_id   INTEGER NOT NULL,
        attacker_name TEXT    NOT NULL,
        target_id     INTEGER NOT NULL,
        target_name   TEXT    NOT NULL,
        stars         INTEGER NOT NULL,
        at            INTEGER NOT NULL
    );
    CREATE INDEX idx_clan_war_attacks_war ON clan_war_attacks (war_id, clan_id);
    """,
    # 54: what each member of a finished clan war may collect with the button in the result message
    """
    CREATE TABLE clan_war_rewards (
        war_id    INTEGER NOT NULL REFERENCES clan_wars (id),
        player_id INTEGER NOT NULL,
        clan_id   INTEGER NOT NULL,
        gold      INTEGER NOT NULL DEFAULT 0,
        khan      INTEGER NOT NULL DEFAULT 0,
        chest     TEXT    NOT NULL DEFAULT '',
        fought    INTEGER NOT NULL DEFAULT 0,
        claimed   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (war_id, player_id)
    );
    """,
    # 55: realm-wide events: the event, the heroes who joined (with the private message that counts down for them) and
    # the group messages that announce it
    """
    CREATE TABLE raids (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        kind       TEXT    NOT NULL,
        status     TEXT    NOT NULL,
        created_at INTEGER NOT NULL,
        starts_at  INTEGER NOT NULL,
        ended_at   INTEGER NOT NULL DEFAULT 0,
        summary    TEXT    NOT NULL DEFAULT '{}'
    );
    CREATE INDEX idx_raids_status ON raids (status, starts_at);
    CREATE TABLE raid_players (
        raid_id    INTEGER NOT NULL REFERENCES raids (id),
        player_id  INTEGER NOT NULL REFERENCES players (id),
        joined_at  INTEGER NOT NULL,
        dm_message INTEGER NOT NULL DEFAULT 0,
        score      INTEGER NOT NULL DEFAULT 0,
        gold       INTEGER NOT NULL DEFAULT 0,
        xp         INTEGER NOT NULL DEFAULT 0,
        crystal    INTEGER NOT NULL DEFAULT 0,
        rank       INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (raid_id, player_id)
    );
    CREATE TABLE raid_posts (
        raid_id    INTEGER NOT NULL REFERENCES raids (id),
        chat_id    INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        PRIMARY KEY (raid_id, chat_id)
    );
    """,
    # 56: habits that bring heroes back: weeks of missions, ranked seasons, titles, group goals, friends, sellers, pop-ups
    """
    CREATE TABLE mission_days (
        player_id INTEGER NOT NULL REFERENCES players (id),
        day       INTEGER NOT NULL,
        PRIMARY KEY (player_id, day)
    );
    CREATE TABLE mission_week_claims (
        player_id INTEGER NOT NULL REFERENCES players (id),
        week      INTEGER NOT NULL,
        PRIMARY KEY (player_id, week)
    );
    CREATE TABLE rank_scores (
        season    INTEGER NOT NULL,
        player_id INTEGER NOT NULL REFERENCES players (id),
        score     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (season, player_id)
    );
    CREATE INDEX idx_rank_scores_top ON rank_scores (season, score DESC);
    CREATE TABLE player_titles (
        player_id INTEGER NOT NULL REFERENCES players (id),
        key       TEXT    NOT NULL,
        text      TEXT    NOT NULL,
        at        INTEGER NOT NULL,
        PRIMARY KEY (player_id, key)
    );
    CREATE TABLE group_goal_hits (
        chat_id   INTEGER NOT NULL,
        week      INTEGER NOT NULL,
        player_id INTEGER NOT NULL REFERENCES players (id),
        n         INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (chat_id, week, player_id)
    );
    CREATE TABLE group_goals (
        chat_id INTEGER NOT NULL,
        week    INTEGER NOT NULL,
        target  INTEGER NOT NULL,
        done    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (chat_id, week)
    );
    CREATE TABLE friends (
        player_id INTEGER NOT NULL REFERENCES players (id),
        friend_id INTEGER NOT NULL REFERENCES players (id),
        status    TEXT    NOT NULL,
        at        INTEGER NOT NULL,
        PRIMARY KEY (player_id, friend_id)
    );
    CREATE TABLE friend_gifts (
        sender_id INTEGER NOT NULL,
        friend_id INTEGER NOT NULL,
        day       INTEGER NOT NULL,
        PRIMARY KEY (sender_id, friend_id, day)
    );
    CREATE TABLE market_sales (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        amount    INTEGER NOT NULL,
        at        INTEGER NOT NULL
    );
    CREATE INDEX idx_market_sales_at ON market_sales (at, seller_id);
    CREATE TABLE popups (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id  INTEGER NOT NULL REFERENCES players (id),
        kind       TEXT    NOT NULL,
        status     TEXT    NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    );
    CREATE INDEX idx_popups_player ON popups (player_id, status, created_at);
    """,
    # 57: the small thank-you boxes a clan finds when one of its members buys something with real money
    """
    CREATE TABLE clan_gift_boxes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id  INTEGER NOT NULL REFERENCES players (id),
        from_id    INTEGER NOT NULL,
        from_name  TEXT    NOT NULL,
        clan_name  TEXT    NOT NULL,
        tier       INTEGER NOT NULL,
        status     TEXT    NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX idx_clan_gift_boxes_player ON clan_gift_boxes (player_id, created_at);
    """,
    # 58: a member asks the clan's owner for gold out of the clan treasury; the owner approves or rejects it
    """
    CREATE TABLE clan_withdrawals (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        clan_id    INTEGER NOT NULL,
        player_id  INTEGER NOT NULL REFERENCES players (id),
        amount     INTEGER NOT NULL CHECK (amount > 0),
        status     TEXT    NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
        created_at INTEGER NOT NULL,
        decided_at INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_clan_withdrawals_clan ON clan_withdrawals (clan_id, status, created_at);
    CREATE INDEX idx_clan_withdrawals_player ON clan_withdrawals (player_id, status);
    """,
    # 59: hero war gear (the four-piece loadout and the pieces a hero owns)
    """
    CREATE TABLE arms_owned (
        player_id INTEGER NOT NULL REFERENCES players (id),
        arm_id    TEXT    NOT NULL,
        qty       INTEGER NOT NULL CHECK (qty >= 0),
        PRIMARY KEY (player_id, arm_id)
    );
    CREATE TABLE arms_equipped (
        player_id INTEGER NOT NULL REFERENCES players (id),
        slot      INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 4),
        arm_id    TEXT    NOT NULL,
        PRIMARY KEY (player_id, slot),
        UNIQUE (player_id, arm_id)
    );
    """,
    # 60: attribute points, class talents and the +1..+10 upgrade of war gear
    """
    CREATE TABLE hero_attrs (
        player_id INTEGER NOT NULL REFERENCES players (id),
        attr      TEXT    NOT NULL,
        pts       INTEGER NOT NULL CHECK (pts >= 0),
        PRIMARY KEY (player_id, attr)
    );
    CREATE TABLE hero_talents (
        player_id INTEGER NOT NULL REFERENCES players (id),
        talent_id TEXT    NOT NULL,
        PRIMARY KEY (player_id, talent_id)
    );
    CREATE TABLE arms_upgrades (
        player_id INTEGER NOT NULL REFERENCES players (id),
        arm_id    TEXT    NOT NULL,
        lvl       INTEGER NOT NULL CHECK (lvl BETWEEN 0 AND 10),
        PRIMARY KEY (player_id, arm_id)
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
