"""
Pure synchronous file-execution logic.

All functions here are blocking (shutil, os I/O) and must be called via
asyncio.to_thread() from async route handlers so they don't block the event loop.

Atomicity strategy
------------------
A plain shutil.move() is only atomic when source and destination are on the
same filesystem (it resolves to a single os.rename() call).  In Docker every
source/destination pair typically lives on a separate bind-mount, so shutil
falls back to copy-then-delete — leaving a partial file at the destination if
the process is killed mid-stream.

Instead we use a three-phase approach for all cross-filesystem transfers:

  1. Copy/move data to  <final_dest>.managarr.tmp  (same directory → same fs)
  2. os.replace(<tmp>, <final_dest>)               (atomic rename on POSIX)
  3. verify_transfer() — 1:1 size check before source is touched
  4. Delete the source (moves only, after step 3 passes)

If the process dies between steps 1 and 2 the destination is untouched; only
the clearly-named .managarr.tmp file is left behind.  If it dies between
steps 2 and 4 the destination is complete and the source is a harmless
duplicate.  If step 3 detects a discrepancy the source is never deleted and
an OSError is raised so the caller can surface the problem.

For same-filesystem moves we skip the temp file entirely and call os.rename()
directly — still atomic, and fast because no data is copied.
"""

import errno
import logging
import os
import shutil
import threading
import time
from typing import Optional

from app.services.extractor import extract_archive

logger = logging.getLogger(__name__)

TMP_SUFFIX = ".managarr.tmp"

# ---------------------------------------------------------------------------
# Transfer progress tracking (updated from the copy thread, read by the API)
# ---------------------------------------------------------------------------

_progress_lock = threading.Lock()
_transfer_progress: dict = {
    "active": False,
    "bytes_transferred": 0,
    "bytes_total": 0,
    "file_name": "",
    "started_at": 0.0,
}


def get_transfer_progress() -> dict:
    """Return a snapshot of the current transfer progress (thread-safe)."""
    with _progress_lock:
        p = dict(_transfer_progress)
    if p["active"] and p["started_at"] > 0 and p["bytes_transferred"] > 0:
        elapsed = time.monotonic() - p["started_at"]
        p["speed_bps"] = p["bytes_transferred"] / elapsed if elapsed > 0 else 0
    else:
        p["speed_bps"] = 0
    return p


def _dir_size(path: str) -> int:
    """Return total byte size of all files under *path*."""
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


_BUF = 1024 * 1024  # 1 MiB copy buffer


def _progress_copy_fn(src: str, dst: str) -> None:
    """shutil.copy2 replacement used by copytree — tracks per-chunk progress."""
    with _progress_lock:
        _transfer_progress["file_name"] = os.path.basename(src)
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            chunk = fi.read(_BUF)
            if not chunk:
                break
            fo.write(chunk)
            with _progress_lock:
                _transfer_progress["bytes_transferred"] += len(chunk)
    shutil.copystat(src, dst)


def _copy_file_with_progress(src: str, dst: str) -> None:
    """Copy a single file tracking byte-level progress."""
    file_size = os.path.getsize(src)
    with _progress_lock:
        _transfer_progress.update({
            "active": True,
            "bytes_transferred": 0,
            "bytes_total": file_size,
            "file_name": os.path.basename(src),
            "started_at": time.monotonic(),
        })
    try:
        with open(src, "rb") as fi, open(dst, "wb") as fo:
            while True:
                chunk = fi.read(_BUF)
                if not chunk:
                    break
                fo.write(chunk)
                with _progress_lock:
                    _transfer_progress["bytes_transferred"] += len(chunk)
        shutil.copystat(src, dst)
    finally:
        with _progress_lock:
            _transfer_progress["active"] = False


class ConflictError(Exception):
    """Raised when a destination path already exists and no resolution was given."""

    def __init__(self, conflict_path: str, moved_count: int = 0) -> None:
        self.conflict_path = conflict_path
        self.moved_count = moved_count  # items already transferred before conflict (unwrap)
        super().__init__(conflict_path)


# ---------------------------------------------------------------------------
# 1:1 content verification
# ---------------------------------------------------------------------------

def verify_transfer(source: str, dest: str) -> tuple[bool, str]:
    """
    Confirm every file that exists in *source* is present in *dest* with a
    matching byte size.

    Called inside atomic_move() BEFORE the source is deleted on cross-fs
    transfers, and from the route layer to verify completed copy operations.

    Returns (ok, message).
    """
    if os.path.isfile(source):
        if not os.path.isfile(dest):
            return False, f"Destination file not found: {dest}"
        src_sz = os.path.getsize(source)
        dst_sz = os.path.getsize(dest)
        if src_sz != dst_sz:
            return False, f"Size mismatch: source {src_sz:,} B ≠ dest {dst_sz:,} B"
        return True, "OK"

    if os.path.isdir(source):
        missing  = []
        mismatch = []
        for dirpath, _dirs, filenames in os.walk(source):
            rel = os.path.relpath(dirpath, source)
            for fname in filenames:
                src_file = os.path.join(dirpath, fname)
                dst_file = os.path.join(dest, rel, fname)
                if not os.path.exists(dst_file):
                    missing.append(os.path.join(rel, fname))
                elif os.path.getsize(src_file) != os.path.getsize(dst_file):
                    mismatch.append(os.path.join(rel, fname))
        if missing:
            n = len(missing)
            return False, f"{n} file{'s' if n != 1 else ''} missing at destination"
        if mismatch:
            n = len(mismatch)
            return False, f"{n} file{'s' if n != 1 else ''} with size mismatch at destination"
        return True, "OK"

    return False, f"Source is neither a file nor a directory: {source}"


# ---------------------------------------------------------------------------
# Atomic copy / move primitives
# ---------------------------------------------------------------------------

def atomic_copy(source: str, final_dest: str) -> None:
    """
    Copy *source* to *final_dest* atomically.

    Copies to ``final_dest + TMP_SUFFIX`` first (same directory → same
    filesystem as the target), then atomically renames to *final_dest*.
    Cleans up the tmp path on any error so the destination is never left in a
    partial state.  Progress is tracked in ``_transfer_progress`` so the
    frontend can poll ``/api/transfer/progress`` for live bytes/speed data.
    """
    tmp = final_dest + TMP_SUFFIX
    # Remove any leftover tmp from a previous failed transfer
    _cleanup_tmp(tmp)
    try:
        if os.path.isdir(source):
            total = _dir_size(source)
            with _progress_lock:
                _transfer_progress.update({
                    "active": True,
                    "bytes_transferred": 0,
                    "bytes_total": total,
                    "file_name": os.path.basename(source) + "/",
                    "started_at": time.monotonic(),
                })
            try:
                shutil.copytree(source, tmp, copy_function=_progress_copy_fn)
            finally:
                with _progress_lock:
                    _transfer_progress["active"] = False
        else:
            _copy_file_with_progress(source, tmp)
        os.replace(tmp, final_dest)          # atomic on POSIX, same-fs rename
    except Exception:
        _cleanup_tmp(tmp)
        raise


def atomic_move(source: str, final_dest: str) -> None:
    """
    Move *source* to *final_dest* atomically regardless of filesystem boundary.

    Fast path: same-filesystem → single os.rename() call (truly atomic).
    Cross-filesystem: copy to tmp → atomic rename → delete source.
    The source is only removed after the destination is fully committed.
    """
    try:
        os.rename(source, final_dest)        # succeeds iff same filesystem
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:         # only cross-device errors fall through
            raise
        # EXDEV: cross-filesystem move — fall back to copy + delete

    atomic_copy(source, final_dest)

    # Verify 1:1 before touching the source — if something is wrong the
    # source is untouched and we raise so the caller can surface the error.
    ok, msg = verify_transfer(source, final_dest)
    if not ok:
        raise OSError(
            f"Pre-delete verification failed — source preserved at {source!r}: {msg}"
        )

    # Source delete: destination is committed and verified.
    try:
        if os.path.isdir(source):
            shutil.rmtree(source)
        else:
            os.remove(source)
    except OSError as exc:
        # Check whether .nfs* NFS open-file placeholders are the only obstacle
        if os.path.isdir(source):
            remnants = [f for f in os.listdir(source) if f.startswith('.nfs')]
            if remnants:
                logger.info(
                    "Atomic move: source %r not removed — %d .nfs* lock file(s) remain "
                    "(NFS open-file placeholders; auto-cleaned by OS when handles close)",
                    source, len(remnants),
                )
                return  # transfer is complete; leave cleanup to the OS
        logger.warning("Atomic move: destination committed but source delete failed: %s", exc)


def _cleanup_tmp(tmp: str) -> None:
    """Remove a leftover .managarr.tmp path, ignoring errors."""
    try:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp)
        elif os.path.exists(tmp):
            os.remove(tmp)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_dest_info(action: dict) -> dict:
    source_path = action["source_path"]
    source_name = os.path.basename(source_path)
    item_name   = action.get("dest_name") or source_name
    dest_base   = action.get("destination", "")
    wrap        = action.get("wrap_in_folder") and action.get("source_type") == "file"

    if wrap:
        folder_name        = os.path.splitext(item_name)[0]
        dest_folder        = os.path.join(dest_base, folder_name)
        conflict_check_path = dest_folder
    else:
        dest_folder        = dest_base
        conflict_check_path = os.path.join(dest_base, item_name)

    return {
        "dest_folder":        dest_folder,
        "item_name":          item_name,
        "conflict_check_path": conflict_check_path,
        "source_name":        source_name,
        "dest_base":          dest_base,
        "wrap":               wrap,
    }


def _perform_transfer(action: dict, dest_folder: str, item_name: str) -> tuple[str, str]:
    """
    Atomically move or copy *source* to ``dest_folder/item_name``.
    Returns (human-readable message, final_dest_path).
    """
    source_path = action["source_path"]
    action_type = action["action_type"]
    os.makedirs(dest_folder, exist_ok=True)
    final_dest = os.path.join(dest_folder, item_name)

    if action_type == "move":
        atomic_move(source_path, final_dest)
        verb = "Moved"
    else:
        atomic_copy(source_path, final_dest)
        verb = "Copied"

    return f"{verb} '{os.path.basename(source_path)}' → {final_dest}", final_dest


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_action(
    action: dict,
    resolution: Optional[str] = None,
    trash_folder: Optional[str] = None,
    extract_temp_folder: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """
    Execute a single queued action synchronously.

    Returns (message, dest_path).  dest_path is None for permanent deletes
    and skip resolutions.

    Raises:
        ConflictError            – destination exists and resolution is None.
        FileNotFoundError / PermissionError / OSError / ValueError – I/O errors.
    """
    action_type = action["action_type"]
    source_path = action["source_path"]

    # ----- Permanent delete -----
    if action_type == "delete_permanent":
        if os.path.isdir(source_path):
            shutil.rmtree(source_path)
        elif os.path.exists(source_path):
            os.remove(source_path)
        else:
            raise FileNotFoundError(f"Source not found: {source_path}")
        return f"Permanently deleted '{os.path.basename(source_path)}'", None

    # ----- Trash -----
    if action_type == "delete_trash":
        if not trash_folder:
            raise ValueError("No trash folder configured")
        # Auto mode: create .Trash folder in the same directory as the source
        if trash_folder == "__auto__":
            trash_folder = os.path.join(os.path.dirname(source_path), ".Trash")
        os.makedirs(trash_folder, exist_ok=True)
        source_name = os.path.basename(source_path)
        dest = os.path.join(trash_folder, source_name)
        if os.path.exists(dest):
            stem, ext = os.path.splitext(source_name)
            n = 1
            while os.path.exists(dest):
                dest = os.path.join(trash_folder, f"{stem} ({n}){ext}")
                n += 1
        atomic_move(source_path, dest)
        return f"Moved '{source_name}' to trash: {dest}", dest

    # ----- Unwrap folder -----
    if action_type in ("move", "copy") and action.get("unwrap_folder") and os.path.isdir(source_path):
        dest_base = action.get("destination", "")
        os.makedirs(dest_base, exist_ok=True)
        children = sorted(os.listdir(source_path))
        moved = []
        for child in children:
            child_src  = os.path.join(source_path, child)
            child_dest = os.path.join(dest_base, child)
            if os.path.exists(child_dest):
                if resolution is None:
                    raise ConflictError(child_dest, moved_count=len(moved))
                if resolution == "skip":
                    continue
                if resolution == "overwrite":
                    if os.path.isdir(child_dest):
                        shutil.rmtree(child_dest)
                    else:
                        os.remove(child_dest)
                elif resolution == "rename":
                    stem, ext = os.path.splitext(child)
                    n = 1
                    while os.path.exists(child_dest):
                        child_dest = os.path.join(dest_base, f"{stem} ({n}){ext}")
                        n += 1
            if action_type == "move":
                atomic_move(child_src, child_dest)
            else:
                atomic_copy(child_src, child_dest)
            moved.append(child)
        if action_type == "move" and action.get("delete_empty_source", True):
            try:
                os.rmdir(source_path)
            except OSError:
                # Check for .nfs* remnants before silently ignoring
                if os.path.isdir(source_path):
                    nfs = [f for f in os.listdir(source_path) if f.startswith('.nfs')]
                    if nfs:
                        verb = "Moved" if action_type == "move" else "Copied"
                        return (
                            f"{verb} {len(moved)} item(s) from '{os.path.basename(source_path)}' → {dest_base}"
                            f" ⚠ Source folder not removed: {len(nfs)} .nfs* lock file(s) left by NFS — auto-cleans when OS releases file handles",
                            dest_base,
                        )
        verb = "Moved" if action_type == "move" else "Copied"
        return f"{verb} {len(moved)} item(s) from '{os.path.basename(source_path)}' → {dest_base}", dest_base

    # ----- Move / Copy -----
    if action_type in ("move", "copy"):
        dest_info    = _get_dest_info(action)
        conflict_path = dest_info["conflict_check_path"]
        dest_folder  = dest_info["dest_folder"]
        item_name    = dest_info["item_name"]
        source_name  = dest_info["source_name"]
        dest_base    = dest_info["dest_base"]
        wrap         = dest_info["wrap"]

        os.makedirs(dest_base, exist_ok=True)

        if os.path.exists(conflict_path):
            if resolution is None:
                raise ConflictError(conflict_path)

            if resolution == "skip":
                return f"Skipped '{source_name}' (conflict)", None

            if resolution == "overwrite":
                if os.path.isdir(conflict_path):
                    shutil.rmtree(conflict_path)
                else:
                    os.remove(conflict_path)
                return _perform_transfer(action, dest_folder, item_name)

            if resolution == "rename":
                if wrap:
                    folder_name    = os.path.splitext(source_name)[0]
                    new_folder_name = folder_name
                    n = 1
                    while os.path.exists(os.path.join(dest_base, new_folder_name)):
                        new_folder_name = f"{folder_name} ({n})"
                        n += 1
                    new_dest_folder = os.path.join(dest_base, new_folder_name)
                    return _perform_transfer(action, new_dest_folder, item_name)
                else:
                    stem, ext = os.path.splitext(source_name)
                    new_name = source_name
                    n = 1
                    while os.path.exists(os.path.join(dest_base, new_name)):
                        new_name = f"{stem} ({n}){ext}"
                        n += 1
                    return _perform_transfer(action, dest_folder, new_name)

        msg, final_dest = _perform_transfer(action, dest_folder, item_name)
        # Warn if source folder remains with only .nfs* lock files after a move
        if action_type == "move" and os.path.isdir(source_path):
            nfs = [f for f in os.listdir(source_path) if f.startswith('.nfs')]
            if nfs:
                msg += (
                    f" ⚠ Source folder not removed: {len(nfs)} .nfs* lock file(s) left by NFS"
                    " — auto-cleans when OS releases file handles"
                )
        return msg, final_dest

    # ----- Extract archive -----
    if action_type == "extract":
        destination = action.get("destination", "")
        if not destination:
            raise ValueError("No destination specified for extract action")
        result = extract_archive(
            source=source_path,
            dest_folder=destination,
            strip_root=bool(action.get("strip_root")),
            rename_to=action.get("dest_name") or None,
            temp_folder=extract_temp_folder,
        )
        if not result.get("success"):
            raise OSError(result.get("error", "Extraction failed"))
        return result["message"], result["dest"]

    raise ValueError(f"Unknown action_type: {action_type}")
