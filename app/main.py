"""FastAPI application entry point."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, memory as memory_api, reminder as reminder_api, schedule
from app.api import settings as settings_api
from app.api import thread as thread_api
from app.schedule.database import init_db

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
APP_VERSION = "0.2.1"


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
    from app.agent.graph import close_checkpointer

    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        close_checkpointer()


app = FastAPI(
    title="HyperAgent API",
    description="Personal AI assistant backend",
    version=APP_VERSION,
    lifespan=lifespan,
)

# Allow the Vite development server to call the API.
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

# ── API routers ──────────────────────────────────────────────────────
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])
app.include_router(reminder_api.router, prefix="/api", tags=["reminder"])
app.include_router(thread_api.router, prefix="/api", tags=["thread"])
app.include_router(settings_api.router, prefix="/api")
app.include_router(memory_api.router, prefix="/api")


# ── Health check ──────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Electron and monitoring."""
    return JSONResponse({"status": "ok", "version": APP_VERSION})


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
