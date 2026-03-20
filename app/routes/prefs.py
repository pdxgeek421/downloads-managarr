"""Per-user UI preferences (theme, accent, panel width).

Stored in /config/user_prefs.json keyed by username.
When auth is disabled the key "default" is used so prefs still persist
server-side and roam across any browser accessing the instance.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Request

from app.routes.auth import COOKIE_NAME, get_session_user

router = APIRouter()

PREFS_PATH = Path(os.environ.get("PREFS_PATH", "/config/user_prefs.json"))

_lock = asyncio.Lock()

DEFAULT_PREFS: dict = {
    "theme": "dark",
    "accent": "purple",
    "custom_accent": None,
    "custom_theme": None,   # {"bg": "#...", "surface": "#...", "text": "#..."}
    "panel_width": None,
    "font_size": 14,
}

_ALLOWED_KEYS = set(DEFAULT_PREFS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read() -> dict:
    if not PREFS_PATH.exists():
        return {}
    try:
        with open(PREFS_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PREFS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _username(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    return get_session_user(token) or "default"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/prefs")
async def get_prefs(request: Request):
    username = _username(request)
    async with _lock:
        all_prefs = _read()
    user_prefs = all_prefs.get(username, {})
    return {**DEFAULT_PREFS, **user_prefs}


@router.put("/prefs")
async def save_prefs(request: Request, body: dict = Body(...)):
    username = _username(request)
    # Only persist known keys to prevent storing arbitrary data
    sanitised = {k: v for k, v in body.items() if k in _ALLOWED_KEYS}
    async with _lock:
        all_prefs = _read()
        all_prefs[username] = sanitised
        _write(all_prefs)
    return {"status": "ok"}
