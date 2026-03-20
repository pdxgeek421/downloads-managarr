"""
History routes backed by SQLite.

Each completed or failed action is stored as a row in the ``history`` table.
Indexed columns (action_type, status, source_name, dest_name, message,
timestamp) allow fast filtering without deserialising the full JSON blob.

Retention pruning happens in ``append_history`` — old rows are deleted in the
same transaction as the new insert so the table stays bounded.
"""
import json
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Body, Query

from app.db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async helpers used by other modules
# ---------------------------------------------------------------------------

async def get_history_raw() -> list:
    """Return all history records as a list of dicts (newest first)."""
    db = await get_db()
    cur = await db.execute(
        "SELECT data FROM history ORDER BY timestamp DESC"
    )
    rows = await cur.fetchall()
    result = []
    for row in rows:
        try:
            result.append(json.loads(row["data"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return result


async def append_history(
    action: dict,
    status: str,
    message: str,
    dest_path: Optional[str] = None,
    days: int = 30,
) -> None:
    """Insert a history record and prune entries older than *days* days."""
    db = await get_db()
    now = time.time()

    record = {
        "id":          secrets.token_hex(8),   # always fresh — action IDs must not collide on retry
        "action_type": action.get("action_type", ""),
        "source_path": action.get("source_path", ""),
        "source_name": os.path.basename(action.get("source_path", "")),
        "destination": action.get("destination", ""),
        "dest_name":   action.get("dest_name", ""),
        "dest_path":   dest_path,
        "status":      status,
        "message":     message,
        "timestamp":   now,
    }

    await db.execute(
        """INSERT OR REPLACE INTO history
           (id, timestamp, action_type, status, source_path, source_name,
            dest_path, dest_name, destination, message, data)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record["id"],
            now,
            record["action_type"],
            status,
            record["source_path"],
            record["source_name"],
            dest_path,
            record["dest_name"],
            record["destination"],
            message,
            json.dumps(record),
        ),
    )

    # Prune old records in the same transaction
    if days != -1:
        cutoff = now - days * 86400
        await db.execute("DELETE FROM history WHERE timestamp < ?", (cutoff,))

    await db.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/history")
async def read_history(
    search: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    from app.routes.config import get_config
    config = get_config()
    days = config.get("history_days", 30)

    db = await get_db()

    cutoff = (time.time() - days * 86400) if days != -1 else 0.0

    if search:
        # Escape SQLite LIKE metacharacters so the search is literal
        safe = search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{safe}%"
        cur = await db.execute(
            """SELECT data FROM history
               WHERE timestamp >= ?
                 AND (source_name LIKE ? ESCAPE '\\'
                      OR dest_name LIKE ? ESCAPE '\\'
                      OR message   LIKE ? ESCAPE '\\')
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?""",
            (cutoff, pattern, pattern, pattern, limit, offset),
        )
    else:
        cur = await db.execute(
            """SELECT data FROM history
               WHERE timestamp >= ?
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?""",
            (cutoff, limit, offset),
        )

    rows = await cur.fetchall()
    result = []
    for row in rows:
        try:
            result.append(json.loads(row["data"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return result


@router.delete("/history")
async def clear_history(body: dict = Body(default={})):
    """Clear history, optionally preserving entries whose IDs are in exclude_ids."""
    exclude_ids = list(body.get("exclude_ids", []))
    db = await get_db()

    if exclude_ids:
        # Keep only the excluded IDs
        placeholders = ",".join("?" * len(exclude_ids))
        await db.execute(
            f"DELETE FROM history WHERE id NOT IN ({placeholders})",
            exclude_ids,
        )
    else:
        await db.execute("DELETE FROM history")

    await db.commit()
    return {"status": "ok"}
