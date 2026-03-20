"""
Simple session-based authentication.

Auth is enabled only when both DL_MANAGARR_ADMIN_USERNAME and DL_MANAGARR_ADMIN_PASSWORD
environment variables are set.  If neither is set the app behaves exactly as before —
no login screen, no cookies.
"""

import os
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Body, Cookie, Response

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration (read once at startup)
# ---------------------------------------------------------------------------

ADMIN_USERNAME: str = os.environ.get("DL_MANAGARR_ADMIN_USERNAME", "")
ADMIN_PASSWORD: str = os.environ.get("DL_MANAGARR_ADMIN_PASSWORD", "")
AUTH_REQUIRED: bool = bool(ADMIN_USERNAME and ADMIN_PASSWORD)

COOKIE_NAME = "managarr_session"
SESSION_TTL_REMEMBER = 60 * 60 * 24 * 30   # 30 days  — "keep me logged in"
SESSION_TTL_SESSION  = 60 * 60 * 24        # 24 hours — browser-session cookie

# In-memory session store: token → {"username": str, "expiry": float}
_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prune_sessions() -> None:
    """Remove all expired sessions from the in-memory store."""
    now = time.time()
    expired = [t for t, s in _sessions.items() if now > s["expiry"]]
    for t in expired:
        _sessions.pop(t, None)


def get_session_user(token: Optional[str]) -> Optional[str]:
    """Return the username for a valid session token, or None if invalid/expired."""
    if not token:
        return None
    session = _sessions.get(token)
    if session is None or time.time() > session["expiry"]:
        _sessions.pop(token, None)
        return None
    return session["username"]


def is_authenticated(token: Optional[str]) -> bool:
    """Return True if auth is disabled or the session token is valid."""
    if not AUTH_REQUIRED:
        return True
    return get_session_user(token) is not None


def check_request(token: Optional[str]) -> bool:
    """Convenience wrapper used by the middleware."""
    return is_authenticated(token)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/auth/status")
async def auth_status(managarr_session: Optional[str] = Cookie(default=None)):
    """Called on page load to decide whether to show the login screen."""
    return {
        "required": AUTH_REQUIRED,
        "authenticated": is_authenticated(managarr_session),
    }


@router.post("/auth/login")
async def login(
    response: Response,
    body: dict = Body(...),
):
    if not AUTH_REQUIRED:
        return {"status": "ok"}

    username = body.get("username", "")
    password = body.get("password", "")

    # Timing-safe comparison to prevent user enumeration via timing
    user_ok = secrets.compare_digest(username, ADMIN_USERNAME)
    pass_ok = secrets.compare_digest(password, ADMIN_PASSWORD)

    if not (user_ok and pass_ok):
        return {"status": "error", "message": "Invalid username or password"}

    # Prune stale sessions on each successful login to bound memory growth
    _prune_sessions()

    remember = bool(body.get("remember", False))
    ttl = SESSION_TTL_REMEMBER if remember else SESSION_TTL_SESSION

    token = secrets.token_hex(32)
    _sessions[token] = {"username": ADMIN_USERNAME, "expiry": time.time() + ttl}

    cookie_kwargs: dict = dict(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        # secure=True  ← enable when serving over HTTPS behind a reverse proxy
    )
    if remember:
        # Persistent cookie — survives browser restarts for 30 days
        cookie_kwargs["max_age"] = ttl
    # No max_age when not remembering → browser-session cookie (expires on close)

    response.set_cookie(**cookie_kwargs)
    return {"status": "ok"}


@router.post("/auth/logout")
async def logout(
    response: Response,
    managarr_session: Optional[str] = Cookie(default=None),
):
    if managarr_session:
        _sessions.pop(managarr_session, None)
    response.delete_cookie(COOKIE_NAME)
    return {"status": "ok"}
