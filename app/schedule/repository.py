"""Data-access layer for schedule events."""

from datetime import date, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.schedule.models import Event, EventCreate, EventUpdate


class ScheduleRepository:
    """Encapsulates all Event CRUD operations against SQLite."""

    def __init__(self, session: Session | None = None):
        self.session = session

    # ── helpers ────────────────────────────────────────────────────

    def _s(self) -> Session:
        if self.session is not None:
            return self.session
        from app.schedule.database import SessionLocal

        return SessionLocal()

    # ── CRUD ────────────────────────────────────────────────────────

    def create_event(self, data: EventCreate) -> Event:
        db = self._s()
        event = Event(**data.model_dump())
        db.add(event)
        db.commit()
        db.refresh(event)
        if self.session is None:
            db.close()
        return event

    def get_event(self, event_id: int) -> Event | None:
        db = self._s()
        event = db.query(Event).filter(Event.id == event_id).first()
        if self.session is None:
            db.close()
        return event

    def list_events_by_date(self, dt: date) -> list[Event]:
        """Return all events that occur on *dt* (any time that day)."""
        db = self._s()
        start = datetime(dt.year, dt.month, dt.day)
        end = datetime(dt.year, dt.month, dt.day, 23, 59, 59)
        events = (
            db.query(Event)
            .filter(Event.start_time.between(start, end))
            .order_by(Event.start_time)
            .all()
        )
        if self.session is None:
            db.close()
        return events

    def list_events_by_date_range(self, start: date, end: date) -> list[Event]:
        db = self._s()
        start_dt = datetime(start.year, start.month, start.day)
        end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
        events = (
            db.query(Event)
            .filter(Event.start_time.between(start_dt, end_dt))
            .order_by(Event.start_time)
            .all()
        )
        if self.session is None:
            db.close()
        return events

    def update_event(self, event_id: int, data: EventUpdate) -> Event | None:
        db = self._s()
        event = db.query(Event).filter(Event.id == event_id).first()
        if event is None:
            if self.session is None:
                db.close()
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(event, key, value)
        db.commit()
        db.refresh(event)
        if self.session is None:
            db.close()
        return event

    def delete_event(self, event_id: int) -> bool:
        db = self._s()
        event = db.query(Event).filter(Event.id == event_id).first()
        if event is None:
            if self.session is None:
                db.close()
            return False
        db.delete(event)
        db.commit()
        if self.session is None:
            db.close()
        return True

    def search_events(self, keyword: str) -> list[Event]:
        """Search events by title or description containing *keyword*."""
        db = self._s()
        pattern = f"%{keyword}%"
        events = (
            db.query(Event)
            .filter(
                or_(Event.title.ilike(pattern), Event.description.ilike(pattern))
            )
            .order_by(Event.start_time)
            .all()
        )
        if self.session is None:
            db.close()
        return events

    def get_upcoming_events(self, limit: int = 10) -> list[Event]:
        """Get the next *limit* events starting from now."""
        db = self._s()
        now = datetime.now()
        events = (
            db.query(Event)
            .filter(Event.start_time >= now)
            .order_by(Event.start_time)
            .limit(limit)
            .all()
        )
        if self.session is None:
            db.close()
        return events
