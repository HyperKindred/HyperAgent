"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, reminder as reminder_api, schedule
from app.api import thread as thread_api
from app.schedule.database import init_db

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Scope, Receive, Send

from app.api import chat, reminder as reminder_api, schedule
from app.api import thread as thread_api
from app.schedule.database import init_db

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


# ── Diagnostic ASGI middleware: catches any exception at the ASGI level ──
class _CatchAllMiddleware:
    """Log ALL unhandled exceptions to a debug file before they crash."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        try:
            await self.app(scope, receive, send)
        except BaseException as exc:
            import traceback
            tb = traceback.format_exc()
            log_dir = os.environ.get("APPDATA", os.getcwd())
            log_path = os.path.join(log_dir, "HyperAgent", "_asgi_crash.log")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w") as f:
                f.write(f"ASGI caught: {type(exc).__name__}: {exc}\n{tb}\n")
            raise  # re-raise so the server still handles it


def _find_frontend_dist() -> Path | None:
    """Locate the frontend ``dist/`` directory.

    Development mode (``uv run``): ``../frontend/dist`` from ``app/main.py``.
    Packaged (PyInstaller + Electron): ``backend/dist`` next to the exe.
    """
    # 1 — Standard dev path (uv run)
    if FRONTEND_DIST.is_dir():
        return FRONTEND_DIST

    # 2 — Packaged: dist/ sits next to the backend executable
    #     (but CWD may have been changed by backend_launcher.py's .env search)
    candidates = [
        Path.cwd() / "dist",
        Path.cwd().parent / "dist",
    ]
    # 3 — Directly relative to the exe itself (most reliable in packaged mode)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.insert(0, exe_dir / "dist")

    for path in candidates:
        if path.is_dir() and (path / "index.html").is_file():
            return path

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and start scheduler on startup."""
    init_db()
    from app.reminder.scheduler import start_scheduler, stop_scheduler
    scheduler = start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="HyperAgent API",
    description="Personal AI assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow Vue dev server (localhost:5173) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "http://localhost:5175", "http://127.0.0.1:5175",
        "http://localhost:5176", "http://127.0.0.1:5176",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Wrap the ASGI app in our catch-all ──────────────────────────────
app.add_middleware(_CatchAllMiddleware)

# ── API routers ──────────────────────────────────────────────────────
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])
app.include_router(reminder_api.router, prefix="/api", tags=["reminder"])
app.include_router(thread_api.router, prefix="/api", tags=["thread"])


# ── Health check ──────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Electron and monitoring."""
    return JSONResponse({"status": "ok", "version": "0.1.0", "build": "20260619-2036"})


@app.get("/api/health/debug")
async def health_debug():
    """Debug endpoint — shows the data paths the backend is using."""
    import os

    from app.config import settings
    from app.schedule.database import SessionLocal, engine

    # Count records in the active database
    try:
        db = SessionLocal()
        from app.memory.models import Memory
        from app.reminder.models import Reminder
        from app.schedule.models import Event

        memory_count = db.query(Memory).count()
        event_count = db.query(Event).count()
        reminder_count = db.query(Reminder).count()
        db.close()
    except Exception as e:
        memory_count = event_count = reminder_count = str(e)

    return JSONResponse({
        "data_dir": str(settings.data_dir),
        "db_url": str(engine.url),
        "HYPERAGENT_DATA_DIR": os.environ.get("HYPERAGENT_DATA_DIR", "(not set)"),
        "CWD": os.getcwd(),
        "memory_count": memory_count,
        "event_count": event_count,
        "reminder_count": reminder_count,
    })


# ── Static frontend serving (production mode) ─────────────────────────
_frontend_dist = _find_frontend_dist()
if _frontend_dist is not None:
    # Serve built assets (JS, CSS, images, etc.)
    assets_dir = _frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the Vue SPA — fall back to index.html for client-side routing."""
        # If the request matches a static file (like favicon.ico), serve it
        file_path = _frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        # Otherwise return index.html for Vue Router to handle
        index_path = _frontend_dist / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)

        return {"message": "Frontend not built. Run: cd frontend && npm run build"}
