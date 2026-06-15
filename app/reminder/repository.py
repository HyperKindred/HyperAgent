"""CRUD operations for reminders and notifications.

Follows the existing pattern: accepts an optional SQLAlchemy Session,
or creates one automatically from SessionLocal.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.reminder.models import PendingNotification, Reminder, ReminderCreate
from app.schedule.database import SessionLocal


# ── Reminder CRUD ───────────────────────────────────────────────────────

class ReminderRepository:
    """Reminder CRUD — mirrors the pattern in MemoryRepository / ScheduleRepository."""

    def __init__(self, db: Optional[Session] = None):
        self._db = db

    def _session(self) -> Session:
        """Return the injected session, or create a new one."""
        if self._db is not None:
            return self._db
        return SessionLocal()

    # ── Create ──────────────────────────────────────────────────────

    def create(self, data: ReminderCreate) -> Reminder:
        db = self._session()
        try:
            reminder = Reminder(
                title=data.title,
                description=data.description,
                trigger_at=data.trigger_at,
                recurring=data.recurring,
                event_id=data.event_id,
                status="pending",
            )
            db.add(reminder)
            db.commit()
            db.refresh(reminder)
            return reminder
        finally:
            if self._db is None:
                db.close()

    # ── Read ────────────────────────────────────────────────────────

    def get_by_id(self, reminder_id: int) -> Optional[Reminder]:
        db = self._session()
        try:
            return db.query(Reminder).filter(Reminder.id == reminder_id).first()
        finally:
            if self._db is None:
                db.close()

    def get_by_event_id(self, event_id: int) -> Optional[Reminder]:
        """Return the pending reminder linked to a schedule event, if any."""
        db = self._session()
        try:
            return (
                db.query(Reminder)
                .filter(Reminder.event_id == event_id, Reminder.status == "pending")
                .first()
            )
        finally:
            if self._db is None:
                db.close()

    def list_pending(self) -> List[Reminder]:
        """Return all reminders with status='pending', ordered by trigger_at."""
        db = self._session()
        try:
            return (
                db.query(Reminder)
                .filter(Reminder.status == "pending")
                .order_by(Reminder.trigger_at)
                .all()
            )
        finally:
            if self._db is None:
                db.close()

    def list_all(self) -> List[Reminder]:
        """Return all reminders, newest first."""
        db = self._session()
        try:
            return (
                db.query(Reminder)
                .order_by(desc(Reminder.created_at))
                .all()
            )
        finally:
            if self._db is None:
                db.close()

    # ── Update ──────────────────────────────────────────────────────

    def mark_fired(self, reminder_id: int) -> Optional[Reminder]:
        db = self._session()
        try:
            reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
            if reminder:
                reminder.status = "fired"
                reminder.fired_at = datetime.utcnow()
                db.commit()
                db.refresh(reminder)
            return reminder
        finally:
            if self._db is None:
                db.close()

    def cancel(self, reminder_id: int) -> bool:
        db = self._session()
        try:
            reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
            if reminder:
                reminder.status = "cancelled"
                db.commit()
                return True
            return False
        finally:
            if self._db is None:
                db.close()

    # ── Delete ──────────────────────────────────────────────────────

    def delete(self, reminder_id: int) -> bool:
        db = self._session()
        try:
            reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
            if reminder:
                db.delete(reminder)
                db.commit()
                return True
            return False
        finally:
            if self._db is None:
                db.close()


# ── Notification CRUD ───────────────────────────────────────────────────

class NotificationRepository:
    """Pending notification queue — read + mark delivered."""

    def __init__(self, db: Optional[Session] = None):
        self._db = db

    def _session(self) -> Session:
        if self._db is not None:
            return self._db
        return SessionLocal()

    def enqueue(self, reminder: Reminder) -> PendingNotification:
        """Create a notification event from a fired reminder."""
        db = self._session()
        try:
            note = PendingNotification(
                reminder_id=reminder.id,
                event_type="reminder",
                title=reminder.title,
                body=reminder.description or reminder.title,
            )
            db.add(note)
            db.commit()
            db.refresh(note)
            return note
        finally:
            if self._db is None:
                db.close()

    def get_undelivered(self) -> List[PendingNotification]:
        """Return all notifications that haven't been SSE-pushed yet."""
        db = self._session()
        try:
            return (
                db.query(PendingNotification)
                .filter(PendingNotification.delivered == False)
                .order_by(PendingNotification.created_at)
                .all()
            )
        finally:
            if self._db is None:
                db.close()

    def mark_delivered(self, note_id: int) -> None:
        db = self._session()
        try:
            note = db.query(PendingNotification).filter(PendingNotification.id == note_id).first()
            if note:
                note.delivered = True
                db.commit()
        finally:
            if self._db is None:
                db.close()
