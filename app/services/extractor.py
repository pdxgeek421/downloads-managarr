"""
Archive detection and extraction utilities.

Supported for extraction (stdlib only):
  zip, tar, tar.gz / tgz, tar.bz2 / tbz2, tar.xz / txz,
  standalone .gz, standalone .bz2

Detected only (no stdlib extractor):
  rar, 7z
"""

import bz2
import gzip
import logging
import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".bz2", ".rar", ".7z"}
ARCHIVE_MULTI_EXTS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz")

EXTRACTABLE_EXTENSIONS = {".zip", ".tar", ".gz", ".bz2"}
EXTRACTABLE_MULTI_EXTS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nl(path: str) -> str:
    """Lowercase filename only."""
    return Path(path).name.lower()


def _archive_stem(p: Path) -> str:
    """Strip archive extension(s) to get a base name."""
    name = p.name
    nl = name.lower()
    for ext in EXTRACTABLE_MULTI_EXTS + ARCHIVE_MULTI_EXTS:
        if nl.endswith(ext):
            return name[: -len(ext)]
    return p.stem


def _detect_format(path: str) -> str:
    nl = _nl(path)
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if nl.endswith(ext):
            return ext[1:]
    fmt_map = {".tgz": "tar.gz", ".tbz2": "tar.bz2", ".txz": "tar.xz"}
    for short, full in fmt_map.items():
        if nl.endswith(short):
            return full
    suffix = Path(path).suffix.lower()
    return suffix.lstrip(".") if suffix else "unknown"


# ---------------------------------------------------------------------------
# Public detection helpers
# ---------------------------------------------------------------------------

def is_archive(path: str) -> bool:
    """Return True if the file looks like a known archive format."""
    nl = _nl(path)
    for ext in ARCHIVE_MULTI_EXTS:
        if nl.endswith(ext):
            return True
    return Path(path).suffix.lower() in ARCHIVE_EXTENSIONS


def can_extract(path: str) -> bool:
    """Return True if we have stdlib support to extract this archive."""
    nl = _nl(path)
    for ext in EXTRACTABLE_MULTI_EXTS:
        if nl.endswith(ext):
            return True
    return Path(path).suffix.lower() in EXTRACTABLE_EXTENSIONS


# ---------------------------------------------------------------------------
# Archive info
# ---------------------------------------------------------------------------

def get_archive_info(path: str) -> dict:
    """
    Return metadata about an archive without extracting it.

    Keys:
      is_archive, can_extract, format,
      file_count, uncompressed_size,
      top_level_names, has_single_root,
      error (optional)
    """
    if not os.path.exists(path):
        return {"is_archive": False, "can_extract": False, "error": "File not found"}

    p = Path(path)
    nl = p.name.lower()
    result: dict = {
        "is_archive":       is_archive(path),
        "can_extract":      can_extract(path),
        "format":           _detect_format(path),
        "file_count":       0,
        "uncompressed_size": 0,
        "top_level_names":  [],
        "has_single_root":  False,
    }

    if not result["is_archive"]:
        return result

    try:
        # ZIP
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                members = zf.infolist()
                result["file_count"] = sum(1 for m in members if not m.filename.endswith("/"))
                result["uncompressed_size"] = sum(m.file_size for m in members)
                top = {m.filename.split("/")[0] for m in members if m.filename}
                result["top_level_names"] = sorted(top)
                result["has_single_root"] = len(top) == 1
            return result

        # TAR family
        if any(nl.endswith(e) for e in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            try:
                with tarfile.open(path, "r:*") as tf:
                    members = tf.getmembers()
                    result["file_count"] = sum(1 for m in members if m.isfile())
                    result["uncompressed_size"] = sum(m.size for m in members if m.isfile())
                    top = {m.name.split("/")[0] for m in members if m.name and m.name != "."}
                    result["top_level_names"] = sorted(top)
                    result["has_single_root"] = len(top) == 1
                return result
            except tarfile.TarError:
                pass

        # Standalone .gz (not tar.gz)
        if nl.endswith(".gz") and not nl.endswith(".tar.gz"):
            result["file_count"] = 1
            result["uncompressed_size"] = os.path.getsize(path) * 3  # rough estimate
            result["top_level_names"] = [p.stem]
            result["has_single_root"] = True
            return result

        # Standalone .bz2 (not tar.bz2)
        if nl.endswith(".bz2") and not nl.endswith(".tar.bz2"):
            result["file_count"] = 1
            result["uncompressed_size"] = os.path.getsize(path) * 4  # rough estimate
            result["top_level_names"] = [p.stem]
            result["has_single_root"] = True
            return result

    except Exception as e:
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Free space
# ---------------------------------------------------------------------------

def get_free_space(path: str) -> Optional[int]:
    """Return free bytes available at *path* (or its nearest existing ancestor)."""
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(str(p)).free
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_archive(
    source: str,
    dest_folder: str,
    strip_root: bool = False,
    rename_to: Optional[str] = None,
    temp_folder: Optional[str] = None,
) -> dict:
    """
    Extract *source* archive into *dest_folder*.

    If *temp_folder* is provided, extraction is staged there first; the
    finished result is then moved into *dest_folder*.  This protects the
    destination from partial writes if the process is interrupted.

    Args:
        source:       Path to the archive file.
        dest_folder:  Final destination directory.
        strip_root:   If the archive has a single top-level folder, place its
                      *contents* directly into dest_folder/<output_name>
                      instead of nesting them one level deeper.
        rename_to:    Override the output folder/file name (default: archive stem).
        temp_folder:  Staging directory for extraction (optional).

    Returns dict with keys: success, dest, file_count, message  (or error).
    """
    p = Path(source)
    nl = p.name.lower()

    stage_base = Path(temp_folder) if temp_folder else Path(dest_folder)
    os.makedirs(str(stage_base), exist_ok=True)
    os.makedirs(dest_folder, exist_ok=True)

    info = get_archive_info(source)
    if not info.get("can_extract"):
        return {"success": False, "error": f"Cannot extract format: {info.get('format', '?')}"}

    has_single = info.get("has_single_root", False)
    top_names  = info.get("top_level_names", [])

    # Determine output name
    if rename_to:
        output_name = rename_to
    elif strip_root and has_single and top_names:
        output_name = top_names[0]
    else:
        output_name = _archive_stem(p)

    tmp_dir = str(stage_base / (output_name + ".managarr.extract.tmp"))
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)

    file_count = 0
    try:
        # ── ZIP ──────────────────────────────────────────────────────────────
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(source, "r") as zf:
                # Basic zip-slip guard
                for member in zf.infolist():
                    target = os.path.normpath(os.path.join(tmp_dir, member.filename))
                    if not target.startswith(os.path.normpath(tmp_dir)):
                        raise ValueError(f"Zip slip blocked: {member.filename}")
                zf.extractall(tmp_dir)
                file_count = sum(1 for m in zf.infolist() if not m.filename.endswith("/"))

        # ── TAR family ───────────────────────────────────────────────────────
        elif any(nl.endswith(e) for e in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            with tarfile.open(source, "r:*") as tf:
                members = tf.getmembers()
                file_count = sum(1 for m in members if m.isfile())
                # Guard against absolute paths and path traversal
                safe = [m for m in members if not os.path.isabs(m.name) and ".." not in m.name]
                tf.extractall(tmp_dir, members=safe)

        # ── Standalone .gz ───────────────────────────────────────────────────
        elif nl.endswith(".gz"):
            out_path = os.path.join(tmp_dir, p.stem)
            with gzip.open(source, "rb") as f_in, open(out_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            file_count = 1

        # ── Standalone .bz2 ──────────────────────────────────────────────────
        elif nl.endswith(".bz2"):
            out_path = os.path.join(tmp_dir, p.stem)
            with bz2.open(source, "rb") as f_in, open(out_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            file_count = 1

        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"success": False, "error": f"Unsupported format: {p.suffix}"}

        # ── Move result to dest_folder ────────────────────────────────────────
        extracted_items = os.listdir(tmp_dir)
        final_path = os.path.join(dest_folder, output_name)

        if strip_root and has_single and len(extracted_items) == 1:
            # Archive had one root dir → strip it, use output_name as the top level
            inner = os.path.join(tmp_dir, extracted_items[0])
            _replace_path(final_path)
            shutil.move(inner, final_path)
            shutil.rmtree(tmp_dir, ignore_errors=True)
        elif len(extracted_items) == 1:
            # Single item at root (no strip_root) — rename it to output_name
            inner = os.path.join(tmp_dir, extracted_items[0])
            _replace_path(final_path)
            shutil.move(inner, final_path)
            shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            # Multiple root items — wrap them in output_name folder
            _replace_path(final_path)
            shutil.move(tmp_dir, final_path)

        return {
            "success":     True,
            "dest":        final_path,
            "file_count":  file_count,
            "message":     f"Extracted {file_count} file(s) → {final_path}",
        }

    except Exception as exc:
        logger.error("Extraction failed for %s: %s", source, exc)
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"success": False, "error": str(exc)}


def _replace_path(path: str) -> None:
    """Remove *path* if it already exists (prepares for an incoming move)."""
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)
