"""
Queue routes backed by SQLite.

The queue is an ordered list of pending actions.  SQLite's ``position``
column defines order; ``save_queue`` rebuilds all positions from scratch
whenever the in-memory list changes (the queue is small — typically < 100
items — so a full replace is fast and keeps the logic simple).
"""
import json
import logging
import secrets

from fastapi import APIRouter, Body

from app.db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async helpers used by other modules
# ---------------------------------------------------------------------------

async def get_queue() -> list:
    """Return the queue as a list of action dicts, ordered by position."""
    db = await get_db()
    cur = await db.execute("SELECT data FROM queue ORDER BY position")
    rows = await cur.fetchall()
    result = []
    for row in rows:
        try:
            result.append(json.loads(row["data"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return result


async def save_queue(queue: list) -> None:
    """Persist the queue, replacing the entire table contents."""
    db = await get_db()
    await db.execute("DELETE FROM queue")
    for i, item in enumerate(queue):
        item_id = item.get("id") or secrets.token_hex(8)
        await db.execute(
            "INSERT OR REPLACE INTO queue (id, position, data) VALUES (?,?,?)",
            (item_id, i, json.dumps(item)),
        )
    await db.commit()


async def pop_first_item_by_id(action_id: str) -> None:
    """Remove the queue item with the given id (used after successful execution)."""
    db = await get_db()
    await db.execute("DELETE FROM queue WHERE id = ?", (action_id,))
    await db.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/queue")
async def read_queue():
    return await get_queue()


@router.post("/queue")
async def write_queue(queue: list = Body(...)):
    await save_queue(queue)
    return {"status": "ok"}


@router.delete("/queue")
async def clear_queue():
    db = await get_db()
    await db.execute("DELETE FROM queue")
    await db.commit()
    return {"status": "ok"}
