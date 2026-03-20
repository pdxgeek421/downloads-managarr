import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/config/config.json"))
_config_lock = asyncio.Lock()

DEFAULT_CONFIG: dict = {
    "sources": [],
    "destinations": [],
    "trash_folder": None,
}

# Simple TTL cache — avoids re-reading config.json on every request
_config_cache: Optional[tuple] = None   # (monotonic_timestamp, config_dict)
_CONFIG_CACHE_TTL = 5.0                 # seconds


def _invalidate_config_cache() -> None:
    global _config_cache
    _config_cache = None


# ---------------------------------------------------------------------------
# Pydantic schema — validates POST /api/config payloads
# ---------------------------------------------------------------------------

class SourceConfig(BaseModel):
    label: str = ""
    path: str


class DestinationConfig(BaseModel):
    label: str = ""
    path: str
    dest_type: str = "tv"


class AppConfig(BaseModel):
    sources: List[SourceConfig] = []
    destinations: List[DestinationConfig] = []
    trash_folder: Optional[str] = None
    extract_temp_folder: Optional[str] = None
    auto_wrap: bool = True
    auto_unwrap: bool = True
    auto_season_folder: bool = True
    history_days: int = 30
    media_types: List[str] = ["tv", "movie", "music", "games"]
    block_mixed_types: bool = True
    type_icons: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Environment-variable config (sources / destinations / trash)
#
# Variables are read on every get_config() call so that changes to the
# container environment take effect on the next request without a rebuild.
#
# Naming convention (0-based, scan stops at the first missing index):
#
#   SOURCE_0_PATH=/data/completed
#   SOURCE_0_LABEL=Completed Downloads   ← optional; basename used if absent
#   SOURCE_1_PATH=/data/usenet/completed
#
#   DEST_0_PATH=/media/tv
#   DEST_0_LABEL=TV Shows               ← optional
#   DEST_0_TYPE=tv                      ← optional; defaults to "tv"
#   DEST_1_PATH=/media/movies
#   DEST_1_LABEL=Movies
#   DEST_1_TYPE=movie
#
#   TRASH_FOLDER=/data/trash
# ---------------------------------------------------------------------------

def _get_env_sources() -> list[dict]:
    """Parse SOURCE_n_PATH / SOURCE_n_LABEL env vars into source dicts."""
    sources = []
    for i in range(256):
        path = os.environ.get(f"SOURCE_{i}_PATH", "").strip()
        if not path:
            break
        label = os.environ.get(f"SOURCE_{i}_LABEL", "").strip() or Path(path).name
        sources.append({"path": path, "label": label, "env_managed": True})
    return sources


def _get_env_destinations() -> list[dict]:
    """Parse DEST_n_PATH / DEST_n_LABEL / DEST_n_TYPE env vars into dest dicts."""
    dests = []
    for i in range(256):
        path = os.environ.get(f"DEST_{i}_PATH", "").strip()
        if not path:
            break
        label     = os.environ.get(f"DEST_{i}_LABEL", "").strip() or Path(path).name
        dest_type = os.environ.get(f"DEST_{i}_TYPE",  "").strip() or "tv"
        dests.append({"path": path, "label": label, "dest_type": dest_type, "env_managed": True})
    return dests


def _get_env_trash() -> Optional[str]:
    """Return TRASH_FOLDER env var value, or None if not set."""
    val = os.environ.get("TRASH_FOLDER", "").strip()
    return val or None


# ---------------------------------------------------------------------------
# Helpers used by other modules (synchronous — safe to call from sync code)
# ---------------------------------------------------------------------------

def get_config() -> dict:
    """
    Load config from disk and inject any env-managed sources/destinations.

    Results are cached for _CONFIG_CACHE_TTL seconds to avoid per-request
    disk reads.  The cache is invalidated immediately on save_config().

    Env-managed entries:
    - Are tagged with ``env_managed: True`` so the UI can render them as read-only.
    - Are always placed before user-defined entries.
    - Are never stored in config.json (save_config strips them by path).
    - Take effect immediately when env vars change — no restart required.
    """
    global _config_cache
    now = time.monotonic()
    if _config_cache is not None and now - _config_cache[0] < _CONFIG_CACHE_TTL:
        return dict(_config_cache[1])

    if not CONFIG_PATH.exists():
        stored: dict = DEFAULT_CONFIG.copy()
    else:
        try:
            with open(CONFIG_PATH) as f:
                stored = json.load(f)
        except (json.JSONDecodeError, OSError):
            stored = DEFAULT_CONFIG.copy()

    # Merge schema defaults for any missing fields
    defaults = AppConfig().model_dump()
    config   = {**defaults, **stored}

    # --- Inject env-managed entries ---
    env_sources = _get_env_sources()
    env_dests   = _get_env_destinations()
    env_trash   = _get_env_trash()

    env_source_paths = {s["path"] for s in env_sources}
    env_dest_paths   = {d["path"] for d in env_dests}

    # User-defined entries (anything not controlled by env vars)
    user_sources = [s for s in config["sources"]      if s.get("path") not in env_source_paths]
    user_dests   = [d for d in config["destinations"] if d.get("path") not in env_dest_paths]

    config["sources"]      = env_sources + user_sources
    config["destinations"] = env_dests   + user_dests

    if env_trash:
        config["trash_folder"]     = env_trash
        config["trash_env_managed"] = True
    else:
        config.setdefault("trash_env_managed", False)

    if env_sources or env_dests or env_trash:
        logger.debug(
            "Env config injected: %d source(s), %d destination(s), trash=%s",
            len(env_sources), len(env_dests), env_trash,
        )

    _config_cache = (time.monotonic(), config)
    return dict(config)


def save_config(config: dict) -> None:
    """
    Persist config to disk.

    Strips any entries whose paths are currently controlled by env vars so
    that stored config only contains user-defined entries.  Env-managed
    entries are re-injected at read time by get_config().
    """
    env_source_paths = {s["path"] for s in _get_env_sources()}
    env_dest_paths   = {d["path"] for d in _get_env_destinations()}
    env_trash        = _get_env_trash()

    to_save = dict(config)

    # Strip env-managed paths — they live in the environment, not on disk
    to_save["sources"]      = [s for s in config.get("sources", [])      if s.get("path") not in env_source_paths]
    to_save["destinations"] = [d for d in config.get("destinations", []) if d.get("path") not in env_dest_paths]

    # If trash is env-managed, don't overwrite it with whatever the UI sent
    if env_trash:
        to_save["trash_folder"] = None

    # Remove runtime-only flags before writing
    to_save.pop("trash_env_managed", None)
    for entry in to_save["sources"] + to_save["destinations"]:
        entry.pop("env_managed", None)

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(to_save, f, indent=2)
    _invalidate_config_cache()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/config")
async def read_config():
    return get_config()


@router.post("/config")
async def write_config(config: AppConfig):
    async with _config_lock:
        save_config(config.model_dump())
    logger.info("Configuration saved")
    return {"status": "ok"}
