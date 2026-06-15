from pathlib import Path

from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Ensure data directory exists
data_dir = Path(settings.data_dir)
data_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create all tables if they don't exist yet + run migrations."""
    from app.schedule.models import Event  # noqa: F401
    from app.schedule.notifier import CalendarNotification  # noqa: F401
    from app.memory.models import Memory  # noqa: F401
    from app.reminder.models import Reminder, PendingNotification  # noqa: F401

    Base.metadata.create_all(engine)

    # ── Migrations ────────────────────────────────────────────────
    # Add columns that were introduced after the initial schema.
    _migrate_add_column("reminders", "event_id", "INTEGER")


def _migrate_add_column(table: str, column: str, col_type: str) -> None:
    """Add a column if it doesn't exist (SQLite-safe)."""
    try:
        existing = {c["name"] for c in sa_inspect(engine).get_columns(table)}
    except Exception:
        return  # table may not exist yet
    if column not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
        except Exception:
            pass


def get_session():
    """Yield a SQLAlchemy session (convenience for FastAPI dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
