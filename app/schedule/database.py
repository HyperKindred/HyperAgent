from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Ensure data directory exists
data_dir = Path(settings.data_dir)
data_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create all tables if they don't exist yet."""
    from app.schedule.models import Event  # noqa: F401
    from app.schedule.notifier import CalendarNotification  # noqa: F401
    from app.memory.models import Memory  # noqa: F401

    Base.metadata.create_all(engine)


def get_session():
    """Yield a SQLAlchemy session (convenience for FastAPI dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
