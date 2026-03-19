"""
DB Manager
SQLite persistence for all D&D game data.

Connection path: DND_DB_PATH env var, or dnd_game.db next to this file.
  set DND_DB_PATH=C:\other\path\dnd_game.db   (Windows)
  export DND_DB_PATH=/other/path/dnd_game.db   (Linux/Mac)
"""

import os
import json
import logging
import sqlite3
from datetime import datetime
from contextlib import contextmanager

log = logging.getLogger("dnd.db")

# ── Connection ─────────────────────────────────────────────────────────────────

DB_PATH = os.environ.get(
    "DND_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dnd_game.db"),
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Schema ─────────────────────────────────────────────────────────────────────

def init_db():
    """Create tables and run migrations. Safe to call on every startup."""
    with _conn() as con:
        # ── New tables (campaigns first — others reference it) ──
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            email               TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash       TEXT    NOT NULL DEFAULT '',
            created_at          TEXT    NOT NULL DEFAULT '',
            subscription_status TEXT    NOT NULL DEFAULT 'free',
            stripe_customer_id  TEXT    DEFAULT NULL,
            stripe_sub_id       TEXT    DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

        CREATE TABLE IF NOT EXISTS campaigns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    UNIQUE NOT NULL,
            description TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS characters (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id   INTEGER NOT NULL DEFAULT 0
                              REFERENCES campaigns(id) ON DELETE CASCADE,
            name          TEXT    NOT NULL,
            char_group    TEXT    DEFAULT '',
            race          TEXT    DEFAULT '',
            char_class    TEXT    DEFAULT '',
            subclass      TEXT    DEFAULT '',
            level         INTEGER DEFAULT 1,
            profession    TEXT    DEFAULT '',
            hp            INTEGER DEFAULT 0,
            max_hp        INTEGER DEFAULT 0,
            ki_points     TEXT    DEFAULT '',
            ac            INTEGER DEFAULT 0,
            speed         TEXT    DEFAULT '',
            initiative    TEXT    DEFAULT '',
            status        TEXT    DEFAULT '',
            gold          INTEGER DEFAULT 0,
            buffs         TEXT    DEFAULT '[]',
            debuffs       TEXT    DEFAULT '[]',
            str_score     INTEGER DEFAULT 0,
            dex_score     INTEGER DEFAULT 0,
            con_score     INTEGER DEFAULT 0,
            int_score     INTEGER DEFAULT 0,
            wis_score     INTEGER DEFAULT 0,
            cha_score     INTEGER DEFAULT 0,
            sending_stone TEXT    DEFAULT '',
            items         TEXT    DEFAULT '[]',
            spells        TEXT    DEFAULT '[]',
            location      TEXT    DEFAULT '',
            notes         TEXT    DEFAULT '',
            updated_at    TEXT    DEFAULT '',
            UNIQUE (campaign_id, name)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_key TEXT    PRIMARY KEY,
            campaign_id INTEGER NOT NULL DEFAULT 0
                            REFERENCES campaigns(id) ON DELETE CASCADE,
            name        TEXT    DEFAULT '',
            last_saved  TEXT    DEFAULT '',
            turn        INTEGER DEFAULT 0,
            game_date   TEXT    DEFAULT '',
            location    TEXT    DEFAULT '',
            gold          INTEGER DEFAULT 0,
            xp            INTEGER DEFAULT 0,
            history       TEXT    DEFAULT '[]',
            created_at    TEXT    DEFAULT '',
            combat_active INTEGER DEFAULT 0,
            session_mode  TEXT    DEFAULT 'narrative',
            party_loot    TEXT    DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS chronicle (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT    DEFAULT '',
            campaign_id INTEGER DEFAULT 0,
            sync_id     TEXT    DEFAULT '',
            game_date   TEXT    DEFAULT '',
            player_text TEXT    DEFAULT '',
            dm_text     TEXT    DEFAULT '',
            user_raw    TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS maps (
            name        TEXT    PRIMARY KEY,
            campaign_id INTEGER DEFAULT 0,
            description TEXT    DEFAULT '',
            data        TEXT    DEFAULT '{}',
            updated_at  TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS story (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT    DEFAULT '',
            campaign_id INTEGER DEFAULT 0,
            sync_id     TEXT    DEFAULT '',
            game_date   TEXT    DEFAULT '',
            narrative   TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS game_state (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            sync_id    TEXT    DEFAULT '',
            game_date  TEXT    DEFAULT '',
            location   TEXT    DEFAULT '',
            gold       INTEGER DEFAULT 0,
            xp         INTEGER DEFAULT 0,
            updated_at TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS spells_reference (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL UNIQUE,
            level         INTEGER DEFAULT 0,
            school        TEXT    DEFAULT '',
            casting_time  TEXT    DEFAULT '',
            spell_range   TEXT    DEFAULT '',
            components    TEXT    DEFAULT '',
            duration      TEXT    DEFAULT '',
            concentration INTEGER DEFAULT 0,
            ritual        INTEGER DEFAULT 0,
            save_type     TEXT    DEFAULT '',
            classes       TEXT    DEFAULT '[]',
            source        TEXT    DEFAULT 'SRD',
            enabled       INTEGER DEFAULT 1,
            description   TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS calendar (
            day_of_year   INTEGER PRIMARY KEY,
            season        TEXT    DEFAULT '',
            month_name    TEXT    DEFAULT '',
            month_short   TEXT    DEFAULT '',
            day_of_month  INTEGER DEFAULT 0,
            is_festival   INTEGER DEFAULT 0,
            is_leap_day   INTEGER DEFAULT 0,
            festival_name TEXT    DEFAULT '',
            notes         TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS character_spellbook (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL DEFAULT 0,
            char_name   TEXT    NOT NULL,
            spell_id    INTEGER NOT NULL REFERENCES spells_reference(id) ON DELETE CASCADE,
            prepared    INTEGER DEFAULT 0,
            notes       TEXT    DEFAULT '',
            UNIQUE(campaign_id, char_name, spell_id)
        );

        CREATE TABLE IF NOT EXISTS npcs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id      INTEGER NOT NULL DEFAULT 0
                                 REFERENCES campaigns(id) ON DELETE CASCADE,
            name             TEXT    NOT NULL,
            npc_type         TEXT    DEFAULT '',
            attitude         INTEGER DEFAULT 0,
            faction          TEXT    DEFAULT '',
            location         TEXT    DEFAULT '',
            notes            TEXT    DEFAULT '',
            last_seen_date   TEXT    DEFAULT '',
            last_seen_loc    TEXT    DEFAULT '',
            updated_at       TEXT    DEFAULT '',
            is_store         INTEGER DEFAULT 0,
            UNIQUE(campaign_id, name)
        );

        CREATE TABLE IF NOT EXISTS npc_offers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            npc_id       INTEGER NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            campaign_id  INTEGER NOT NULL DEFAULT 0,
            offer_type   TEXT    NOT NULL DEFAULT 'item',
            title        TEXT    NOT NULL DEFAULT '',
            description  TEXT    DEFAULT '',
            price_gp     INTEGER DEFAULT NULL,
            status       TEXT    DEFAULT 'active',
            created_date TEXT    DEFAULT '',
            expires_date TEXT    DEFAULT '',
            created_at   TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS npc_affinity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL DEFAULT 0,
            npc_id      INTEGER NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            char_name   TEXT    NOT NULL,
            score       INTEGER DEFAULT 0,
            updated_at  TEXT    DEFAULT '',
            UNIQUE(campaign_id, npc_id, char_name)
        );

        CREATE TABLE IF NOT EXISTS organizations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id  INTEGER NOT NULL DEFAULT 0,
            name         TEXT    NOT NULL,
            org_type     TEXT    DEFAULT '',
            description  TEXT    DEFAULT '',
            headquarters TEXT    DEFAULT '',
            notes        TEXT    DEFAULT '',
            updated_at   TEXT    DEFAULT '',
            UNIQUE(campaign_id, name)
        );

        CREATE TABLE IF NOT EXISTS org_members (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            campaign_id INTEGER NOT NULL DEFAULT 0,
            entity_type TEXT    NOT NULL,
            entity_ref  TEXT    NOT NULL,
            rank        TEXT    DEFAULT '',
            UNIQUE(org_id, entity_type, entity_ref)
        );

        CREATE TABLE IF NOT EXISTS org_affinity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL DEFAULT 0,
            org_id_a    INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            org_id_b    INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            score       INTEGER DEFAULT 0,
            updated_at  TEXT    DEFAULT '',
            UNIQUE(campaign_id, org_id_a, org_id_b)
        );

        CREATE TABLE IF NOT EXISTS players (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name   TEXT    NOT NULL DEFAULT '',
            created_at     TEXT    DEFAULT '',
            last_seen      TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS player_tokens (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            token          TEXT    NOT NULL UNIQUE,
            campaign_id    INTEGER NOT NULL DEFAULT 0,
            character_name TEXT    NOT NULL DEFAULT '',
            player_id      INTEGER REFERENCES players(id),
            created_at     TEXT    DEFAULT '',
            last_seen      TEXT    DEFAULT '',
            is_active      INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS round_submissions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key    TEXT    NOT NULL,
            round_num      INTEGER NOT NULL DEFAULT 1,
            character_name TEXT    NOT NULL,
            action_text    TEXT    NOT NULL DEFAULT '',
            submitted_at   TEXT    DEFAULT '',
            UNIQUE(session_key, round_num, character_name)
        );

        CREATE TABLE IF NOT EXISTS roleplay_threads (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key    TEXT    NOT NULL,
            character_name TEXT    NOT NULL,
            npc_id         INTEGER,
            history        TEXT    DEFAULT '[]',
            is_active      INTEGER DEFAULT 0,
            started_at     TEXT    DEFAULT '',
            ended_at       TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS player_messages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key    TEXT    NOT NULL,
            from_character TEXT    NOT NULL,
            to_character   TEXT    NOT NULL,
            message        TEXT    NOT NULL DEFAULT '',
            sent_at        TEXT    DEFAULT '',
            read           INTEGER DEFAULT 0
        );
        """)
        _migrate(con)
    log.info("DB ready: %s", DB_PATH)


def _migrate(con):
    """Add columns to existing tables when upgrading from older schema versions."""
    def has_column(table, col):
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r["name"] == col for r in rows)

    def table_exists(name):
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    # If old characters table exists (name TEXT PRIMARY KEY, no campaign_id)
    # migrate it to new schema under a placeholder campaign
    if table_exists("characters") and not has_column("characters", "campaign_id"):
        log.info("Migrating characters table to campaign-aware schema...")
        # Create placeholder campaign for orphaned data
        con.execute("""
            INSERT OR IGNORE INTO campaigns (id, name, description, created_at)
            VALUES (0, 'Legacy', 'Pre-campaign data', ?)
        """, (datetime.now().isoformat(),))
        # Rebuild table with campaign_id
        con.executescript("""
            ALTER TABLE characters RENAME TO _characters_old;
            CREATE TABLE characters (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id   INTEGER NOT NULL DEFAULT 0,
                name          TEXT    NOT NULL,
                char_group    TEXT    DEFAULT '',
                race          TEXT    DEFAULT '',
                char_class    TEXT    DEFAULT '',
                subclass      TEXT    DEFAULT '',
                level         INTEGER DEFAULT 1,
                profession    TEXT    DEFAULT '',
                hp            INTEGER DEFAULT 0,
                max_hp        INTEGER DEFAULT 0,
                ki_points     TEXT    DEFAULT '',
                ac            INTEGER DEFAULT 0,
                speed         TEXT    DEFAULT '',
                initiative    TEXT    DEFAULT '',
                status        TEXT    DEFAULT '',
                gold          INTEGER DEFAULT 0,
                buffs         TEXT    DEFAULT '[]',
                debuffs       TEXT    DEFAULT '[]',
                str_score     INTEGER DEFAULT 0,
                dex_score     INTEGER DEFAULT 0,
                con_score     INTEGER DEFAULT 0,
                int_score     INTEGER DEFAULT 0,
                wis_score     INTEGER DEFAULT 0,
                cha_score     INTEGER DEFAULT 0,
                sending_stone TEXT    DEFAULT '',
                items         TEXT    DEFAULT '[]',
                spells        TEXT    DEFAULT '[]',
                notes         TEXT    DEFAULT '',
                updated_at    TEXT    DEFAULT '',
                UNIQUE (campaign_id, name)
            );
            INSERT INTO characters
                (campaign_id, name, char_group, race, char_class, subclass, level,
                 profession, hp, max_hp, ki_points, ac, speed, initiative, status,
                 gold, buffs, debuffs, str_score, dex_score, con_score, int_score,
                 wis_score, cha_score, sending_stone, items, notes, updated_at)
            SELECT
                0, name, char_group, race, char_class, subclass, level,
                profession, hp, max_hp, ki_points, ac, speed, initiative, status,
                gold, buffs, debuffs, str_score, dex_score, con_score, int_score,
                wis_score, cha_score, sending_stone, items, notes, updated_at
            FROM _characters_old;
            DROP TABLE _characters_old;
        """)

    # Add campaign_id to sessions if missing
    if table_exists("sessions") and not has_column("sessions", "campaign_id"):
        con.execute("ALTER TABLE sessions ADD COLUMN campaign_id INTEGER DEFAULT 0")

    # Add name to sessions if missing (friendly session name)
    if table_exists("sessions") and not has_column("sessions", "name"):
        con.execute("ALTER TABLE sessions ADD COLUMN name TEXT DEFAULT ''")

    # Add campaign_id to chronicle if missing
    if table_exists("chronicle") and not has_column("chronicle", "campaign_id"):
        con.execute("ALTER TABLE chronicle ADD COLUMN campaign_id INTEGER DEFAULT 0")

    # Add campaign_id to maps if missing
    if table_exists("maps") and not has_column("maps", "campaign_id"):
        con.execute("ALTER TABLE maps ADD COLUMN campaign_id INTEGER DEFAULT 0")

    # Add campaign_id to story if missing
    if table_exists("story") and not has_column("story", "campaign_id"):
        con.execute("ALTER TABLE story ADD COLUMN campaign_id INTEGER DEFAULT 0")

    # Add spells column to characters if missing (legacy item spells JSON)
    if table_exists("characters") and not has_column("characters", "spells"):
        con.execute("ALTER TABLE characters ADD COLUMN spells TEXT DEFAULT '[]'")

    # Add location to characters if missing
    if table_exists("characters") and not has_column("characters", "location"):
        con.execute("ALTER TABLE characters ADD COLUMN location TEXT DEFAULT ''")

    # Add is_npc to characters if missing
    if table_exists("characters") and not has_column("characters", "is_npc"):
        con.execute("ALTER TABLE characters ADD COLUMN is_npc INTEGER DEFAULT 0")

    # Add nickname and rp_notes to characters if missing
    if table_exists("characters") and not has_column("characters", "nickname"):
        con.execute("ALTER TABLE characters ADD COLUMN nickname TEXT DEFAULT ''")
    if table_exists("characters") and not has_column("characters", "rp_notes"):
        con.execute("ALTER TABLE characters ADD COLUMN rp_notes TEXT DEFAULT ''")
    if table_exists("characters") and not has_column("characters", "portrait_path"):
        con.execute("ALTER TABLE characters ADD COLUMN portrait_path TEXT DEFAULT ''")
    if table_exists("characters") and not has_column("characters", "classes"):
        con.execute("ALTER TABLE characters ADD COLUMN classes TEXT DEFAULT '[]'")
    if table_exists("mobs") and not has_column("mobs", "languages"):
        con.execute("ALTER TABLE mobs ADD COLUMN languages TEXT DEFAULT ''")
    if table_exists("mobs") and not has_column("mobs", "image_path"):
        con.execute("ALTER TABLE mobs ADD COLUMN image_path TEXT DEFAULT ''")

    # Add player_id to characters if missing
    if table_exists("characters") and not has_column("characters", "player_id"):
        con.execute("ALTER TABLE characters ADD COLUMN player_id INTEGER REFERENCES players(id)")

    # Rebuild player_tokens to make character_name nullable and add player_id
    if table_exists("player_tokens") and not has_column("player_tokens", "player_id"):
        con.executescript("""
            ALTER TABLE player_tokens RENAME TO _player_tokens_old;
            CREATE TABLE player_tokens (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                token          TEXT    NOT NULL UNIQUE,
                campaign_id    INTEGER NOT NULL DEFAULT 0,
                character_name TEXT    NOT NULL DEFAULT '',
                player_id      INTEGER REFERENCES players(id),
                created_at     TEXT    DEFAULT '',
                last_seen      TEXT    DEFAULT '',
                is_active      INTEGER DEFAULT 1
            );
            INSERT INTO player_tokens (id, token, campaign_id, character_name, created_at, last_seen, is_active)
            SELECT id, token, campaign_id, character_name, created_at, last_seen, is_active
            FROM _player_tokens_old;
            DROP TABLE _player_tokens_old;
        """)

    # Add is_store to npcs if missing
    if table_exists("npcs") and not has_column("npcs", "is_store"):
        con.execute("ALTER TABLE npcs ADD COLUMN is_store INTEGER DEFAULT 0")

    # Add combat state columns to sessions if missing
    if table_exists("sessions") and not has_column("sessions", "combat_active"):
        con.execute("ALTER TABLE sessions ADD COLUMN combat_active INTEGER DEFAULT 0")
    if table_exists("sessions") and not has_column("sessions", "session_mode"):
        con.execute("ALTER TABLE sessions ADD COLUMN session_mode TEXT DEFAULT 'narrative'")
    if table_exists("sessions") and not has_column("sessions", "combat_ui_state"):
        con.execute("ALTER TABLE sessions ADD COLUMN combat_ui_state TEXT DEFAULT '{}'")
    if table_exists("sessions") and not has_column("sessions", "party_loot"):
        con.execute("ALTER TABLE sessions ADD COLUMN party_loot TEXT DEFAULT '[]'")

    # Add user_id to campaigns and characters for multi-user support
    if table_exists("campaigns") and not has_column("campaigns", "user_id"):
        con.execute("ALTER TABLE campaigns ADD COLUMN user_id INTEGER REFERENCES users(id)")
    if table_exists("characters") and not has_column("characters", "user_id"):
        con.execute("ALTER TABLE characters ADD COLUMN user_id INTEGER REFERENCES users(id)")

    # User activity tracking
    if table_exists("users") and not has_column("users", "last_login"):
        con.execute("ALTER TABLE users ADD COLUMN last_login TEXT DEFAULT NULL")
    if table_exists("api_usage_log") and not has_column("api_usage_log", "user_id"):
        con.execute("ALTER TABLE api_usage_log ADD COLUMN user_id INTEGER DEFAULT NULL REFERENCES users(id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_usage_user ON api_usage_log(user_id)")

    # Magic items reference table
    con.execute("""
    CREATE TABLE IF NOT EXISTS magic_items (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        name                TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        category            TEXT    DEFAULT '',
        rarity              TEXT    DEFAULT 'common',
        requires_attunement INTEGER DEFAULT 0,
        attunement_by       TEXT    DEFAULT '',
        effect              TEXT    DEFAULT '',
        stat_set_str        INTEGER DEFAULT 0,
        stat_set_dex        INTEGER DEFAULT 0,
        stat_set_con        INTEGER DEFAULT 0,
        stat_set_int        INTEGER DEFAULT 0,
        stat_set_wis        INTEGER DEFAULT 0,
        stat_set_cha        INTEGER DEFAULT 0,
        stat_bonus_str      INTEGER DEFAULT 0,
        stat_bonus_dex      INTEGER DEFAULT 0,
        stat_bonus_con      INTEGER DEFAULT 0,
        stat_bonus_int      INTEGER DEFAULT 0,
        stat_bonus_wis      INTEGER DEFAULT 0,
        stat_bonus_cha      INTEGER DEFAULT 0,
        ac_bonus            INTEGER DEFAULT 0,
        attack_bonus        INTEGER DEFAULT 0,
        value_gp            INTEGER DEFAULT 0,
        source              TEXT    DEFAULT 'DMG'
    )
    """)

    # Mobs and mundane items reference tables
    con.executescript("""
    CREATE TABLE IF NOT EXISTS mobs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        description     TEXT    DEFAULT '',
        ac              INTEGER DEFAULT 0,
        hp_formula      TEXT    DEFAULT '',
        hp_avg          INTEGER DEFAULT 0,
        speed           TEXT    DEFAULT '',
        str             INTEGER DEFAULT 10,
        dex             INTEGER DEFAULT 10,
        con             INTEGER DEFAULT 10,
        int             INTEGER DEFAULT 10,
        wis             INTEGER DEFAULT 10,
        cha             INTEGER DEFAULT 10,
        challenge       TEXT    DEFAULT '',
        xp              INTEGER DEFAULT 0,
        size            TEXT    DEFAULT '',
        mob_type        TEXT    DEFAULT '',
        alignment       TEXT    DEFAULT '',
        melee_mod       TEXT    DEFAULT '',
        ranged_mod      TEXT    DEFAULT '',
        attack1         TEXT    DEFAULT '',
        attack1_range   TEXT    DEFAULT '',
        attack1_dmg     TEXT    DEFAULT '',
        attack2         TEXT    DEFAULT '',
        attack2_range   TEXT    DEFAULT '',
        attack2_dmg     TEXT    DEFAULT '',
        attack3         TEXT    DEFAULT '',
        attack3_range   TEXT    DEFAULT '',
        attack3_dmg     TEXT    DEFAULT '',
        source          TEXT    DEFAULT '',
        notes           TEXT    DEFAULT '',
        languages       TEXT    DEFAULT '',
        image_path      TEXT    DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS mundane_items (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        category        TEXT    DEFAULT '',
        subcategory     TEXT    DEFAULT '',
        store_types     TEXT    DEFAULT '',
        cost_gp         REAL    DEFAULT 0,
        weight_lb       REAL    DEFAULT 0,
        damage          TEXT    DEFAULT '',
        damage_type     TEXT    DEFAULT '',
        properties      TEXT    DEFAULT '',
        armor_class     TEXT    DEFAULT '',
        str_requirement INTEGER DEFAULT 0,
        stealth_disadv  INTEGER DEFAULT 0,
        capacity        TEXT    DEFAULT '',
        speed           TEXT    DEFAULT '',
        description     TEXT    DEFAULT ''
    )
    """)

    con.executescript("""
    CREATE TABLE IF NOT EXISTS mob_knowledge (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id  INTEGER NOT NULL DEFAULT 0,
        mob_name     TEXT    NOT NULL COLLATE NOCASE,
        knowledge_rank TEXT  DEFAULT 'unknown',
        notes        TEXT    DEFAULT '',
        UNIQUE(campaign_id, mob_name)
    );
    """)

    con.executescript("""
    CREATE TABLE IF NOT EXISTS campaign_mob_overrides (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        mob_name    TEXT    NOT NULL COLLATE NOCASE,
        image_path  TEXT    DEFAULT NULL,
        description TEXT    DEFAULT NULL,
        notes       TEXT    DEFAULT NULL,
        UNIQUE(campaign_id, mob_name)
    );
    CREATE TABLE IF NOT EXISTS campaign_spell_overrides (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        spell_id    INTEGER NOT NULL REFERENCES spells_reference(id) ON DELETE CASCADE,
        enabled     INTEGER DEFAULT NULL,
        description TEXT    DEFAULT NULL,
        notes       TEXT    DEFAULT NULL,
        UNIQUE(campaign_id, spell_id)
    );
    """)

    con.executescript("""
    CREATE TABLE IF NOT EXISTS api_usage_log (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key    TEXT    NOT NULL DEFAULT '',
        campaign_id    INTEGER NOT NULL DEFAULT 0,
        call_type      TEXT    NOT NULL DEFAULT '',
        model          TEXT    NOT NULL DEFAULT '',
        prompt_tokens  INTEGER NOT NULL DEFAULT 0,
        output_tokens  INTEGER NOT NULL DEFAULT 0,
        total_tokens   INTEGER NOT NULL DEFAULT 0,
        called_at      TEXT    NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_usage_session ON api_usage_log(session_key);
    CREATE INDEX IF NOT EXISTS idx_usage_called  ON api_usage_log(called_at);
    """)

    # Seed PHB Lifestyle Expenses into mundane_items (one-time, skipped if already present)
    if table_exists("mundane_items") and not con.execute(
        "SELECT 1 FROM mundane_items WHERE category='Lifestyle' LIMIT 1"
    ).fetchone():
        _LIFESTYLE_ITEMS = [
            # (name, subcategory, cost_gp, description)
            ("Wretched Lodging",     "Wretched",     0.00,
             "Miserable and desperate. No shelter — sleeping rough, under bridges, or in alleys. "
             "Includes no meals; you scavenge or beg."),
            ("Squalid Lodging",      "Squalid",      0.10,
             "A place among vermin in a flea-ridden boarding house or a filthy stable corner. "
             "Rotten food, stinking water. 1 sp/night. PHB lifestyle: Squalid."),
            ("Poor Lodging",         "Poor",         0.20,
             "A leaky stable, a mat in a common room, or a cramped shared space. "
             "Simple but adequate food. 2 sp/night. PHB lifestyle: Poor."),
            ("Modest Room",          "Modest",       1.00,
             "A private room at a modest inn or boarding house with a real bed, a lock on the door, "
             "and three simple meals. 1 gp/night. PHB lifestyle: Modest."),
            ("Comfortable Room",     "Comfortable",  2.00,
             "A clean private room at a respectable inn. Good meals, hot water, fresh linens. "
             "2 gp/night. PHB lifestyle: Comfortable."),
            ("Wealthy Suite",        "Wealthy",      4.00,
             "A spacious suite at a fine inn. Fine meals, attentive service, well-appointed furnishings. "
             "4 gp/night. PHB lifestyle: Wealthy."),
            ("Aristocratic Suite",   "Aristocratic", 10.00,
             "A luxury suite fit for nobility. Gourmet meals, personal attendant, "
             "opulent decor, private bath. 10+ gp/night. PHB lifestyle: Aristocratic."),
        ]
        for name, sub, cost, desc in _LIFESTYLE_ITEMS:
            con.execute("""
                INSERT OR IGNORE INTO mundane_items
                    (name, category, subcategory, store_types, cost_gp, description)
                VALUES (?, 'Lifestyle', ?, 'innkeeper', ?, ?)
            """, (name, sub, cost, desc))
        log.info("Seeded PHB Lifestyle Expenses into mundane_items.")

    # spells_reference and character_spellbook are created via IF NOT EXISTS above
    if table_exists("spells_reference") and not has_column("spells_reference", "source"):
        con.execute("ALTER TABLE spells_reference ADD COLUMN source TEXT DEFAULT 'SRD'")
    if table_exists("spells_reference") and not has_column("spells_reference", "enabled"):
        con.execute("ALTER TABLE spells_reference ADD COLUMN enabled INTEGER DEFAULT 1")
    if table_exists("spells_reference") and not has_column("spells_reference", "save_type"):
        con.execute("ALTER TABLE spells_reference ADD COLUMN save_type TEXT DEFAULT ''")


# ── Campaigns ──────────────────────────────────────────────────────────────────

_WORLD_FACTIONS = [
    # (name, org_type, description, headquarters)
    ("Harpers",                  "secret_society",  "A secretive network of bards and spies dedicated to preserving balance and thwarting tyranny across the Realms.", ""),
    ("Zhentarim",                "criminal",        "A mercenary organization known as the Black Network, seeking wealth and influence through trade, intimidation, and shadow dealings.", ""),
    ("Lords' Alliance",          "government",      "A coalition of rulers and nobles from major cities united for mutual protection, prosperity, and the stability of the Sword Coast.", ""),
    ("Order of the Gauntlet",    "religious",       "A devout and vigilant order of paladins and clerics dedicated to smiting evil and protecting the innocent.", ""),
    ("Emerald Enclave",          "other",           "A far-ranging group of druids and rangers working to maintain balance between civilization and the natural world.", ""),
    ("Bregan D'aerthe",          "criminal",        "An elite drow mercenary band led by the enigmatic Jarlaxle, operating from the shadows across the Sword Coast.", ""),
    ("Xanathar's Guild",         "criminal",        "Waterdeep's most powerful criminal organization, secretly run by the paranoid beholder known as Xanathar.", "Waterdeep"),
    ("Flaming Fist",             "military",        "Baldur's Gate's formidable mercenary army that serves as the city's primary military and law-enforcement force.", "Baldur's Gate"),
    ("City Watch - Waterdeep",   "government",      "The law enforcement arm of Waterdeep, keeping order across the City of Splendors under the authority of the Lords.", "Waterdeep"),
    ("City Watch - Neverwinter", "government",      "Neverwinter's police force, loyal to Lord Dagult Neverember, maintaining order in the Jewel of the North.", "Neverwinter"),
    ("City Watch - Baldur's Gate","government",     "The civic guard of Baldur's Gate, distinct from the Flaming Fist, responsible for keeping the peace within the city walls.", "Baldur's Gate"),
    ("Neverwinter Nine",         "military",        "An elite band of nine champions personally chosen to serve as Neverwinter's most capable defenders.", "Neverwinter"),
    ("Gray Hands",               "military",        "Waterdeep's elite adventuring force answering directly to the Open Lord, handling threats too dangerous for the City Watch.", "Waterdeep"),
    ("Force Grey",               "military",        "A special branch of the Gray Hands — adventurers deputized to act with full authority when the city faces existential threats.", "Waterdeep"),
    ("Clan Battlehammer",        "other",           "The renowned dwarven clan of Mithral Hall, legendary allies of surface folk and foes of darkness.", "Mithral Hall"),
    ("The Kraken Society",       "secret_society",  "A clandestine organization controlled by a powerful kraken, with agents planted throughout the Trackless Sea region and beyond.", ""),
    ("The Iron Throne",          "merchant_league", "A ruthless merchant consortium dealing in illicit goods, slaves, and intelligence across the Sword Coast.", ""),
    ("Cult of the Dragon",       "religious",       "A fanatical cult devoted to transforming dragons into dracoliches, believing undead dragons will one day rule Faerûn.", ""),
    ("Red Wizards of Thay",      "government",      "The ruling wizard-council of the nation of Thay, seeking magical domination and the spread of Szass Tam's undead empire.", "Thay"),
    ("The Underdark Consortium", "criminal",        "A loose coalition of illithid, drow, and deep-gnome traders operating in the depths of the Underdark.", ""),
]


def seed_world_factions(campaign_id: int) -> int:
    """Insert well-known Forgotten Realms factions for a campaign (skips existing names).
    Returns the number of factions inserted."""
    count = 0
    for name, org_type, description, hq in _WORLD_FACTIONS:
        with _conn() as con:
            existing = con.execute(
                "SELECT id FROM organizations WHERE campaign_id=? AND name=? COLLATE NOCASE",
                (campaign_id, name)
            ).fetchone()
            if existing:
                continue
        create_org(campaign_id, name, org_type=org_type,
                   description=description, headquarters=hq)
        count += 1
    return count


def create_campaign(name: str, description: str = "") -> int:
    """Create a new campaign, seed world factions, and return the campaign id."""
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO campaigns (name, description, created_at)
            VALUES (?, ?, ?)
        """, (name, description, datetime.now().isoformat()))
        cid = cur.lastrowid
    seed_world_factions(cid)
    return cid


def get_campaign(campaign_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
    return dict(row) if row else None


def list_campaigns() -> list[dict]:
    """Return all campaigns with session counts."""
    with _conn() as con:
        rows = con.execute("""
            SELECT c.id, c.name, c.description, c.created_at,
                   COUNT(s.session_key) AS session_count,
                   MAX(s.last_saved)    AS last_played,
                   MAX(s.turn)          AS max_turn
            FROM campaigns c
            LEFT JOIN sessions s ON s.campaign_id = c.id
            GROUP BY c.id
            ORDER BY last_played DESC NULLS LAST
        """).fetchall()
    return [dict(r) for r in rows]


def update_campaign(campaign_id: int, name: str, description: str):
    with _conn() as con:
        con.execute("""
            UPDATE campaigns SET name=?, description=? WHERE id=?
        """, (name, description, campaign_id))


# ── Characters ─────────────────────────────────────────────────────────────────

def _row_to_char(row) -> dict:
    return {
        "name":          row["name"],
        "group":         row["char_group"],
        "race":          row["race"],
        "class":         row["char_class"],
        "subclass":      row["subclass"],
        "level":         row["level"],
        "profession":    row["profession"],
        "hp":            row["hp"],
        "max_hp":        row["max_hp"],
        "ki_points":     row["ki_points"],
        "ac":            row["ac"],
        "speed":         row["speed"],
        "initiative":    row["initiative"],
        "status":        row["status"],
        "gold":          row["gold"],
        "buffs":         json.loads(row["buffs"]   or "[]"),
        "debuffs":       json.loads(row["debuffs"] or "[]"),
        "str":           row["str_score"],
        "dex":           row["dex_score"],
        "con":           row["con_score"],
        "int":           row["int_score"],
        "wis":           row["wis_score"],
        "cha":           row["cha_score"],
        "sending_stone": row["sending_stone"],
        "items":         json.loads(row["items"]   or "[]"),
        "spells":        json.loads(row["spells"]  or "[]"),
        "location":      row["location"] if "location" in row.keys() else "",
        "is_npc":        bool(row["is_npc"]) if "is_npc" in row.keys() else False,
        "notes":         row["notes"],
        "nickname":      row["nickname"]      if "nickname"      in row.keys() else "",
        "rp_notes":      row["rp_notes"]      if "rp_notes"      in row.keys() else "",
        "portrait_path": row["portrait_path"] if "portrait_path" in row.keys() else "",
        "classes":       json.loads(row["classes"] or "[]") if "classes" in row.keys() else [],
    }


def _char_params(c: dict, campaign_id: int) -> dict:
    def safe_int(v):
        try: return int(v or 0)
        except (ValueError, TypeError): return 0
    return {
        "campaign_id":  campaign_id,
        "name":         c.get("name", ""),
        "char_group":   c.get("group", ""),
        "race":         c.get("race", ""),
        "char_class":   c.get("class", ""),
        "subclass":     c.get("subclass", ""),
        "level":        safe_int(c.get("level", 1)) or 1,
        "profession":   c.get("profession", ""),
        "hp":           safe_int(c.get("hp")),
        "max_hp":       safe_int(c.get("max_hp")),
        "ki_points":    str(c.get("ki_points", "") or ""),
        "ac":           safe_int(c.get("ac")),
        "speed":        str(c.get("speed", "") or ""),
        "initiative":   str(c.get("initiative", "") or ""),
        "status":       str(c.get("status", "") or ""),
        "gold":         safe_int(c.get("gold")),
        "buffs":        json.dumps(c.get("buffs")   or []),
        "debuffs":      json.dumps(c.get("debuffs") or []),
        "str_score":    safe_int(c.get("str")),
        "dex_score":    safe_int(c.get("dex")),
        "con_score":    safe_int(c.get("con")),
        "int_score":    safe_int(c.get("int")),
        "wis_score":    safe_int(c.get("wis")),
        "cha_score":    safe_int(c.get("cha")),
        "sending_stone": str(c.get("sending_stone", "") or ""),
        "items":        json.dumps(c.get("items")   or []),
        "spells":       json.dumps(c.get("spells")  or []),
        "location":     str(c.get("location", "") or ""),
        "is_npc":       1 if c.get("is_npc") else 0,
        "notes":        str(c.get("notes", "") or ""),
        "nickname":      str(c.get("nickname",      "") or ""),
        "rp_notes":      str(c.get("rp_notes",      "") or ""),
        "portrait_path": str(c.get("portrait_path", "") or ""),
        "classes":       json.dumps(c.get("classes") or []),
        "updated_at":    datetime.now().isoformat(),
    }


def read_all_characters(campaign_id: int, party_only: bool = False) -> list[dict]:
    with _conn() as con:
        if party_only:
            rows = con.execute(
                "SELECT * FROM characters WHERE campaign_id=? AND char_group='Y' ORDER BY name",
                (campaign_id,)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM characters WHERE campaign_id=? ORDER BY name",
                (campaign_id,)
            ).fetchall()
    return [_row_to_char(r) for r in rows]


def upsert_character(c: dict, campaign_id: int):
    p = _char_params(c, campaign_id)
    with _conn() as con:
        con.execute("""
        INSERT INTO characters
            (campaign_id, name, char_group, race, char_class, subclass, level,
             profession, hp, max_hp, ki_points, ac, speed, initiative, status, gold,
             buffs, debuffs, str_score, dex_score, con_score, int_score,
             wis_score, cha_score, sending_stone, items, spells, location, is_npc, notes,
             nickname, rp_notes, portrait_path, classes, updated_at)
        VALUES
            (:campaign_id, :name, :char_group, :race, :char_class, :subclass, :level,
             :profession, :hp, :max_hp, :ki_points, :ac, :speed, :initiative, :status, :gold,
             :buffs, :debuffs, :str_score, :dex_score, :con_score, :int_score,
             :wis_score, :cha_score, :sending_stone, :items, :spells, :location, :is_npc, :notes,
             :nickname, :rp_notes, :portrait_path, :classes, :updated_at)
        ON CONFLICT(campaign_id, name) DO UPDATE SET
            char_group=excluded.char_group, race=excluded.race,
            char_class=excluded.char_class, subclass=excluded.subclass,
            level=excluded.level, profession=excluded.profession,
            hp=excluded.hp, max_hp=excluded.max_hp, ki_points=excluded.ki_points,
            ac=excluded.ac, speed=excluded.speed, initiative=excluded.initiative,
            status=excluded.status, gold=excluded.gold,
            buffs=excluded.buffs, debuffs=excluded.debuffs,
            str_score=excluded.str_score, dex_score=excluded.dex_score,
            con_score=excluded.con_score, int_score=excluded.int_score,
            wis_score=excluded.wis_score, cha_score=excluded.cha_score,
            sending_stone=excluded.sending_stone, items=excluded.items,
            spells=excluded.spells, location=excluded.location, is_npc=excluded.is_npc,
            notes=excluded.notes, nickname=excluded.nickname,
            rp_notes=excluded.rp_notes, classes=excluded.classes,
            portrait_path=CASE WHEN excluded.portrait_path != '' THEN excluded.portrait_path ELSE portrait_path END,
            updated_at=excluded.updated_at
        """, p)


def delete_character(name: str, campaign_id: int):
    """Remove a character from the DB."""
    with _conn() as con:
        con.execute(
            "DELETE FROM character_spellbook WHERE campaign_id=? AND char_name=? COLLATE NOCASE",
            (campaign_id, name),
        )
        con.execute(
            "DELETE FROM characters WHERE campaign_id=? AND name=? COLLATE NOCASE",
            (campaign_id, name),
        )


def set_character_portrait(name: str, campaign_id: int, portrait_path: str):
    """Update only the portrait_path for a character."""
    with _conn() as con:
        con.execute(
            "UPDATE characters SET portrait_path=?, updated_at=? WHERE campaign_id=? AND name=?",
            (portrait_path, datetime.now().isoformat(), campaign_id, name),
        )


def update_character_combat(c: dict, campaign_id: int):
    def safe_int(v):
        try: return int(v or 0)
        except (ValueError, TypeError): return 0
    with _conn() as con:
        con.execute("""
        UPDATE characters SET
            hp=:hp, max_hp=:max_hp, ac=:ac, gold=:gold,
            buffs=:buffs, debuffs=:debuffs, status=:status, updated_at=:updated_at
        WHERE campaign_id=:campaign_id AND name=:name
        """, {
            "campaign_id": campaign_id,
            "name":        c.get("name", ""),
            "hp":          safe_int(c.get("hp")),
            "max_hp":      safe_int(c.get("max_hp")),
            "ac":          safe_int(c.get("ac")),
            "gold":        safe_int(c.get("gold")),
            "buffs":       json.dumps(c.get("buffs")   or []),
            "debuffs":     json.dumps(c.get("debuffs") or []),
            "status":      str(c.get("status", "") or ""),
            "updated_at":  datetime.now().isoformat(),
        })


# ── Sessions ───────────────────────────────────────────────────────────────────

def save_session(session_key: str, campaign_id: int, turn: int,
                 game_state: dict, history: list[dict], name: str = "",
                 combat_active: bool = False, session_mode: str = "narrative",
                 combat_ui_state: dict = None, party_loot: list = None):
    now = datetime.now().isoformat()
    with _conn() as con:
        con.execute("""
        INSERT INTO sessions
            (session_key, campaign_id, name, last_saved, turn,
             game_date, location, gold, xp, history, created_at,
             combat_active, session_mode, combat_ui_state, party_loot)
        VALUES
            (:key, :cid, :name, :saved, :turn,
             :game_date, :location, :gold, :xp, :history, :created_at,
             :combat_active, :session_mode, :combat_ui_state, :party_loot)
        ON CONFLICT(session_key) DO UPDATE SET
            last_saved=excluded.last_saved, turn=excluded.turn,
            game_date=excluded.game_date, location=excluded.location,
            gold=excluded.gold, xp=excluded.xp, history=excluded.history,
            combat_active=excluded.combat_active, session_mode=excluded.session_mode,
            combat_ui_state=excluded.combat_ui_state, party_loot=excluded.party_loot,
            name=CASE WHEN excluded.name != '' THEN excluded.name ELSE sessions.name END
        """, {
            "key":              session_key,
            "cid":              campaign_id,
            "name":             name,
            "saved":            now,
            "turn":             turn,
            "game_date":        game_state.get("game_date", ""),
            "location":         game_state.get("location", ""),
            "gold":             int(game_state.get("gold", 0) or 0),
            "xp":               int(game_state.get("xp", 0) or 0),
            "history":          json.dumps(history),
            "created_at":       now,
            "combat_active":    1 if combat_active else 0,
            "session_mode":     session_mode or "narrative",
            "combat_ui_state":  json.dumps(combat_ui_state or {}),
            "party_loot":       json.dumps(party_loot or []),
        })


def load_session(session_key: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM sessions WHERE session_key=?", (session_key,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["history"]          = json.loads(d["history"] or "[]")
    d["combat_ui_state"]  = json.loads(d.get("combat_ui_state") or "{}")
    d["party_loot"]       = json.loads(d.get("party_loot") or "[]")
    return d


def list_sessions(campaign_id: int) -> list[dict]:
    with _conn() as con:
        rows = con.execute("""
            SELECT session_key, campaign_id, name, last_saved, turn,
                   game_date, location, gold, xp
            FROM sessions WHERE campaign_id=?
            ORDER BY last_saved DESC
        """, (campaign_id,)).fetchall()
    return [dict(r) for r in rows]


def rename_session(session_key: str, name: str):
    with _conn() as con:
        con.execute("UPDATE sessions SET name=? WHERE session_key=?",
                    (name, session_key))


# ── Chronicle ──────────────────────────────────────────────────────────────────

def append_chronicle(session_key: str, campaign_id: int, sync_id: str,
                     game_date: str, player_text: str, dm_text: str,
                     user_raw: str = ""):
    with _conn() as con:
        con.execute("""
        INSERT INTO chronicle
            (session_key, campaign_id, sync_id, game_date,
             player_text, dm_text, user_raw, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_key, campaign_id, sync_id, game_date,
              player_text, dm_text, user_raw, datetime.now().isoformat()))


def read_chronicle(session_key: str, limit: int = 200) -> list[dict]:
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM chronicle WHERE session_key=?
            ORDER BY id ASC LIMIT ?
        """, (session_key, limit)).fetchall()
    return [dict(r) for r in rows]


# ── Game state (legacy single-row, kept for compatibility) ─────────────────────

def update_game_state(sync_id: str, game_date: str, location: str,
                      gold: int, xp: int):
    with _conn() as con:
        con.execute("""
        INSERT INTO game_state (id, sync_id, game_date, location, gold, xp, updated_at)
        VALUES (1, :sync_id, :game_date, :location, :gold, :xp, :updated_at)
        ON CONFLICT(id) DO UPDATE SET
            sync_id=excluded.sync_id, game_date=excluded.game_date,
            location=excluded.location, gold=excluded.gold, xp=excluded.xp,
            updated_at=excluded.updated_at
        """, {
            "sync_id":    sync_id, "game_date": game_date, "location": location,
            "gold": int(gold or 0), "xp": int(xp or 0),
            "updated_at": datetime.now().isoformat(),
        })


# ── Maps ───────────────────────────────────────────────────────────────────────

def save_map(name: str, description: str, data: dict, campaign_id: int = 0):
    with _conn() as con:
        con.execute("""
        INSERT INTO maps (name, campaign_id, description, data, updated_at)
        VALUES (:name, :cid, :desc, :data, :ts)
        ON CONFLICT(name) DO UPDATE SET
            campaign_id=excluded.campaign_id, description=excluded.description,
            data=excluded.data, updated_at=excluded.updated_at
        """, {
            "name": name, "cid": campaign_id, "desc": description,
            "data": json.dumps(data), "ts": datetime.now().isoformat(),
        })


def load_map(name: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM maps WHERE name=?", (name,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["data"] = json.loads(d["data"] or "{}")
    return d


def list_maps(campaign_id: int | None = None) -> list[str]:
    with _conn() as con:
        if campaign_id is not None:
            rows = con.execute(
                "SELECT name FROM maps WHERE campaign_id=? OR campaign_id=0 ORDER BY name",
                (campaign_id,)
            ).fetchall()
        else:
            rows = con.execute("SELECT name FROM maps ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def delete_map(name: str):
    with _conn() as con:
        con.execute("DELETE FROM maps WHERE name=?", (name,))


# ── Story ──────────────────────────────────────────────────────────────────────

STORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "story")


def append_story(session_key: str, campaign_id: int, sync_id: str,
                 game_date: str, narrative: str):
    with _conn() as con:
        con.execute("""
        INSERT INTO story (session_key, campaign_id, sync_id, game_date, narrative, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (session_key, campaign_id, sync_id, game_date, narrative,
              datetime.now().isoformat()))
    os.makedirs(STORY_DIR, exist_ok=True)
    md_path = os.path.join(STORY_DIR, f"{session_key}.md")
    with open(md_path, "a", encoding="utf-8") as f:
        if game_date:
            f.write(f"\n## {game_date}\n\n")
        f.write(narrative.strip())
        f.write("\n\n---\n")


def read_story(session_key: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM story WHERE session_key=? ORDER BY id ASC", (session_key,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Compatibility shims ────────────────────────────────────────────────────────

def update_from_session(game_state: dict, sync_id: str, game_date: str = "",
                        campaign_id: int = 0):
    update_game_state(
        sync_id=sync_id, game_date=game_date,
        location=game_state.get("location", ""),
        gold=game_state.get("gold", 0), xp=game_state.get("xp", 0),
    )
    for c in game_state.get("characters", []):
        update_character_combat(c, campaign_id)
    log.debug("Session saved — %s", sync_id)


def append_session_entry(turn_data: dict, user_raw: str = "",
                         session_key: str = "", campaign_id: int = 0):
    append_chronicle(
        session_key=session_key, campaign_id=campaign_id,
        sync_id=turn_data.get("sync_id", ""),
        game_date=turn_data.get("game_date", ""),
        player_text=turn_data.get("player_restatement", ""),
        dm_text=turn_data.get("dm_response", ""),
        user_raw=user_raw,
    )
    log.debug("Chronicle entry — %s", turn_data.get('sync_id', ''))


def read_main_tab_characters(campaign_id: int = 0) -> list[dict]:
    return read_all_characters(campaign_id, party_only=True)


# ── Spells Reference ───────────────────────────────────────────────────────────

def search_spells_reference(query: str = "", level: int = None,
                             school: str = "", source: str = "",
                             char_class: str = "",
                             enabled_only: bool = True, limit: int = 50) -> list[dict]:
    """Search the master spell list. Returns matching spells sorted by level, name."""
    clauses = []
    params  = []
    if enabled_only:
        clauses.append("enabled = 1")
    if query:
        clauses.append("(name LIKE ? OR school LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]
    if level is not None:
        clauses.append("level = ?")
        params.append(level)
    if school:
        clauses.append("school LIKE ?")
        params.append(f"%{school}%")
    if source:
        clauses.append("source = ?")
        params.append(source)
    if char_class:
        # classes column is a JSON array string e.g. '["Wizard","Sorcerer"]'
        clauses.append("classes LIKE ?")
        params.append(f'%"{char_class}"%')
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM spells_reference {where} ORDER BY level, name LIMIT ?",
            params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


def list_spell_sources() -> list[dict]:
    """Return each distinct source with count and enabled status."""
    with _conn() as con:
        rows = con.execute("""
            SELECT source,
                   COUNT(*) AS total,
                   SUM(enabled) AS enabled_count
            FROM spells_reference
            GROUP BY source
            ORDER BY source
        """).fetchall()
    return [dict(r) for r in rows]


def set_source_enabled(source: str, enabled: bool):
    """Enable or disable all spells from a given source."""
    with _conn() as con:
        con.execute(
            "UPDATE spells_reference SET enabled=? WHERE source=?",
            (1 if enabled else 0, source)
        )


def upsert_spell_reference(spell: dict) -> int:
    """Insert or update a spell in the reference table. Returns the spell id."""
    with _conn() as con:
        cur = con.execute("""
        INSERT INTO spells_reference
            (name, level, school, casting_time, spell_range, components,
             duration, concentration, ritual, save_type, classes, source, enabled, description)
        VALUES
            (:name, :level, :school, :casting_time, :spell_range, :components,
             :duration, :concentration, :ritual, :save_type, :classes, :source, :enabled, :description)
        ON CONFLICT(name) DO UPDATE SET
            level=excluded.level, school=excluded.school,
            casting_time=excluded.casting_time, spell_range=excluded.spell_range,
            components=excluded.components, duration=excluded.duration,
            concentration=excluded.concentration, ritual=excluded.ritual,
            save_type=excluded.save_type, classes=excluded.classes,
            source=excluded.source, description=excluded.description
        """, {
            "name":          spell.get("name", ""),
            "level":         spell.get("level", 0),
            "school":        spell.get("school", ""),
            "casting_time":  spell.get("casting_time", ""),
            "spell_range":   spell.get("range", ""),
            "components":    spell.get("components", ""),
            "duration":      spell.get("duration", ""),
            "concentration": 1 if spell.get("concentration") else 0,
            "ritual":        1 if spell.get("ritual") else 0,
            "save_type":     spell.get("save_type", ""),
            "classes":       json.dumps(spell.get("classes", [])),
            "source":        spell.get("source", "SRD"),
            "enabled":       1,
            "description":   spell.get("description", ""),
        })
        # Fetch id (may have been an update)
        row = con.execute(
            "SELECT id FROM spells_reference WHERE name=?", (spell["name"],)
        ).fetchone()
        return row["id"] if row else cur.lastrowid


def count_spells_reference() -> int:
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM spells_reference").fetchone()
    return row["n"] if row else 0


def get_spell_reference(spell_id: int) -> dict | None:
    """Return a single spell by id."""
    with _conn() as con:
        row = con.execute("SELECT * FROM spells_reference WHERE id=?", (spell_id,)).fetchone()
    return dict(row) if row else None


def delete_spell_reference(spell_id: int):
    """Delete a spell from the reference table."""
    with _conn() as con:
        con.execute("DELETE FROM spells_reference WHERE id=?", (spell_id,))


# ── Character Spellbook ────────────────────────────────────────────────────────

def get_spellbook(campaign_id: int, char_name: str) -> list[dict]:
    """Return the character's full spellbook joined with reference data."""
    with _conn() as con:
        rows = con.execute("""
        SELECT csb.id, csb.spell_id, csb.prepared, csb.notes,
               sr.name, sr.level, sr.school, sr.casting_time, sr.spell_range,
               sr.components, sr.duration, sr.concentration, sr.ritual, sr.description
        FROM character_spellbook csb
        JOIN spells_reference sr ON sr.id = csb.spell_id
        WHERE csb.campaign_id = ? AND csb.char_name = ?
        ORDER BY sr.level, sr.name
        """, (campaign_id, char_name)).fetchall()
    return [dict(r) for r in rows]


def add_to_spellbook(campaign_id: int, char_name: str,
                     spell_id: int, prepared: bool = False, notes: str = "") -> bool:
    try:
        with _conn() as con:
            con.execute("""
            INSERT OR IGNORE INTO character_spellbook
                (campaign_id, char_name, spell_id, prepared, notes)
            VALUES (?, ?, ?, ?, ?)
            """, (campaign_id, char_name, spell_id, 1 if prepared else 0, notes))
        return True
    except Exception:
        return False


def seed_spellbook_from_names(campaign_id: int, char_name: str,
                              spell_names: list, cantrip_names: list):
    """Populate character_spellbook from name lists (used after character creation).
    Cantrips (level 0) are marked prepared=True. Spells are prepared=True for known-spell
    classes; for prepared casters they start unprepared."""
    if not spell_names and not cantrip_names:
        return
    with _conn() as con:
        for name in cantrip_names:
            row = con.execute(
                "SELECT id FROM spells_reference WHERE name=? COLLATE NOCASE AND level=0 LIMIT 1",
                (name,)
            ).fetchone()
            if row:
                con.execute(
                    "INSERT OR IGNORE INTO character_spellbook (campaign_id, char_name, spell_id, prepared) VALUES (?,?,?,1)",
                    (campaign_id, char_name, row["id"])
                )
        for name in spell_names:
            row = con.execute(
                "SELECT id FROM spells_reference WHERE name=? COLLATE NOCASE LIMIT 1",
                (name,)
            ).fetchone()
            if row:
                con.execute(
                    "INSERT OR IGNORE INTO character_spellbook (campaign_id, char_name, spell_id, prepared) VALUES (?,?,?,1)",
                    (campaign_id, char_name, row["id"])
                )


def remove_from_spellbook(campaign_id: int, char_name: str, spell_id: int):
    with _conn() as con:
        con.execute("""
        DELETE FROM character_spellbook
        WHERE campaign_id=? AND char_name=? AND spell_id=?
        """, (campaign_id, char_name, spell_id))


def set_spell_prepared(campaign_id: int, char_name: str,
                       spell_id: int, prepared: bool):
    with _conn() as con:
        con.execute("""
        UPDATE character_spellbook SET prepared=?
        WHERE campaign_id=? AND char_name=? AND spell_id=?
        """, (1 if prepared else 0, campaign_id, char_name, spell_id))


def update_spellbook_notes(campaign_id: int, char_name: str,
                           spell_id: int, notes: str):
    with _conn() as con:
        con.execute("""
        UPDATE character_spellbook SET notes=?
        WHERE campaign_id=? AND char_name=? AND spell_id=?
        """, (notes, campaign_id, char_name, spell_id))


# ── Calendar ───────────────────────────────────────────────────────────────────

def upsert_calendar_day(day: dict):
    with _conn() as con:
        con.execute("""
        INSERT INTO calendar
            (day_of_year, season, month_name, month_short, day_of_month,
             is_festival, is_leap_day, festival_name, notes)
        VALUES
            (:day_of_year, :season, :month_name, :month_short, :day_of_month,
             :is_festival, :is_leap_day, :festival_name, :notes)
        ON CONFLICT(day_of_year) DO UPDATE SET
            season=excluded.season, month_name=excluded.month_name,
            month_short=excluded.month_short, day_of_month=excluded.day_of_month,
            is_festival=excluded.is_festival, is_leap_day=excluded.is_leap_day,
            festival_name=excluded.festival_name, notes=excluded.notes
        """, day)


def get_calendar_day(day_of_year: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM calendar WHERE day_of_year=?", (day_of_year,)
        ).fetchone()
    return dict(row) if row else None


def get_calendar_month(month_name: str) -> list[dict]:
    """Return all days in a given month (partial match on month_name or month_short)."""
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM calendar
            WHERE month_name LIKE ? OR month_short LIKE ?
            ORDER BY day_of_year
        """, (f"%{month_name}%", f"%{month_name}%")).fetchall()
    return [dict(r) for r in rows]


def get_calendar_full(include_leap_day: bool = False) -> list[dict]:
    """Return the full calendar. Optionally exclude Shieldmeet (leap day)."""
    with _conn() as con:
        if include_leap_day:
            rows = con.execute(
                "SELECT * FROM calendar ORDER BY day_of_year"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM calendar WHERE is_leap_day=0 ORDER BY day_of_year"
            ).fetchall()
    return [dict(r) for r in rows]


def count_calendar_days() -> int:
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM calendar").fetchone()
    return row["n"] if row else 0


def advance_date(current_day: int, days: int,
                 is_leap_year: bool = False) -> dict | None:
    """
    Advance current_day by `days`, skipping Shieldmeet if not a leap year.
    Returns the resulting calendar row.
    """
    with _conn() as con:
        if is_leap_year:
            rows = con.execute(
                "SELECT day_of_year FROM calendar ORDER BY day_of_year"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT day_of_year FROM calendar WHERE is_leap_day=0 ORDER BY day_of_year"
            ).fetchall()

    day_sequence = [r["day_of_year"] for r in rows]
    if current_day not in day_sequence:
        # snap to nearest valid day
        current_day = min(day_sequence, key=lambda d: abs(d - current_day))

    idx     = day_sequence.index(current_day)
    new_idx = (idx + days) % len(day_sequence)
    return get_calendar_day(day_sequence[new_idx])


# ── NPCs ───────────────────────────────────────────────────────────────────────

def _row_to_npc(row) -> dict:
    return {
        "id":             row["id"],
        "campaign_id":    row["campaign_id"],
        "name":           row["name"],
        "npc_type":       row["npc_type"],
        "attitude":       row["attitude"],
        "faction":        row["faction"],
        "location":       row["location"],
        "notes":          row["notes"],
        "last_seen_date": row["last_seen_date"],
        "last_seen_loc":  row["last_seen_loc"],
        "updated_at":     row["updated_at"],
        "is_store":       bool(row["is_store"]) if "is_store" in row.keys() else False,
    }


def upsert_npc(campaign_id: int, name: str, npc_type: str = "",
               attitude_delta: int = 0, faction: str = "",
               location: str = "", notes: str = "",
               last_seen_date: str = "", last_seen_loc: str = "",
               is_store: bool = False) -> dict:
    """
    Create or update an NPC.  attitude_delta is ADDED to the current attitude
    (clamped to -100/+100). Pass attitude_delta=0 to leave attitude unchanged.
    Returns the updated NPC row.
    """
    now = datetime.now().isoformat()
    with _conn() as con:
        existing = con.execute(
            "SELECT * FROM npcs WHERE campaign_id=? AND name=?",
            (campaign_id, name)
        ).fetchone()
        if existing:
            new_att = max(-100, min(100, existing["attitude"] + attitude_delta))
            con.execute("""
                UPDATE npcs SET
                    npc_type       = CASE WHEN ? != '' THEN ? ELSE npc_type END,
                    attitude       = ?,
                    faction        = CASE WHEN ? != '' THEN ? ELSE faction END,
                    location       = CASE WHEN ? != '' THEN ? ELSE location END,
                    notes          = CASE WHEN ? != '' THEN ? ELSE notes END,
                    last_seen_date = CASE WHEN ? != '' THEN ? ELSE last_seen_date END,
                    last_seen_loc  = CASE WHEN ? != '' THEN ? ELSE last_seen_loc END,
                    is_store       = CASE WHEN ? THEN 1 ELSE is_store END,
                    updated_at     = ?
                WHERE campaign_id=? AND name=?
            """, (npc_type, npc_type, new_att, faction, faction,
                  location, location, notes, notes,
                  last_seen_date, last_seen_date, last_seen_loc, last_seen_loc,
                  1 if is_store else 0, now, campaign_id, name))
        else:
            new_att = max(-100, min(100, attitude_delta))
            con.execute("""
                INSERT INTO npcs
                    (campaign_id, name, npc_type, attitude, faction, location,
                     notes, last_seen_date, last_seen_loc, is_store, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (campaign_id, name, npc_type, new_att, faction, location,
                  notes, last_seen_date, last_seen_loc, 1 if is_store else 0, now))
        row = con.execute(
            "SELECT * FROM npcs WHERE campaign_id=? AND name=?",
            (campaign_id, name)
        ).fetchone()
    return _row_to_npc(row)


def get_npc(npc_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM npcs WHERE id=?", (npc_id,)).fetchone()
    return _row_to_npc(row) if row else None


def get_npc_by_name(campaign_id: int, name: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM npcs WHERE campaign_id=? AND name=?",
            (campaign_id, name)
        ).fetchone()
    return _row_to_npc(row) if row else None


def list_npcs(campaign_id: int) -> list[dict]:
    """All NPCs for a campaign, ordered by attitude descending (friendliest first)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM npcs WHERE campaign_id=? ORDER BY attitude DESC, name ASC",
            (campaign_id,)
        ).fetchall()
    return [_row_to_npc(r) for r in rows]


def get_npcs_at_location(campaign_id: int, location: str) -> list[dict]:
    """
    Return NPCs whose stored location overlaps with the given location string.
    Matches if either is a substring of the other (case-insensitive).
    """
    if not location or not location.strip():
        return []
    loc_lower = location.strip().lower()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM npcs WHERE campaign_id=? AND location != '' ORDER BY attitude DESC",
            (campaign_id,)
        ).fetchall()
    results = []
    for r in rows:
        npc_loc = (r["location"] or "").strip().lower()
        if npc_loc and (npc_loc in loc_lower or loc_lower in npc_loc):
            results.append(_row_to_npc(r))
    return results


def set_npc_attitude(npc_id: int, attitude: int):
    """Directly set attitude (absolute, not delta). Clamped to -100/+100."""
    with _conn() as con:
        con.execute(
            "UPDATE npcs SET attitude=?, updated_at=? WHERE id=?",
            (max(-100, min(100, attitude)), datetime.now().isoformat(), npc_id)
        )


def delete_npc(npc_id: int):
    with _conn() as con:
        con.execute("DELETE FROM npcs WHERE id=?", (npc_id,))


# ── NPC Affinity ────────────────────────────────────────────────────────────────

def get_npc_affinity(campaign_id: int, npc_id: int, char_name: str) -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT score FROM npc_affinity WHERE campaign_id=? AND npc_id=? AND char_name=? COLLATE NOCASE",
            (campaign_id, npc_id, char_name)
        ).fetchone()
    return row["score"] if row else 0


def get_all_npc_affinities(campaign_id: int, npc_id: int) -> dict:
    """Returns {char_name: score} for all characters with a recorded affinity."""
    with _conn() as con:
        rows = con.execute(
            "SELECT char_name, score FROM npc_affinity WHERE campaign_id=? AND npc_id=?",
            (campaign_id, npc_id)
        ).fetchall()
    return {r["char_name"]: r["score"] for r in rows}


def set_npc_affinity(campaign_id: int, npc_id: int, char_name: str, score: int):
    score = max(-100, min(100, score))
    with _conn() as con:
        con.execute("""
            INSERT INTO npc_affinity (campaign_id, npc_id, char_name, score, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, npc_id, char_name)
            DO UPDATE SET score=excluded.score, updated_at=excluded.updated_at
        """, (campaign_id, npc_id, char_name, score, datetime.now().isoformat()))


def adjust_npc_affinity(campaign_id: int, npc_id: int, char_name: str, delta: int) -> int:
    current = get_npc_affinity(campaign_id, npc_id, char_name)
    new_score = max(-100, min(100, current + delta))
    set_npc_affinity(campaign_id, npc_id, char_name, new_score)
    return new_score


# ── NPC Offers ─────────────────────────────────────────────────────────────────

def add_npc_offer(npc_id: int, campaign_id: int, offer_type: str,
                  title: str, description: str = "", price_gp: int = None,
                  created_date: str = "", expires_date: str = "") -> int:
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO npc_offers
                (npc_id, campaign_id, offer_type, title, description,
                 price_gp, status, created_date, expires_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (npc_id, campaign_id, offer_type, title, description,
              price_gp, created_date, expires_date,
              datetime.now().isoformat()))
        return cur.lastrowid


def list_npc_offers(npc_id: int, status: str = None) -> list[dict]:
    with _conn() as con:
        if status:
            rows = con.execute(
                "SELECT * FROM npc_offers WHERE npc_id=? AND status=? ORDER BY id",
                (npc_id, status)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM npc_offers WHERE npc_id=? ORDER BY id",
                (npc_id,)
            ).fetchall()
    return [dict(r) for r in rows]


def list_all_active_offers(campaign_id: int) -> list[dict]:
    """All active offers across all NPCs in a campaign, joined with NPC name."""
    with _conn() as con:
        rows = con.execute("""
            SELECT o.*, n.name AS npc_name, n.npc_type, n.location AS npc_location
            FROM npc_offers o
            JOIN npcs n ON n.id = o.npc_id
            WHERE o.campaign_id=? AND o.status='active'
            ORDER BY o.offer_type, n.name
        """, (campaign_id,)).fetchall()
    return [dict(r) for r in rows]


def get_offer(offer_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM npc_offers WHERE id=?", (offer_id,)).fetchone()
    return dict(row) if row else None


def set_offer_status(offer_id: int, status: str):
    """status: 'active' | 'sold' | 'resolved' | 'expired'"""
    with _conn() as con:
        con.execute(
            "UPDATE npc_offers SET status=? WHERE id=?",
            (status, offer_id)
        )


def delete_offer(offer_id: int):
    with _conn() as con:
        con.execute("DELETE FROM npc_offers WHERE id=?", (offer_id,))


# ── Magic Items Reference ───────────────────────────────────────────────────────

def upsert_magic_item(item: dict):
    with _conn() as con:
        con.execute("""
        INSERT INTO magic_items
            (name, category, rarity, requires_attunement, attunement_by, effect,
             stat_set_str, stat_set_dex, stat_set_con, stat_set_int, stat_set_wis, stat_set_cha,
             stat_bonus_str, stat_bonus_dex, stat_bonus_con, stat_bonus_int, stat_bonus_wis, stat_bonus_cha,
             ac_bonus, attack_bonus, value_gp, source)
        VALUES
            (:name, :category, :rarity, :requires_attunement, :attunement_by, :effect,
             :stat_set_str, :stat_set_dex, :stat_set_con, :stat_set_int, :stat_set_wis, :stat_set_cha,
             :stat_bonus_str, :stat_bonus_dex, :stat_bonus_con, :stat_bonus_int, :stat_bonus_wis, :stat_bonus_cha,
             :ac_bonus, :attack_bonus, :value_gp, :source)
        ON CONFLICT(name) DO UPDATE SET
            category=excluded.category, rarity=excluded.rarity,
            requires_attunement=excluded.requires_attunement, attunement_by=excluded.attunement_by,
            effect=excluded.effect,
            stat_set_str=excluded.stat_set_str, stat_set_dex=excluded.stat_set_dex,
            stat_set_con=excluded.stat_set_con, stat_set_int=excluded.stat_set_int,
            stat_set_wis=excluded.stat_set_wis, stat_set_cha=excluded.stat_set_cha,
            stat_bonus_str=excluded.stat_bonus_str, stat_bonus_dex=excluded.stat_bonus_dex,
            stat_bonus_con=excluded.stat_bonus_con, stat_bonus_int=excluded.stat_bonus_int,
            stat_bonus_wis=excluded.stat_bonus_wis, stat_bonus_cha=excluded.stat_bonus_cha,
            ac_bonus=excluded.ac_bonus, attack_bonus=excluded.attack_bonus,
            value_gp=excluded.value_gp, source=excluded.source
        """, {
            "name":                item.get("name", ""),
            "category":            item.get("category", ""),
            "rarity":              item.get("rarity", "common"),
            "requires_attunement": 1 if item.get("requires_attunement") else 0,
            "attunement_by":       item.get("attunement_by", ""),
            "effect":              item.get("effect", ""),
            "stat_set_str":        item.get("stat_set_str", 0),
            "stat_set_dex":        item.get("stat_set_dex", 0),
            "stat_set_con":        item.get("stat_set_con", 0),
            "stat_set_int":        item.get("stat_set_int", 0),
            "stat_set_wis":        item.get("stat_set_wis", 0),
            "stat_set_cha":        item.get("stat_set_cha", 0),
            "stat_bonus_str":      item.get("stat_bonus_str", 0),
            "stat_bonus_dex":      item.get("stat_bonus_dex", 0),
            "stat_bonus_con":      item.get("stat_bonus_con", 0),
            "stat_bonus_int":      item.get("stat_bonus_int", 0),
            "stat_bonus_wis":      item.get("stat_bonus_wis", 0),
            "stat_bonus_cha":      item.get("stat_bonus_cha", 0),
            "ac_bonus":            item.get("ac_bonus", 0),
            "attack_bonus":        item.get("attack_bonus", 0),
            "value_gp":            item.get("value_gp", 0),
            "source":              item.get("source", "DMG"),
        })


def search_magic_items(query: str = "", category: str = "", rarity: str = "",
                       limit: int = 20) -> list[dict]:
    clauses = []
    params  = []
    if query:
        clauses.append("name LIKE ?")
        params.append(f"%{query}%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if rarity:
        clauses.append("rarity = ?")
        params.append(rarity)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM magic_items {where} ORDER BY name LIMIT ?", params
        ).fetchall()
    return [dict(r) for r in rows]


def get_magic_item(name: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM magic_items WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
    return dict(row) if row else None


def count_magic_items() -> int:
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM magic_items").fetchone()
    return row["n"] if row else 0


# ── Mundane Items Reference ─────────────────────────────────────────────────────

def upsert_mundane_item(item: dict):
    with _conn() as con:
        con.execute("""
        INSERT INTO mundane_items
            (name, category, subcategory, store_types, cost_gp, weight_lb,
             damage, damage_type, properties, armor_class,
             str_requirement, stealth_disadv, capacity, speed, description)
        VALUES
            (:name, :category, :subcategory, :store_types, :cost_gp, :weight_lb,
             :damage, :damage_type, :properties, :armor_class,
             :str_requirement, :stealth_disadv, :capacity, :speed, :description)
        ON CONFLICT(name) DO UPDATE SET
            category=excluded.category, subcategory=excluded.subcategory,
            store_types=excluded.store_types, cost_gp=excluded.cost_gp,
            weight_lb=excluded.weight_lb, damage=excluded.damage,
            damage_type=excluded.damage_type, properties=excluded.properties,
            armor_class=excluded.armor_class, str_requirement=excluded.str_requirement,
            stealth_disadv=excluded.stealth_disadv, capacity=excluded.capacity,
            speed=excluded.speed, description=excluded.description
        """, {
            "name":            item.get("name", ""),
            "category":        item.get("category", ""),
            "subcategory":     item.get("subcategory", ""),
            "store_types":     item.get("store_types", ""),
            "cost_gp":         item.get("cost_gp", 0),
            "weight_lb":       item.get("weight_lb", 0),
            "damage":          item.get("damage", ""),
            "damage_type":     item.get("damage_type", ""),
            "properties":      item.get("properties", ""),
            "armor_class":     item.get("armor_class", ""),
            "str_requirement": item.get("str_requirement", 0),
            "stealth_disadv":  1 if item.get("stealth_disadv") else 0,
            "capacity":        item.get("capacity", ""),
            "speed":           item.get("speed", ""),
            "description":     item.get("description", ""),
        })


def search_mundane_items(query: str = "", category: str = "",
                         subcategory: str = "", store_type: str = "",
                         limit: int = 50) -> list[dict]:
    clauses = []
    params  = []
    if query:
        clauses.append("name LIKE ?")
        params.append(f"%{query}%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if subcategory:
        clauses.append("subcategory = ?")
        params.append(subcategory)
    if store_type:
        clauses.append("(',' || store_types || ',') LIKE ?")
        params.append(f"%,{store_type},%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM mundane_items {where} ORDER BY category, subcategory, name LIMIT ?",
            params
        ).fetchall()
    return [dict(r) for r in rows]


def get_mundane_item(name: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM mundane_items WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
    return dict(row) if row else None


def count_mundane_items() -> int:
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM mundane_items").fetchone()
    return row["n"] if row else 0


# ── Mobs ───────────────────────────────────────────────────────────────────────

def _hp_avg(formula: str) -> int:
    """Compute average HP from a dice expression like '3d8+6' or '4d6-4'."""
    if not formula:
        return 0
    formula = formula.strip()
    # Pure integer
    try:
        return int(formula)
    except ValueError:
        pass
    import re as _re
    m = _re.match(r'^(\d+)d(\d+)\s*([+-]\s*\d+)?$', formula, _re.I)
    if not m:
        return 0
    num, sides = int(m.group(1)), int(m.group(2))
    mod = int((m.group(3) or '0').replace(' ', '')) if m.group(3) else 0
    return round(num * (sides + 1) / 2 + mod)


def upsert_mob(mob: dict):
    with _conn() as con:
        con.execute("""
        INSERT INTO mobs
            (name, description, ac, hp_formula, hp_avg, speed,
             str, dex, con, int, wis, cha,
             challenge, xp, size, mob_type, alignment,
             melee_mod, ranged_mod,
             attack1, attack1_range, attack1_dmg,
             attack2, attack2_range, attack2_dmg,
             attack3, attack3_range, attack3_dmg,
             source, notes, languages, image_path)
        VALUES
            (:name, :description, :ac, :hp_formula, :hp_avg, :speed,
             :str, :dex, :con, :int, :wis, :cha,
             :challenge, :xp, :size, :mob_type, :alignment,
             :melee_mod, :ranged_mod,
             :attack1, :attack1_range, :attack1_dmg,
             :attack2, :attack2_range, :attack2_dmg,
             :attack3, :attack3_range, :attack3_dmg,
             :source, :notes, :languages, :image_path)
        ON CONFLICT(name) DO UPDATE SET
            description=excluded.description, ac=excluded.ac,
            hp_formula=excluded.hp_formula, hp_avg=excluded.hp_avg,
            speed=excluded.speed,
            str=excluded.str, dex=excluded.dex, con=excluded.con,
            int=excluded.int, wis=excluded.wis, cha=excluded.cha,
            challenge=excluded.challenge, xp=excluded.xp,
            size=excluded.size, mob_type=excluded.mob_type, alignment=excluded.alignment,
            melee_mod=excluded.melee_mod, ranged_mod=excluded.ranged_mod,
            attack1=excluded.attack1, attack1_range=excluded.attack1_range, attack1_dmg=excluded.attack1_dmg,
            attack2=excluded.attack2, attack2_range=excluded.attack2_range, attack2_dmg=excluded.attack2_dmg,
            attack3=excluded.attack3, attack3_range=excluded.attack3_range, attack3_dmg=excluded.attack3_dmg,
            source=excluded.source, notes=excluded.notes,
            languages=excluded.languages,
            image_path=CASE WHEN excluded.image_path != '' THEN excluded.image_path ELSE image_path END
        """, {
            "name":         str(mob.get("name", "") or ""),
            "description":  str(mob.get("description", "") or ""),
            "ac":           int(mob.get("ac") or 0),
            "hp_formula":   str(mob.get("hp_formula", "") or ""),
            "hp_avg":       int(mob.get("hp_avg") or _hp_avg(str(mob.get("hp_formula", "") or ""))),
            "speed":        str(mob.get("speed", "") or ""),
            "str":          int(mob.get("str") or 10),
            "dex":          int(mob.get("dex") or 10),
            "con":          int(mob.get("con") or 10),
            "int":          int(mob.get("int") or 10),
            "wis":          int(mob.get("wis") or 10),
            "cha":          int(mob.get("cha") or 10),
            "challenge":    str(mob.get("challenge", "") or ""),
            "xp":           int(mob.get("xp") or 0),
            "size":         str(mob.get("size", "") or ""),
            "mob_type":     str(mob.get("mob_type", "") or ""),
            "alignment":    str(mob.get("alignment", "") or ""),
            "melee_mod":    str(mob.get("melee_mod", "") or ""),
            "ranged_mod":   str(mob.get("ranged_mod", "") or ""),
            "attack1":      str(mob.get("attack1", "") or ""),
            "attack1_range":str(mob.get("attack1_range", "") or ""),
            "attack1_dmg":  str(mob.get("attack1_dmg", "") or ""),
            "attack2":      str(mob.get("attack2", "") or ""),
            "attack2_range":str(mob.get("attack2_range", "") or ""),
            "attack2_dmg":  str(mob.get("attack2_dmg", "") or ""),
            "attack3":      str(mob.get("attack3", "") or ""),
            "attack3_range":str(mob.get("attack3_range", "") or ""),
            "attack3_dmg":  str(mob.get("attack3_dmg", "") or ""),
            "source":       str(mob.get("source",     "") or ""),
            "notes":        str(mob.get("notes",      "") or ""),
            "languages":    str(mob.get("languages",  "") or ""),
            "image_path":   str(mob.get("image_path", "") or ""),
        })


def search_mobs(query: str = "", limit: int = 12) -> list[dict]:
    q = f"%{query.strip()}%" if query.strip() else "%"
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM mobs WHERE name LIKE ? ORDER BY name LIMIT ?",
            (q, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_mob(name: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM mobs WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
    return dict(row) if row else None


def count_mobs() -> int:
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM mobs").fetchone()
    return row["n"] if row else 0


def delete_mob(name: str):
    """Delete a mob from the bestiary by name."""
    with _conn() as con:
        con.execute("DELETE FROM mobs WHERE name=? COLLATE NOCASE", (name,))


def set_mob_image(name: str, image_path: str):
    """Update only the image_path for a mob."""
    with _conn() as con:
        con.execute(
            "UPDATE mobs SET image_path=? WHERE name=? COLLATE NOCASE",
            (image_path, name),
        )


def update_mob_languages(name: str, languages: str):
    """Update only the languages field for a mob."""
    with _conn() as con:
        con.execute(
            "UPDATE mobs SET languages=? WHERE name=? COLLATE NOCASE",
            (languages, name),
        )


# ── Mob Knowledge ──────────────────────────────────────────────────────────────

KNOWLEDGE_RANKS = ['unknown', 'seen', 'fought', 'researched', 'known']


def get_mob_knowledge(mob_name: str, campaign_id: int) -> dict:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM mob_knowledge WHERE campaign_id=? AND mob_name=? COLLATE NOCASE",
            (campaign_id, mob_name),
        ).fetchone()
    if row:
        return {"mob_name": row["mob_name"], "knowledge_rank": row["knowledge_rank"], "notes": row["notes"]}
    return {"mob_name": mob_name, "knowledge_rank": "unknown", "notes": ""}


def set_mob_knowledge(mob_name: str, campaign_id: int, knowledge_rank: str, notes: str = None):
    if knowledge_rank not in KNOWLEDGE_RANKS:
        knowledge_rank = "unknown"
    with _conn() as con:
        existing = con.execute(
            "SELECT notes FROM mob_knowledge WHERE campaign_id=? AND mob_name=? COLLATE NOCASE",
            (campaign_id, mob_name),
        ).fetchone()
        keep_notes = existing["notes"] if existing and notes is None else (notes or "")
        con.execute("""
            INSERT INTO mob_knowledge (campaign_id, mob_name, knowledge_rank, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(campaign_id, mob_name) DO UPDATE SET
                knowledge_rank=excluded.knowledge_rank,
                notes=excluded.notes
        """, (campaign_id, mob_name, knowledge_rank, keep_notes))


def advance_mob_knowledge(mob_name: str, campaign_id: int, min_rank: str):
    """Advance knowledge to at least min_rank, never downgrade."""
    current = get_mob_knowledge(mob_name, campaign_id)["knowledge_rank"]
    try:
        if KNOWLEDGE_RANKS.index(min_rank) > KNOWLEDGE_RANKS.index(current):
            set_mob_knowledge(mob_name, campaign_id, min_rank)
    except ValueError:
        pass


def list_mob_knowledge(campaign_id: int) -> dict:
    """Return dict of mob_name -> knowledge_rank for the campaign."""
    with _conn() as con:
        rows = con.execute(
            "SELECT mob_name, knowledge_rank FROM mob_knowledge WHERE campaign_id=?",
            (campaign_id,),
        ).fetchall()
    return {r["mob_name"].lower(): r["knowledge_rank"] for r in rows}


def list_mobs_for_manual(campaign_id: int) -> list[dict]:
    """Return all mobs joined with their knowledge rank for current campaign."""
    knowledge = list_mob_knowledge(campaign_id)
    with _conn() as con:
        rows = con.execute("SELECT * FROM mobs ORDER BY name").fetchall()
    result = []
    for r in rows:
        mob = dict(r)
        mob["knowledge_rank"] = knowledge.get(r["name"].lower(), "unknown")
        result.append(mob)
    return result


# ── Campaign Overrides ─────────────────────────────────────────────────────────

def get_mob_override(mob_name: str, campaign_id: int) -> dict:
    """Return the campaign-specific override row for a mob, or empty dict."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM campaign_mob_overrides WHERE mob_name=? COLLATE NOCASE AND campaign_id=?",
            (mob_name, campaign_id)
        ).fetchone()
    return dict(row) if row else {}


def set_mob_override(campaign_id: int, mob_name: str,
                     image_path: str = None, description: str = None, notes: str = None):
    """Upsert campaign-specific override fields for a mob. Pass None to leave field unchanged."""
    with _conn() as con:
        con.execute("""
        INSERT INTO campaign_mob_overrides (campaign_id, mob_name, image_path, description, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(campaign_id, mob_name) DO UPDATE SET
            image_path  = CASE WHEN excluded.image_path  IS NOT NULL THEN excluded.image_path  ELSE image_path  END,
            description = CASE WHEN excluded.description IS NOT NULL THEN excluded.description ELSE description END,
            notes       = CASE WHEN excluded.notes       IS NOT NULL THEN excluded.notes       ELSE notes       END
        """, (campaign_id, mob_name, image_path, description, notes))


def clear_mob_override(campaign_id: int, mob_name: str):
    with _conn() as con:
        con.execute(
            "DELETE FROM campaign_mob_overrides WHERE campaign_id=? AND mob_name=? COLLATE NOCASE",
            (campaign_id, mob_name)
        )


def get_mob_with_override(mob_name: str, campaign_id: int) -> dict | None:
    """Return mob master data merged with any campaign override."""
    mob = get_mob(mob_name)
    if not mob:
        return None
    if campaign_id:
        ov = get_mob_override(mob_name, campaign_id)
        if ov:
            mob["_override"] = ov
            if ov.get("image_path"):
                mob["image_path"] = ov["image_path"]
            if ov.get("description") is not None:
                mob["description"] = ov["description"]
            if ov.get("notes") is not None:
                mob["notes"] = ov["notes"]
    return mob


def get_spell_override(spell_id: int, campaign_id: int) -> dict:
    """Return the campaign-specific override row for a spell, or empty dict."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM campaign_spell_overrides WHERE spell_id=? AND campaign_id=?",
            (spell_id, campaign_id)
        ).fetchone()
    return dict(row) if row else {}


def set_spell_override(campaign_id: int, spell_id: int,
                       enabled: int = None, description: str = None, notes: str = None):
    """Upsert campaign-specific override fields for a spell. Pass None to leave field unchanged."""
    with _conn() as con:
        con.execute("""
        INSERT INTO campaign_spell_overrides (campaign_id, spell_id, enabled, description, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(campaign_id, spell_id) DO UPDATE SET
            enabled     = CASE WHEN excluded.enabled     IS NOT NULL THEN excluded.enabled     ELSE enabled     END,
            description = CASE WHEN excluded.description IS NOT NULL THEN excluded.description ELSE description END,
            notes       = CASE WHEN excluded.notes       IS NOT NULL THEN excluded.notes       ELSE notes       END
        """, (campaign_id, spell_id, enabled, description, notes))


def clear_spell_override(campaign_id: int, spell_id: int):
    with _conn() as con:
        con.execute(
            "DELETE FROM campaign_spell_overrides WHERE campaign_id=? AND spell_id=?",
            (campaign_id, spell_id)
        )


def get_spell_with_override(spell_id: int, campaign_id: int) -> dict | None:
    """Return spell master data merged with any campaign override."""
    spell = get_spell_reference(spell_id)
    if not spell:
        return None
    if campaign_id:
        ov = get_spell_override(spell_id, campaign_id)
        if ov:
            spell["_override"] = ov
            if ov.get("enabled") is not None:
                spell["enabled"] = ov["enabled"]
            if ov.get("description") is not None:
                spell["description"] = ov["description"]
            if ov.get("notes") is not None:
                spell["notes"] = ov["notes"]
    return spell


# ── API Usage Logging ──────────────────────────────────────────────────────────

def log_api_call(session_key: str, campaign_id: int, call_type: str,
                 model: str, prompt_tokens: int, output_tokens: int,
                 user_id: int = None):
    """Record a single AI API call with token counts."""
    total = prompt_tokens + output_tokens
    with _conn() as con:
        con.execute("""
        INSERT INTO api_usage_log
            (session_key, campaign_id, call_type, model,
             prompt_tokens, output_tokens, total_tokens, called_at, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_key or "", campaign_id or 0, call_type, model or "",
              prompt_tokens, output_tokens, total,
              datetime.now().isoformat(), user_id))


def get_usage_by_session(campaign_id: int = None, limit: int = 50) -> list[dict]:
    """Return per-session aggregated usage, most recent first."""
    where  = "WHERE campaign_id = ?" if campaign_id is not None else ""
    params = [campaign_id] if campaign_id is not None else []
    with _conn() as con:
        rows = con.execute(f"""
        SELECT session_key,
               campaign_id,
               COUNT(*)                      AS calls,
               SUM(prompt_tokens)            AS prompt_tokens,
               SUM(output_tokens)            AS output_tokens,
               SUM(total_tokens)             AS total_tokens,
               MIN(called_at)                AS first_call,
               MAX(called_at)                AS last_call
        FROM api_usage_log
        {where}
        GROUP BY session_key, campaign_id
        ORDER BY last_call DESC
        LIMIT ?
        """, params + [limit]).fetchall()
    return [dict(r) for r in rows]


def get_usage_by_type(session_key: str = None) -> list[dict]:
    """Return per-call-type breakdown, optionally for one session."""
    where  = "WHERE session_key = ?" if session_key else ""
    params = [session_key] if session_key else []
    with _conn() as con:
        rows = con.execute(f"""
        SELECT call_type,
               model,
               COUNT(*)           AS calls,
               SUM(prompt_tokens) AS prompt_tokens,
               SUM(output_tokens) AS output_tokens,
               SUM(total_tokens)  AS total_tokens
        FROM api_usage_log
        {where}
        GROUP BY call_type, model
        ORDER BY total_tokens DESC
        """, params).fetchall()
    return [dict(r) for r in rows]


def get_usage_totals(campaign_id: int = None) -> dict:
    """Return overall token and call totals."""
    where  = "WHERE campaign_id = ?" if campaign_id is not None else ""
    params = [campaign_id] if campaign_id is not None else []
    with _conn() as con:
        row = con.execute(f"""
        SELECT COUNT(*)           AS calls,
               SUM(prompt_tokens) AS prompt_tokens,
               SUM(output_tokens) AS output_tokens,
               SUM(total_tokens)  AS total_tokens
        FROM api_usage_log {where}
        """, params).fetchone()
    return dict(row) if row else {}


# ── Organizations ───────────────────────────────────────────────────────────────

def create_org(campaign_id: int, name: str, org_type: str = "",
               description: str = "", headquarters: str = "", notes: str = "") -> int:
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO organizations (campaign_id, name, org_type, description, headquarters, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, name) DO UPDATE SET
                org_type=excluded.org_type, description=excluded.description,
                headquarters=excluded.headquarters, notes=excluded.notes,
                updated_at=excluded.updated_at
        """, (campaign_id, name.strip(), org_type, description, headquarters, notes,
              datetime.now().isoformat()))
        return cur.lastrowid


def get_org(org_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
    return dict(row) if row else None


def list_orgs(campaign_id: int) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM organizations WHERE campaign_id=? ORDER BY name",
            (campaign_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_org(org_id: int, name: str = None, org_type: str = None,
               description: str = None, headquarters: str = None, notes: str = None):
    fields, vals = [], []
    if name        is not None: fields.append("name=?");         vals.append(name.strip())
    if org_type    is not None: fields.append("org_type=?");     vals.append(org_type)
    if description is not None: fields.append("description=?");  vals.append(description)
    if headquarters is not None: fields.append("headquarters=?"); vals.append(headquarters)
    if notes       is not None: fields.append("notes=?");        vals.append(notes)
    if not fields:
        return
    fields.append("updated_at=?"); vals.append(datetime.now().isoformat())
    vals.append(org_id)
    with _conn() as con:
        con.execute(f"UPDATE organizations SET {', '.join(fields)} WHERE id=?", vals)


def delete_org(org_id: int):
    with _conn() as con:
        con.execute("DELETE FROM organizations WHERE id=?", (org_id,))


# ── Org Members ─────────────────────────────────────────────────────────────────

def add_org_member(org_id: int, campaign_id: int, entity_type: str,
                   entity_ref: str, rank: str = ""):
    """entity_type: 'character' or 'npc'. entity_ref: char name or str(npc_id)."""
    with _conn() as con:
        con.execute("""
            INSERT OR REPLACE INTO org_members (org_id, campaign_id, entity_type, entity_ref, rank)
            VALUES (?, ?, ?, ?, ?)
        """, (org_id, campaign_id, entity_type, str(entity_ref).strip(), rank))


def remove_org_member(org_id: int, entity_type: str, entity_ref: str):
    with _conn() as con:
        con.execute(
            "DELETE FROM org_members WHERE org_id=? AND entity_type=? AND entity_ref=?",
            (org_id, entity_type, str(entity_ref).strip())
        )


def get_org_members(org_id: int) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM org_members WHERE org_id=? ORDER BY entity_type, entity_ref",
            (org_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_entity_orgs(campaign_id: int, entity_type: str, entity_ref: str) -> list[dict]:
    """Return list of org dicts for a given character (entity_ref=name) or NPC (entity_ref=str(id))."""
    with _conn() as con:
        rows = con.execute("""
            SELECT o.*, m.rank
            FROM organizations o
            JOIN org_members m ON m.org_id = o.id
            WHERE o.campaign_id=? AND m.entity_type=? AND m.entity_ref=?
            ORDER BY o.name
        """, (campaign_id, entity_type, str(entity_ref).strip())).fetchall()
    return [dict(r) for r in rows]


# ── Org Affinity ────────────────────────────────────────────────────────────────

def get_org_affinity(campaign_id: int, org_id_a: int, org_id_b: int) -> int:
    # Symmetric: check both orderings
    with _conn() as con:
        row = con.execute("""
            SELECT score FROM org_affinity
            WHERE campaign_id=? AND ((org_id_a=? AND org_id_b=?) OR (org_id_a=? AND org_id_b=?))
        """, (campaign_id, org_id_a, org_id_b, org_id_b, org_id_a)).fetchone()
    return row["score"] if row else 0


def get_all_org_affinities(campaign_id: int, org_id: int) -> list[dict]:
    """Return [{org_id, org_name, score}] for all orgs that have a recorded affinity with org_id."""
    with _conn() as con:
        rows = con.execute("""
            SELECT
                CASE WHEN a.org_id_a=? THEN a.org_id_b ELSE a.org_id_a END AS other_org_id,
                o.name AS org_name,
                a.score
            FROM org_affinity a
            JOIN organizations o ON o.id = (CASE WHEN a.org_id_a=? THEN a.org_id_b ELSE a.org_id_a END)
            WHERE a.campaign_id=? AND (a.org_id_a=? OR a.org_id_b=?)
            ORDER BY o.name
        """, (org_id, org_id, campaign_id, org_id, org_id)).fetchall()
    return [dict(r) for r in rows]


def set_org_affinity(campaign_id: int, org_id_a: int, org_id_b: int, score: int):
    score = max(-100, min(100, score))
    # Always store with the lower id first for consistency
    a, b = (org_id_a, org_id_b) if org_id_a <= org_id_b else (org_id_b, org_id_a)
    with _conn() as con:
        con.execute("""
            INSERT INTO org_affinity (campaign_id, org_id_a, org_id_b, score, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, org_id_a, org_id_b)
            DO UPDATE SET score=excluded.score, updated_at=excluded.updated_at
        """, (campaign_id, a, b, score, datetime.now().isoformat()))


def adjust_org_affinity(campaign_id: int, org_id_a: int, org_id_b: int, delta: int) -> int:
    current = get_org_affinity(campaign_id, org_id_a, org_id_b)
    new_score = max(-100, min(100, current + delta))
    set_org_affinity(campaign_id, org_id_a, org_id_b, new_score)
    return new_score


def compute_interaction_org_score(campaign_id: int, char_name: str, npc_id: int) -> dict:
    """
    Compute the combined org-to-org affinity modifier for a character interacting with an NPC.
    Returns {score: int, pairs: [{char_org, npc_org, score}], mod: float}
    score is the average of all (char_org × npc_org) pairs, or 0 if none exist.
    """
    char_orgs = get_entity_orgs(campaign_id, "character", char_name)
    npc_orgs  = get_entity_orgs(campaign_id, "npc", str(npc_id))
    if not char_orgs or not npc_orgs:
        return {"score": 0, "pairs": [], "mod": 1.0,
                "char_orgs": char_orgs, "npc_orgs": npc_orgs}
    pairs = []
    for co in char_orgs:
        for no in npc_orgs:
            s = get_org_affinity(campaign_id, co["id"], no["id"])
            pairs.append({"char_org": co["name"], "npc_org": no["name"], "score": s})
    avg_score = round(sum(p["score"] for p in pairs) / len(pairs)) if pairs else 0
    # Price modifier reuses same bands as personal affinity
    if avg_score <= -61:   mod = 1.50
    elif avg_score <= -21: mod = 1.20
    elif avg_score <=  20: mod = 1.00
    elif avg_score <=  60: mod = 0.90
    else:                  mod = 0.80
    return {"score": avg_score, "pairs": pairs, "mod": mod,
            "char_orgs": char_orgs, "npc_orgs": npc_orgs}


# ── Players ──────────────────────────────────────────────────────────────────────

def create_player(display_name: str) -> int:
    """Create a new player identity and return its id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO players (display_name, created_at, last_seen) VALUES (?, ?, ?)",
            (display_name, datetime.now().isoformat(), datetime.now().isoformat())
        )
        return cur.lastrowid


def get_player(player_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    return dict(row) if row else None


def touch_player(player_id: int):
    with _conn() as con:
        con.execute("UPDATE players SET last_seen=? WHERE id=?",
                    (datetime.now().isoformat(), player_id))


# ── Player tokens ───────────────────────────────────────────────────────────────

def create_player_token(campaign_id: int, character_name: str = '') -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    with _conn() as con:
        con.execute("""
            INSERT INTO player_tokens (token, campaign_id, character_name, created_at)
            VALUES (?, ?, ?, ?)
        """, (token, campaign_id, character_name, datetime.now().isoformat()))
    return token


def get_player_token(token: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM player_tokens WHERE token=? AND is_active=1", (token,)
        ).fetchone()
    return dict(row) if row else None


def list_player_tokens(campaign_id: int) -> list:
    with _conn() as con:
        rows = con.execute("""
            SELECT pt.*, p.display_name as player_display_name
            FROM player_tokens pt
            LEFT JOIN players p ON p.id = pt.player_id
            WHERE pt.campaign_id=?
            ORDER BY CASE WHEN pt.character_name='' THEN 1 ELSE 0 END, pt.character_name
        """, (campaign_id,)).fetchall()
    return [dict(r) for r in rows]


def update_player_token(token: str, character_name: str, player_id: int):
    """Attach a character and player identity to an existing token (called at setup)."""
    with _conn() as con:
        con.execute("""
            UPDATE player_tokens
            SET character_name=?, player_id=?, last_seen=?
            WHERE token=?
        """, (character_name, player_id, datetime.now().isoformat(), token))


def touch_player_token(token: str):
    with _conn() as con:
        con.execute(
            "UPDATE player_tokens SET last_seen=? WHERE token=?",
            (datetime.now().isoformat(), token)
        )


def deactivate_player_token(token: str):
    with _conn() as con:
        con.execute("UPDATE player_tokens SET is_active=0 WHERE token=?", (token,))


# ── Round submissions ───────────────────────────────────────────────────────────

def save_round_submission(session_key: str, round_num: int,
                          character_name: str, action_text: str):
    with _conn() as con:
        con.execute("""
            INSERT INTO round_submissions
                (session_key, round_num, character_name, action_text, submitted_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_key, round_num, character_name)
            DO UPDATE SET action_text=excluded.action_text,
                          submitted_at=excluded.submitted_at
        """, (session_key, round_num, character_name, action_text,
              datetime.now().isoformat()))


def get_round_submissions(session_key: str, round_num: int) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM round_submissions WHERE session_key=? AND round_num=? ORDER BY submitted_at",
            (session_key, round_num)
        ).fetchall()
    return [dict(r) for r in rows]


def clear_round_submissions(session_key: str, round_num: int):
    with _conn() as con:
        con.execute(
            "DELETE FROM round_submissions WHERE session_key=? AND round_num=?",
            (session_key, round_num)
        )


# ── Player direct messages ──────────────────────────────────────────────────────

def save_player_message(session_key: str, from_char: str,
                        to_char: str, message: str) -> int:
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO player_messages
                (session_key, from_character, to_character, message, sent_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_key, from_char, to_char, message, datetime.now().isoformat()))
        return cur.lastrowid


def get_player_messages(session_key: str, character_name: str) -> list:
    """Return all messages sent to or from this character in the session."""
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM player_messages
            WHERE session_key=?
              AND (from_character=? OR to_character=?)
            ORDER BY sent_at
        """, (session_key, character_name, character_name)).fetchall()
    return [dict(r) for r in rows]


def get_all_player_messages(session_key: str) -> list:
    """GM view — all DMs in the session."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM player_messages WHERE session_key=? ORDER BY sent_at",
            (session_key,)
        ).fetchall()
    return [dict(r) for r in rows]


def mark_messages_read(session_key: str, to_character: str):
    with _conn() as con:
        con.execute(
            "UPDATE player_messages SET read=1 WHERE session_key=? AND to_character=?",
            (session_key, to_character)
        )


# ── User account functions ─────────────────────────────────────────────────────

def create_user(email: str, password_hash: str) -> int:
    """Insert a new user row and return its id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email.lower().strip(), password_hash, datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_user_by_id(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None


def update_user_subscription(
    user_id: int,
    status: str,
    stripe_customer_id: str | None = None,
    stripe_sub_id: str | None = None,
):
    with _conn() as con:
        con.execute(
            """UPDATE users
               SET subscription_status=?,
                   stripe_customer_id=COALESCE(?, stripe_customer_id),
                   stripe_sub_id=COALESCE(?, stripe_sub_id)
               WHERE id=?""",
            (status, stripe_customer_id, stripe_sub_id, user_id),
        )


def touch_last_login(user_id: int):
    """Stamp last_login with the current UTC timestamp."""
    with _conn() as con:
        con.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.now().isoformat(), user_id),
        )


def get_user_by_stripe_customer(stripe_customer_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE stripe_customer_id=?", (stripe_customer_id,)
        ).fetchone()
        return dict(row) if row else None


def get_user_campaign_count(user_id: int) -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM campaigns WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else 0


def get_user_character_count(user_id: int) -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM characters WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else 0

