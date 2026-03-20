import asyncio
import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Body, Query

from app.routes.config import get_config
from app.routes.history import append_history
from app.services.executor import atomic_move

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/trash")
async def list_trash():
    config = get_config()
    trash = config.get("trash_folder")
    if not trash or not os.path.exists(trash):
        return []

    def _scan() -> list:
        items = []
        for entry in sorted(os.scandir(trash), key=lambda e: e.name.lower()):
            if entry.name.startswith("."):
                continue
            stat = entry.stat(follow_symlinks=False)
            size = None
            if entry.is_file(follow_symlinks=False):
                size = stat.st_size
            elif entry.is_dir(follow_symlinks=False):
                total = 0
                try:
                    for f in Path(entry.path).rglob("*"):
                        try:
                            if not f.is_symlink() and f.is_file():
                                total += f.stat().st_size
                        except (PermissionError, OSError):
                            pass
                except (PermissionError, OSError):
                    pass
                size = total
            items.append({
                "name": entry.name,
                "path": entry.path,
                "type": "folder" if entry.is_dir() else "file",
                "size": size,
                "modified": stat.st_mtime,
            })
        return items

    return await asyncio.to_thread(_scan)


@router.post("/trash/restore")
async def restore_from_trash(body: dict = Body(...)):
    path = body.get("path")
    destination = body.get("destination")

    if not path or not os.path.exists(path):
        return {"status": "error", "message": "Item not found in trash"}
    if not destination:
        return {"status": "error", "message": "No destination provided"}

    config = get_config()
    days = config.get("history_days", 30)

    def _restore() -> str:
        os.makedirs(destination, exist_ok=True)
        name = os.path.basename(path)
        dest = os.path.join(destination, name)
        if os.path.exists(dest):
            stem, ext = os.path.splitext(name)
            n = 1
            while os.path.exists(dest):
                dest = os.path.join(destination, f"{stem} ({n}){ext}")
                n += 1
        atomic_move(path, dest)
        return dest

    try:
        final_dest = await asyncio.to_thread(_restore)
        name = os.path.basename(path)
        action = {
            "action_type": "restore",
            "source_path": path,
            "destination": destination,
            "dest_name": os.path.basename(final_dest),
        }
        await append_history(action, "success", f"Restored '{name}' → {final_dest}", final_dest, days=days)
        return {"status": "ok", "message": f"Restored '{name}' → {final_dest}"}
    except (OSError, PermissionError) as e:
        logger.error("Restore failed: %s", e)
        return {"status": "error", "message": str(e)}


@router.delete("/trash/item")
async def delete_trash_item(path: str = Query(...)):
    config = get_config()
    trash = config.get("trash_folder")
    if not trash:
        return {"status": "error", "message": "No trash folder configured"}
    norm_path  = os.path.normpath(path)
    norm_trash = os.path.normpath(trash)
    if not (norm_path == norm_trash or norm_path.startswith(norm_trash + os.sep)):
        return {"status": "error", "message": "Path is not within the configured trash folder"}
    if not os.path.exists(path):
        return {"status": "error", "message": "Item not found"}

    def _delete() -> None:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    try:
        await asyncio.to_thread(_delete)
        return {"status": "ok"}
    except (OSError, PermissionError) as e:
        logger.error("Delete trash item failed: %s", e)
        return {"status": "error", "message": str(e)}


@router.delete("/trash")
async def empty_trash():
    config = get_config()
    trash = config.get("trash_folder")
    if not trash or not os.path.exists(trash):
        return {"status": "ok"}

    def _empty() -> None:
        for entry in os.scandir(trash):
            if entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path)
            else:
                os.remove(entry.path)

    try:
        await asyncio.to_thread(_empty)
        return {"status": "ok"}
    except (OSError, PermissionError) as e:
        logger.error("Empty trash failed: %s", e)
        return {"status": "error", "message": str(e)}
