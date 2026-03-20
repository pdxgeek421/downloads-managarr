import asyncio
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Query

from app.routes.config import get_config

router = APIRouter()

# ---------------------------------------------------------------------------
# Size cache — avoid recomputing large directory trees on every request
# ---------------------------------------------------------------------------
_size_cache: dict[str, tuple[float, int]] = {}  # path → (monotonic_time, bytes)
_SIZE_CACHE_TTL = 60  # seconds


# ---------------------------------------------------------------------------
# Path containment guard
# ---------------------------------------------------------------------------

def _path_is_allowed(path: str, config: dict) -> bool:
    """Return True if *path* is within any configured source, destination, or trash folder."""
    p = os.path.normpath(path)
    allowed: list[str] = []
    for s in config.get("sources", []):
        if s.get("path"):
            allowed.append(os.path.normpath(s["path"]))
    for d in config.get("destinations", []):
        if d.get("path"):
            allowed.append(os.path.normpath(d["path"]))
    trash = config.get("trash_folder")
    if trash:
        allowed.append(os.path.normpath(trash))
    return any(p == a or p.startswith(a + os.sep) for a in allowed)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/files")
async def list_files(
    limit: int = Query(default=0, ge=0, description="Max items to return (0 = all)"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
):
    config = get_config()
    sources = config.get("sources", [])
    items: list[dict] = []
    missing_paths: list[dict] = []

    for source in sources:
        path = source.get("path", "")
        label = source.get("label", path)
        p = Path(path)

        if not p.exists():
            missing_paths.append({"label": label, "path": path})
            continue

        if not p.is_dir():
            missing_paths.append({"label": label, "path": path, "reason": "not a directory"})
            continue

        try:
            for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
                try:
                    stat = entry.stat()
                    items.append({
                        "name": entry.name,
                        "path": str(entry),
                        "source_label": label,
                        "source_path": path,
                        "type": "folder" if entry.is_dir() else "file",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
                except (PermissionError, OSError):
                    items.append({
                        "name": entry.name,
                        "path": str(entry),
                        "source_label": label,
                        "source_path": path,
                        "type": "folder" if entry.is_dir() else "file",
                        "size": 0,
                        "modified": 0,
                        "error": "permission denied",
                    })
        except PermissionError:
            missing_paths.append({"label": label, "path": path, "reason": "permission denied"})

    total = len(items)
    if limit > 0:
        items = items[offset:offset + limit]

    return {
        "items": items,
        "missing_paths": missing_paths,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/browse")
async def browse_directory(path: str = Query(default="/")):
    # Reject explicit path-traversal sequences before resolving
    raw_parts = Path(path).parts
    if ".." in raw_parts:
        return {"path": path, "dirs": [], "parent": None, "error": "Path traversal not allowed"}

    try:
        p = Path(os.path.normpath(path))
    except (ValueError, OSError):
        return {"path": path, "dirs": [], "parent": None, "error": "Invalid path"}

    if not p.exists():
        return {"path": str(p), "dirs": [], "parent": None, "error": "Path does not exist"}

    if not p.is_dir():
        return {"path": str(p), "dirs": [], "parent": None, "error": "Not a directory"}

    try:
        dirs = []
        for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_dir():
                try:
                    entry.stat()
                    dirs.append({"name": entry.name, "path": str(entry)})
                except (PermissionError, OSError):
                    dirs.append({"name": entry.name, "path": str(entry), "inaccessible": True})
    except PermissionError:
        return {
            "path": str(p),
            "dirs": [],
            "parent": str(p.parent) if p != p.parent else None,
            "error": "Permission denied",
        }

    parent = str(p.parent) if p != p.parent else None
    return {"path": str(p), "dirs": dirs, "parent": parent}


@router.get("/ls")
async def list_directory(path: str = Query(...)):
    """List all contents (files + folders) of a specific path for in-app folder navigation."""
    raw_parts = Path(path).parts
    if ".." in raw_parts:
        return {"items": [], "total": 0, "error": "Path traversal not allowed"}
    try:
        p = Path(os.path.normpath(path))
    except (ValueError, OSError):
        return {"items": [], "total": 0, "error": "Invalid path"}
    config = get_config()
    if not _path_is_allowed(str(p), config):
        return {"items": [], "total": 0, "error": "Path is not within any configured folder"}
    if not p.exists() or not p.is_dir():
        return {"items": [], "total": 0, "error": "Not a directory"}

    # Resolve which configured source this path belongs to
    source_label = p.name
    source_root  = str(p)
    for source in config.get("sources", []):
        src_path = source.get("path", "")
        if str(p).startswith(src_path):
            source_label = source.get("label", src_path)
            source_root  = src_path
            break

    items: list[dict] = []
    try:
        for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
            try:
                stat = entry.stat()
                items.append({
                    "name":         entry.name,
                    "path":         str(entry),
                    "source_label": source_label,
                    "source_path":  source_root,
                    "type":         "folder" if entry.is_dir() else "file",
                    "size":         stat.st_size,
                    "modified":     stat.st_mtime,
                })
            except (PermissionError, OSError):
                items.append({
                    "name":         entry.name,
                    "path":         str(entry),
                    "source_label": source_label,
                    "source_path":  source_root,
                    "type":         "folder" if entry.is_dir() else "file",
                    "size":         0,
                    "modified":     0,
                    "error":        "permission denied",
                })
    except PermissionError:
        return {"items": [], "total": 0, "error": "Permission denied"}

    return {"items": items, "total": len(items)}


@router.get("/size")
async def get_folder_size(path: str = Query(...)):
    """Recursively compute the total size of a directory (runs in a thread pool, TTL-cached)."""
    config = get_config()
    if not _path_is_allowed(path, config):
        return {"path": path, "size": None, "error": "Path is not within any configured folder"}

    # Return cached value if still fresh
    cached = _size_cache.get(path)
    if cached is not None and time.monotonic() - cached[0] < _SIZE_CACHE_TTL:
        return {"path": path, "size": cached[1]}

    def _compute(p: Path) -> dict:
        if not p.exists():
            return {"path": str(p), "size": None, "error": "not found"}
        if not p.is_dir():
            size = p.stat().st_size
            _size_cache[path] = (time.monotonic(), size)
            return {"path": str(p), "size": size}
        total = 0
        try:
            for entry in p.rglob("*"):
                try:
                    if not entry.is_symlink() and entry.is_file():
                        total += entry.stat().st_size
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
        _size_cache[path] = (time.monotonic(), total)
        return {"path": str(p), "size": total}

    return await asyncio.to_thread(_compute, Path(path))


@router.get("/extract/info")
async def extract_info(path: str = Query(...)):
    """Return archive metadata and available space for the configured temp folder."""
    from app.services.extractor import get_archive_info, get_free_space

    config = get_config()
    if not _path_is_allowed(path, config):
        return {"error": "Path is not within any configured folder"}

    def _get() -> dict:
        cfg = get_config()
        temp_folder = cfg.get("extract_temp_folder")
        info = get_archive_info(path)
        result = dict(info)
        uncompressed = info.get("uncompressed_size", 0)
        if temp_folder:
            free = get_free_space(temp_folder)
            result["temp_folder"] = temp_folder
            result["temp_free"] = free
            result["space_ok"] = (free is None or free >= uncompressed)
        else:
            free = get_free_space(path)
            result["temp_folder"] = None
            result["temp_free"] = free
            result["space_ok"] = True
        return result

    return await asyncio.to_thread(_get)


@router.get("/disk-stats")
async def disk_stats():
    """Return disk usage for all configured source and destination paths."""
    config = get_config()

    def _stat(path: str, label: str, kind: str) -> dict:
        # Walk up to the nearest existing ancestor so configured-but-not-yet-created
        # paths still return meaningful disk stats (same volume).
        check = Path(path)
        while not check.exists() and check != check.parent:
            check = check.parent
        try:
            usage = shutil.disk_usage(str(check))
            return {
                "path":  path,
                "label": label,
                "kind":  kind,
                "total": usage.total,
                "used":  usage.used,
                "free":  usage.free,
            }
        except OSError as exc:
            return {"path": path, "label": label, "kind": kind, "error": str(exc)}

    # Collect unique paths to check
    to_check: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for src in config.get("sources", []):
        p = src.get("path", "")
        if p and p not in seen:
            seen.add(p)
            to_check.append((p, src.get("label", p), "source"))

    for dst in config.get("destinations", []):
        p = dst.get("path", "")
        if p and p not in seen:
            seen.add(p)
            to_check.append((p, dst.get("label", p), "dest"))

    # Run all disk_usage calls concurrently in the thread pool (avoids blocking
    # the event loop, especially important for NFS/SMB mounts).
    stats = await asyncio.gather(
        *[asyncio.to_thread(_stat, p, label, kind) for p, label, kind in to_check]
    )
    return {"stats": list(stats)}
