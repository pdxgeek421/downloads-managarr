import json
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.db import DB_PATH, close_db, get_db, init_db
from app.routes import auth as auth_routes
from app.routes import config, executor, files, history, prefs, queue, trash
from app.routes.auth import AUTH_REQUIRED, COOKIE_NAME, check_request

QUEUE_PATH   = Path(os.environ.get("QUEUE_PATH",   "/config/queue.json"))
CONFIG_PATH  = Path(os.environ.get("CONFIG_PATH",  "/config/config.json"))
HISTORY_PATH = Path(os.environ.get("HISTORY_PATH", str(QUEUE_PATH.parent / "history.json")))
LOG_PATH     = Path(os.environ.get("LOG_PATH",     str(QUEUE_PATH.parent / "app.log")))

STATIC_DIR = Path(__file__).parent / "static"


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(
            str(LOG_PATH),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)
    # Prevent uvicorn from double-logging HTTP access lines
    logging.getLogger("uvicorn.access").propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logger = logging.getLogger(__name__)

    # Ensure config file exists on first boot
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w") as f:
            json.dump({"sources": [], "destinations": [], "trash_folder": None}, f, indent=2)

    # Initialise SQLite — auto-migrates from queue.json / history.json if present
    await init_db(queue_json=QUEUE_PATH, history_json=HISTORY_PATH)

    logger.info(
        "Downloads-Managarr started | db=%s | config=%s | log=%s",
        DB_PATH, CONFIG_PATH, LOG_PATH,
    )
    yield
    await close_db()
    logger.info("Downloads-Managarr shutting down.")


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests to /api/* (except /api/auth/*)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Only guard API routes; let auth endpoints and the UI through freely
        if AUTH_REQUIRED and path.startswith("/api/") and not path.startswith("/api/auth"):
            token = request.cookies.get(COOKIE_NAME)
            if not check_request(token):
                return JSONResponse(
                    {"status": "error", "message": "Unauthorized"},
                    status_code=401,
                )
        return await call_next(request)


app = FastAPI(title="Downloads-Managarr", lifespan=lifespan)

app.add_middleware(AuthMiddleware)

app.include_router(auth_routes.router, prefix="/api")
app.include_router(prefs.router,       prefix="/api")
app.include_router(files.router,       prefix="/api")
app.include_router(queue.router,       prefix="/api")
app.include_router(history.router,     prefix="/api")
app.include_router(executor.router,    prefix="/api")
app.include_router(trash.router,       prefix="/api")
app.include_router(config.router,      prefix="/api")


@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    try:
        db = await get_db()
        await db.execute("SELECT 1")
    except Exception as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=503)
    return {"status": "ok"}
