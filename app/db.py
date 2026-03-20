"""
SQLite database module.

Single shared aiosqlite connection opened at startup (lifespan) and closed
on shutdown.  WAL journal mode gives crash-safe writes and allows concurrent
readers without blocking.

Migration
---------
On first run the module checks whether existing queue.json / history.json
files are present and imports their contents automatically, so upgrading from
the JSON-based storage requires no manual steps.
"""
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get("DB_PATH", "/config/state.db"))

_db: Optional[aiosqlite.Connection] = None

# Increment when the schema changes.  The startup routine applies any pending
# migrations in order so existing databases are upgraded automatically.
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init_db(
    queue_json: Optional[Path] = None,
    history_json: Optional[Path] = None,
) -> None:
    """Open the database, create/migrate the schema, and import legacy JSON if present."""
    global _db
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row

    # WAL mode: readers never block writers; writers never block readers.
    # NORMAL sync is safe with WAL (data survives OS crash; only power-loss to
    # the WAL file itself could lose the last committed transaction).
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute("PRAGMA foreign_keys=ON")

    await _apply_schema()
    await _db.commit()

    await _migrate_from_json(queue_json, history_json)

    logger.info("Database ready: %s (schema v%d)", DB_PATH, SCHEMA_VERSION)


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


async def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() in lifespan first")
    return _db


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

async def _apply_schema() -> None:
    """Create tables and indexes if they don't exist, then run pending migrations."""
    # Create baseline tables — IF NOT EXISTS keeps this idempotent for existing DBs
    await _db.executescript("""
        -- Version tracking
        CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER PRIMARY KEY
        );

        -- Queue: ordered list of pending actions
        CREATE TABLE IF NOT EXISTS queue (
            id       TEXT PRIMARY KEY,
            position INTEGER NOT NULL,
            data     TEXT NOT NULL         -- full action dict as JSON
        );

        -- History: completed/failed action records
        CREATE TABLE IF NOT EXISTS history (
            id          TEXT    PRIMARY KEY,
            timestamp   REAL    NOT NULL,
            action_type TEXT    NOT NULL DEFAULT '',
            status      TEXT    NOT NULL DEFAULT '',
            source_path TEXT    NOT NULL DEFAULT '',
            source_name TEXT    NOT NULL DEFAULT '',
            dest_path   TEXT,
            dest_name   TEXT    NOT NULL DEFAULT '',
            destination TEXT    NOT NULL DEFAULT '',
            message     TEXT    NOT NULL DEFAULT '',
            data        TEXT    NOT NULL               -- full record as JSON
        );

        CREATE INDEX IF NOT EXISTS history_ts     ON history(timestamp);
        CREATE INDEX IF NOT EXISTS history_search ON history(source_name, dest_name, message);
    """)

    # Read the stored schema version (0 if this is a brand-new database)
    cur = await _db.execute("SELECT version FROM _schema_version")
    row = await cur.fetchone()
    current = row["version"] if row else 0

    # Apply incremental migrations in order.  Each block runs exactly once and
    # bumps the stored version so it is skipped on every subsequent startup.
    if current < 1:
        # Version 1 is the baseline schema created above — nothing extra to do.
        await _db.execute(
            "INSERT OR REPLACE INTO _schema_version (version) VALUES (1)"
        )
        current = 1

    # Template for future migrations:
    # if current < 2:
    #     await _db.execute("ALTER TABLE history ADD COLUMN new_col TEXT NOT NULL DEFAULT ''")
    #     await _db.execute("UPDATE _schema_version SET version = 2")
    #     current = 2


# ---------------------------------------------------------------------------
# JSON migration (runs once on first boot after upgrade)
# ---------------------------------------------------------------------------

async def _migrate_from_json(
    queue_json: Optional[Path],
    history_json: Optional[Path],
) -> None:
    """Import queue.json / history.json into SQLite if the tables are empty."""

    if queue_json and queue_json.exists():
        cur = await _db.execute("SELECT COUNT(*) FROM queue")
        if (await cur.fetchone())[0] == 0:
            try:
                items = json.loads(queue_json.read_text())
                for i, item in enumerate(items):
                    await _db.execute(
                        "INSERT OR IGNORE INTO queue (id, position, data) VALUES (?,?,?)",
                        (item.get("id") or f"migrated_{i}", i, json.dumps(item)),
                    )
                await _db.commit()
                logger.info("Migrated %d queue item(s) from %s", len(items), queue_json)
            except Exception as exc:
                logger.warning("Queue JSON migration failed: %s", exc)

    if history_json and history_json.exists():
        cur = await _db.execute("SELECT COUNT(*) FROM history")
        if (await cur.fetchone())[0] == 0:
            try:
                items = json.loads(history_json.read_text())
                for item in items:
                    await _db.execute(
                        """INSERT OR IGNORE INTO history
                           (id, timestamp, action_type, status, source_path, source_name,
                            dest_path, dest_name, destination, message, data)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            item.get("id") or secrets.token_hex(8),
                            item.get("timestamp") or time.time(),
                            item.get("action_type", ""),
                            item.get("status", ""),
                            item.get("source_path", ""),
                            item.get("source_name", ""),
                            item.get("dest_path"),
                            item.get("dest_name", ""),
                            item.get("destination", ""),
                            item.get("message", ""),
                            json.dumps(item),
                        ),
                    )
                await _db.commit()
                logger.info("Migrated %d history item(s) from %s", len(items), history_json)
            except Exception as exc:
                logger.warning("History JSON migration failed: %s", exc)
