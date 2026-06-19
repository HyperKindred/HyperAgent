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
    from app.thread.models import Thread  # noqa: F401

    Base.metadata.create_all(engine)

    # ── Migrations ────────────────────────────────────────────────
    # Add columns that were introduced after the initial schema.
    _migrate_add_column("reminders", "event_id", "INTEGER")

    # Fix any threads with null timestamps (from earlier versions)
    _migrate_fix_null_timestamps("threads")


def _migrate_add_column(table: str, column: str, col_type: str) -> None:
    """Add a column if it doesn't exist (SQLite-safe)."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        existing = {c["name"] for c in sa_inspect(engine).get_columns(table)}
    except Exception:
        return  # table may not exist yet
    if column not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
            logger.info("Migration: added column %s.%s", table, column)
        except Exception as e:
            logger.warning("Migration: failed to add column %s.%s: %s", table, column, e)


def _migrate_fix_null_timestamps(table: str) -> None:
    """Fix rows where created_at or updated_at is NULL (from earlier dev versions).

    Sets missing timestamps to the current UTC time.
    """
    import logging
    from datetime import datetime, timezone
    logger = logging.getLogger(__name__)
    try:
        existing = {c["name"] for c in sa_inspect(engine).get_columns(table)}
    except Exception:
        return
    has_created = "created_at" in existing
    has_updated = "updated_at" in existing
    if not has_created and not has_updated:
        return
    now = datetime.now(timezone.utc)
    try:
        with engine.connect() as conn:
            if has_created:
                conn.execute(
                    text(f"UPDATE {table} SET created_at = :now WHERE created_at IS NULL"),
                    {"now": now}
                )
            if has_updated:
                conn.execute(
                    text(f"UPDATE {table} SET updated_at = :now WHERE updated_at IS NULL"),
                    {"now": now}
                )
            conn.commit()
    except Exception as e:
        logger.warning("Migration: failed to fix null timestamps in %s: %s", table, e)


def get_session():
    """Yield a SQLAlchemy session (convenience for FastAPI dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
