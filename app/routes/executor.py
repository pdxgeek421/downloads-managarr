import asyncio
import logging
import os
import shutil
from typing import Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel

from app.routes.config import get_config
from app.routes.history import append_history, get_history_raw
from app.routes.queue import get_queue, pop_first_item_by_id, save_queue
from app.services.executor import ConflictError, execute_action, atomic_move, verify_transfer

router = APIRouter()
logger = logging.getLogger(__name__)

# Serialise all execution requests so only one file transfer runs at a time.
_execute_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Post-transfer verification
# ---------------------------------------------------------------------------

def _verify_result(action: dict, dest_path: Optional[str]) -> tuple[bool, str]:
    """
    Blocking filesystem sanity-check after a transfer.  Call via asyncio.to_thread().

    Returns (ok, message).
    """
    action_type = action.get("action_type", "")
    source_path = action.get("source_path", "")
    is_unwrap   = bool(action.get("unwrap_folder"))

    if action_type == "delete_permanent":
        gone = not os.path.exists(source_path)
        return (gone, "Source removed" if gone
                else "Warning: source still exists after delete")

    if action_type == "delete_trash":
        ok = bool(dest_path and os.path.exists(dest_path))
        return (ok, "Confirmed in trash" if ok
                else "Warning: file not found in trash after move")

    if action_type in ("move", "copy"):
        # A skip resolution returns dest_path=None — nothing to verify
        if dest_path is None:
            return True, "Skipped"

        if not os.path.exists(dest_path):
            return False, "Warning: destination not found after transfer"

        # For plain moves the source should be gone (1:1 was verified pre-delete
        # inside atomic_move, so this is a final sanity check)
        if action_type == "move" and not is_unwrap and source_path:
            if os.path.exists(source_path):
                return False, "Warning: source still present after move"

        # For copies the source still exists — do a full 1:1 tree check
        if action_type == "copy" and not is_unwrap and source_path and os.path.exists(source_path):
            ok, msg = verify_transfer(source_path, dest_path)
            if not ok:
                return False, f"Warning: {msg}"

        return True, "Transfer confirmed"

    return True, "OK"


# ---------------------------------------------------------------------------
# Path validation helpers
# ---------------------------------------------------------------------------

def _allowed_source_paths(config: dict) -> list[str]:
    return [os.path.normpath(s["path"]) for s in config.get("sources", []) if s.get("path")]


def _allowed_dest_paths(config: dict) -> list[str]:
    paths = [os.path.normpath(d["path"]) for d in config.get("destinations", []) if d.get("path")]
    trash = config.get("trash_folder")
    if trash:
        paths.append(os.path.normpath(trash))
    return paths


def _in_allowed(path: str, allowed: list[str]) -> bool:
    p = os.path.normpath(path)
    return any(p == a or p.startswith(a + os.sep) for a in allowed)


def _validate_action_paths(action: dict, config: dict) -> Optional[str]:
    """Return an error string if the action's paths fall outside configured roots."""
    source = action.get("source_path", "")
    if not source:
        return "Missing source_path"

    allowed_sources = _allowed_source_paths(config)
    if allowed_sources and not _in_allowed(source, allowed_sources):
        logger.warning("Rejected action: source %s not in configured sources", source)
        return "Source path is not within any configured source folder"

    action_type = action.get("action_type", "")
    if action_type in ("move", "copy"):
        dest = action.get("destination", "")
        if not dest:
            return "Missing destination for move/copy action"
        allowed_dests = _allowed_dest_paths(config)
        if allowed_dests and not _in_allowed(dest, allowed_dests):
            logger.warning("Rejected action: destination %s not in configured dests", dest)
            return "Destination is not within any configured destination folder"

    if action_type == "extract":
        dest = action.get("destination", "")
        if not dest:
            return "Missing destination for extract action"
        # Extract destination may be a source (in-place) or a destination
        allowed = _allowed_source_paths(config) + _allowed_dest_paths(config)
        if allowed and not _in_allowed(dest, allowed):
            logger.warning("Rejected extract: destination %s not in configured paths", dest)
            return "Extract destination is not within any configured folder"

    return None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ConflictResolution(BaseModel):
    action_id: str
    resolution: str  # "skip" | "overwrite" | "rename"


class ExecuteRequest(BaseModel):
    conflict_resolution: Optional[ConflictResolution] = None


# ---------------------------------------------------------------------------
# Execute routes
# ---------------------------------------------------------------------------

@router.post("/execute")
async def execute_queue(body: Optional[ExecuteRequest] = None):
    async with _execute_lock:
        queue = await get_queue()
        if not queue:
            return {"status": "complete", "results": []}

        config = get_config()
        days = config.get("history_days", 30)
        trash_mode = config.get("trash_mode", "auto")
        trash = "__auto__" if trash_mode == "auto" else config.get("trash_folder")
        extract_temp = config.get("extract_temp_folder")

        resolution_map: dict[str, str] = {}
        if body and body.conflict_resolution:
            cr = body.conflict_resolution
            resolution_map[cr.action_id] = cr.resolution

        results = []

        for action in list(queue):
            action_id = action.get("id", "")

            err = _validate_action_paths(action, config)
            if err:
                results.append({"action_id": action_id, "status": "error", "message": err})
                queue.remove(action)
                await save_queue(queue)
                await append_history(action, "error", err, days=days)
                continue

            resolution = resolution_map.get(action_id)
            try:
                msg, dest_path = await asyncio.to_thread(
                    execute_action, action, resolution, trash, extract_temp
                )
                results.append({"action_id": action_id, "status": "success", "message": msg})
                queue.remove(action)
                await save_queue(queue)
                await append_history(action, "success", msg, dest_path, days=days)
                logger.info("Executed %s: %s", action_id, msg)

            except ConflictError as e:
                return {
                    "status": "conflict",
                    "completed": results,
                    "conflict": {
                        "action": action,
                        "conflicting_path": e.conflict_path,
                        "moved_before_conflict": e.moved_count,
                    },
                }

            except (FileNotFoundError, PermissionError, ValueError, OSError) as e:
                logger.error("Action %s failed: %s", action_id, e)
                results.append({"action_id": action_id, "status": "error", "message": str(e)})
                queue.remove(action)
                await save_queue(queue)
                await append_history(action, "error", str(e), days=days)

        return {"status": "complete", "results": results}


@router.post("/execute/next")
async def execute_next(body: Optional[ExecuteRequest] = None):
    """Process only the first queue item — used by the frontend for per-item progress."""
    async with _execute_lock:
        queue = await get_queue()
        if not queue:
            return {"status": "empty"}

        action = queue[0]
        action_id = action.get("id", "")
        config = get_config()
        days = config.get("history_days", 30)
        trash_mode = config.get("trash_mode", "auto")
        trash = "__auto__" if trash_mode == "auto" else config.get("trash_folder")
        extract_temp = config.get("extract_temp_folder")

        err = _validate_action_paths(action, config)
        if err:
            await pop_first_item_by_id(action_id)
            await append_history(action, "error", err, days=days)
            return {"status": "error", "action": action, "message": err}

        resolution = None
        if body and body.conflict_resolution and body.conflict_resolution.action_id == action_id:
            resolution = body.conflict_resolution.resolution

        try:
            msg, dest_path = await asyncio.to_thread(
                execute_action, action, resolution, trash, extract_temp
            )
            verify_ok, verify_msg = await asyncio.to_thread(
                _verify_result, action, dest_path
            )
            if not verify_ok:
                logger.warning("Verification failed for %s: %s", action_id, verify_msg)
            await pop_first_item_by_id(action_id)
            await append_history(action, "success", msg, dest_path, days=days)
            logger.info("Executed next %s: %s", action_id, msg)
            return {
                "status": "success",
                "action": action,
                "message": msg,
                "verify_ok": verify_ok,
                "verify_msg": verify_msg,
            }

        except ConflictError as e:
            return {
                "status": "conflict",
                "conflict": {
                    "action": action,
                    "conflicting_path": e.conflict_path,
                    "moved_before_conflict": e.moved_count,
                },
            }

        except (FileNotFoundError, PermissionError, ValueError, OSError) as e:
            logger.error("Action %s failed: %s", action_id, e)
            await pop_first_item_by_id(action_id)
            await append_history(action, "error", str(e), days=days)
            return {"status": "error", "action": action, "message": str(e)}


@router.post("/execute/direct")
async def execute_direct(body: dict = Body(...)):
    """Execute a list of actions immediately without touching the queue."""
    async with _execute_lock:
        config = get_config()
        days = config.get("history_days", 30)
        trash_mode = config.get("trash_mode", "auto")
        trash = "__auto__" if trash_mode == "auto" else config.get("trash_folder")
        extract_temp = config.get("extract_temp_folder")
        actions = body.get("actions", [])
        results = []

        for action in actions:
            err = _validate_action_paths(action, config)
            if err:
                results.append({"status": "error", "action": action, "message": err})
                await append_history(action, "error", err, days=days)
                continue
            try:
                msg, dest_path = await asyncio.to_thread(
                    execute_action, action, None, trash, extract_temp
                )
                verify_ok, verify_msg = await asyncio.to_thread(
                    _verify_result, action, dest_path
                )
                if not verify_ok:
                    logger.warning("Verification failed for direct action: %s", verify_msg)
                await append_history(action, "success", msg, dest_path, days=days)
                logger.info("Direct execute: %s", msg)
                results.append({
                    "status": "success",
                    "action": action,
                    "message": msg,
                    "verify_ok": verify_ok,
                    "verify_msg": verify_msg,
                })
            except ConflictError as e:
                results.append({
                    "status": "conflict",
                    "action": action,
                    "conflict": {"action": action, "conflicting_path": e.conflict_path},
                })
            except (FileNotFoundError, PermissionError, ValueError, OSError) as e:
                logger.error("Direct action failed: %s", e)
                await append_history(action, "error", str(e), days=days)
                results.append({"status": "error", "action": action, "message": str(e)})

        return {"results": results}


# ---------------------------------------------------------------------------
# History revert
# ---------------------------------------------------------------------------

@router.post("/history/revert")
async def revert_history_item(body: dict = Body(...)):
    """Revert a completed history action."""
    history_id = body.get("id")
    history = await get_history_raw()
    item = next((h for h in history if h.get("id") == history_id), None)
    if not item:
        # Fall back to paths supplied directly by the frontend (history record may
        # have been pruned by retention policy or a clear-history call)
        action_type = body.get("action_type")
        source_path = body.get("source_path")
        dest_path   = body.get("dest_path")
        if not (action_type and dest_path):
            return {"status": "error", "message": "History record not found and insufficient data to restore"}
    else:
        action_type = item.get("action_type")
        source_path = item.get("source_path")
        dest_path   = item.get("dest_path")

    if action_type == "delete_permanent":
        return {"status": "error", "message": "Cannot revert a permanent deletion"}

    if not dest_path:
        return {"status": "error", "message": "No destination path recorded — revert not available for this entry"}

    if not os.path.exists(dest_path):
        return {"status": "error", "message": f"File no longer at expected location: {dest_path}"}

    try:
        if action_type in ("move", "delete_trash"):
            source_dir = os.path.dirname(source_path)
            if not os.path.exists(source_dir):
                return {"status": "error", "message": f"Original location no longer exists: {source_dir}"}
            if os.path.exists(source_path):
                return {"status": "error", "message": f"A file already exists at the original location: {source_path}"}
            await asyncio.to_thread(atomic_move, dest_path, source_path)
            return {"status": "ok", "message": f"Reverted: moved back to {source_path}"}

        if action_type == "copy":
            if os.path.isdir(dest_path):
                await asyncio.to_thread(shutil.rmtree, dest_path)
            else:
                await asyncio.to_thread(os.remove, dest_path)
            return {"status": "ok", "message": f"Reverted: deleted copy at {dest_path}"}

        if action_type == "restore":
            config = get_config()
            trash_mode = config.get("trash_mode") or "auto"
            if trash_mode == "auto":
                # Re-trash next to the item's current location
                trash = os.path.join(os.path.dirname(dest_path), ".Trash")
            else:
                trash = config.get("trash_folder")
                if not trash:
                    return {"status": "error", "message": "No trash folder configured"}
            os.makedirs(trash, exist_ok=True)
            name = os.path.basename(dest_path)
            trash_dest = os.path.join(trash, name)
            if os.path.exists(trash_dest):
                return {"status": "error", "message": f"A file already exists in trash: {trash_dest}"}
            await asyncio.to_thread(atomic_move, dest_path, trash_dest)
            return {"status": "ok", "message": "Reverted: moved back to trash"}

    except (OSError, PermissionError) as e:
        logger.error("Revert failed: %s", e)
        return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Revert not supported for action type: {action_type}"}
