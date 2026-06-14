"""Data-access layer for schedule events."""

from datetime import date, datetime
from contextlib import contextmanager

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.schedule.models import Event, EventCreate, EventUpdate


class ScheduleRepository:
    """Encapsulates all Event CRUD operations against SQLite."""

    def __init__(self, session: Session | None = None):
        self.session = session

    # ── session helper ─────────────────────────────────────────────

    @contextmanager
    def _session(self):
        """Provide a transactional scope.  When a session was injected (e.g.
        by a test fixture) yield it directly; otherwise create, commit on
        success, rollback on error, and always close."""
        if self.session is not None:
            yield self.session
        else:
            from app.schedule.database import SessionLocal

            db = SessionLocal()
            try:
                yield db
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    # ── CRUD ────────────────────────────────────────────────────────

    def create_event(self, data: EventCreate) -> Event:
        with self._session() as db:
            event = Event(**data.model_dump())
            db.add(event)
            db.commit()
            db.refresh(event)
            return event

    def get_event(self, event_id: int) -> Event | None:
        with self._session() as db:
            return db.query(Event).filter(Event.id == event_id).first()

    def list_events_by_date(self, dt: date) -> list[Event]:
        """Return all events that occur on *dt* (any time that day)."""
        with self._session() as db:
            start = datetime(dt.year, dt.month, dt.day)
            end = datetime(dt.year, dt.month, dt.day, 23, 59, 59)
            return (
                db.query(Event)
                .filter(Event.start_time.between(start, end))
                .order_by(Event.start_time)
                .all()
            )

    def list_events_by_date_range(self, start: date, end: date) -> list[Event]:
        with self._session() as db:
            start_dt = datetime(start.year, start.month, start.day)
            end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
            return (
                db.query(Event)
                .filter(Event.start_time.between(start_dt, end_dt))
                .order_by(Event.start_time)
                .all()
            )

    def update_event(self, event_id: int, data: EventUpdate) -> Event | None:
        with self._session() as db:
            event = db.query(Event).filter(Event.id == event_id).first()
            if event is None:
                return None
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(event, key, value)
            db.commit()
            db.refresh(event)
            return event

    def delete_event(self, event_id: int) -> bool:
        with self._session() as db:
            event = db.query(Event).filter(Event.id == event_id).first()
            if event is None:
                return False
            db.delete(event)
            db.commit()
            return True

    def search_events(self, keyword: str) -> list[Event]:
        """Search events by title or description containing *keyword*."""
        with self._session() as db:
            pattern = f"%{keyword}%"
            return (
                db.query(Event)
                .filter(
                    or_(Event.title.ilike(pattern), Event.description.ilike(pattern))
                )
                .order_by(Event.start_time)
                .all()
            )

    def get_upcoming_events(self, limit: int = 10) -> list[Event]:
        """Get the next *limit* events starting from now."""
        with self._session() as db:
            now = datetime.now()
            return (
                db.query(Event)
                .filter(Event.start_time >= now)
                .order_by(Event.start_time)
                .limit(limit)
                .all()
            )
