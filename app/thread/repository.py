"""CRUD operations for thread metadata + checkpoints cleanup.

Follows the existing dual-Session pattern (MemoryRepository / ScheduleRepository).
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.schedule.database import SessionLocal
from app.thread.models import Thread, ThreadCreate

logger = logging.getLogger(__name__)


class ThreadRepository:
    """Thread metadata CRUD — mirrors pattern in MemoryRepository / ScheduleRepository."""

    def __init__(self, db: Optional[Session] = None):
        self._db = db

    def _session(self) -> Session:
        if self._db is not None:
            return self._db
        return SessionLocal()

    # ── Read ────────────────────────────────────────────────────────

    def get_all(self) -> List[Thread]:
        """Return all threads ordered by updated_at descending."""
        db = self._session()
        try:
            return db.query(Thread).order_by(desc(Thread.updated_at)).all()
        finally:
            if self._db is None:
                db.close()

    def get_by_id(self, thread_id: str) -> Optional[Thread]:
        db = self._session()
        try:
            return db.query(Thread).filter(Thread.id == thread_id).first()
        finally:
            if self._db is None:
                db.close()

    # ── Create ──────────────────────────────────────────────────────

    def create(self, data: ThreadCreate) -> Thread:
        db = self._session()
        try:
            thread = Thread(
                id=data.thread_id,
                title=data.title,
            )
            db.add(thread)
            db.commit()
            db.refresh(thread)
            logger.info("Thread created: %s (%s)", thread.id, thread.title)
            return thread
        finally:
            if self._db is None:
                db.close()

    # ── Update ──────────────────────────────────────────────────────

    def update_title(self, thread_id: str, title: str) -> Optional[Thread]:
        db = self._session()
        try:
            thread = db.query(Thread).filter(Thread.id == thread_id).first()
            if thread:
                thread.title = title
                db.commit()
                db.refresh(thread)
            return thread
        finally:
            if self._db is None:
                db.close()

    def touch(self, thread_id: str) -> None:
        """Update the updated_at timestamp (called after each message)."""
        db = self._session()
        try:
            thread = db.query(Thread).filter(Thread.id == thread_id).first()
            if thread:
                thread.message_count = (thread.message_count or 0) + 1
                db.commit()
        finally:
            if self._db is None:
                db.close()

    def get_or_create(self, thread_id: str, title: str = "新对话") -> Thread:
        """Return an existing thread or create a new one.

        Called when a message is sent to a thread_id that doesn't have
        metadata yet (e.g. the first message in a brand-new conversation).
        """
        thread = self.get_by_id(thread_id)
        if thread:
            return thread
        return self.create(ThreadCreate(thread_id=thread_id, title=title))

    # ── Delete ──────────────────────────────────────────────────────

    def delete(self, thread_id: str) -> bool:
        """Delete thread metadata + checkpoints for this thread.

        Returns True if the metadata was deleted (checkpoints may not exist).
        """
        db = self._session()
        try:
            thread = db.query(Thread).filter(Thread.id == thread_id).first()
            if not thread:
                return False
            db.delete(thread)
            db.commit()

            # Also delete checkpoints for this thread
            self._delete_checkpoints(thread_id)

            logger.info("Thread deleted: %s", thread_id)
            return True
        finally:
            if self._db is None:
                db.close()

    @staticmethod
    def _delete_checkpoints(thread_id: str) -> None:
        """Remove checkpoint rows for *thread_id* from checkpoints.db."""
        db_path: Path = settings.data_dir / "checkpoints.db"
        if not db_path.exists():
            return
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            # LangGraph schema varies by version. Only delete tables and columns
            # that are actually present so one absent optional table cannot roll
            # back deletion from the primary checkpoints table.
            for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                if table not in existing_tables:
                    continue
                columns = {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                }
                if "thread_id" in columns:
                    conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
            conn.commit()
            logger.info("Checkpoints cleaned for thread: %s", thread_id)
        except Exception as e:
            logger.warning("Failed to clean checkpoints for %s: %s", thread_id, e)
        finally:
            if conn is not None:
                conn.close()
