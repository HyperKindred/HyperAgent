"""Tests for APScheduler integration — notification dedup, safety net, and job lifecycle.

These tests verify the core scheduling logic without requiring a live
APScheduler BackgroundScheduler thread.  We mock the repository constructor
so that ``fire_reminder()`` and ``_scan_and_schedule()`` use the same
in-memory SQLite session as the test.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.reminder.models import Reminder, ReminderCreate
from app.reminder.repository import ReminderRepository, NotificationRepository
from app.schedule.database import Base
from app.utils import time as ut  # unified UTC time module


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    """In-memory SQLite engine (creates a fresh database per test)."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Read-write session for test setup/assertions."""
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def patched_session(engine):
    """Return an (session, unpatch) pair where the session is patched as
    the default for ``ReminderRepository()`` and ``NotificationRepository()``.

    Usage in tests::

        session, unpatch = patched_session
        try:
            fire_reminder(...)
        finally:
            unpatch()
    """
    Session = sessionmaker(bind=engine)
    db = Session()
    original_rs = ReminderRepository._session
    original_ns = NotificationRepository._session

    def _patch_repo_session(self):
        return db

    ReminderRepository._session = _patch_repo_session
    NotificationRepository._session = _patch_repo_session

    def _unpatch():
        ReminderRepository._session = original_rs
        NotificationRepository._session = original_ns
        db.close()

    return db, _unpatch


# ── core: fire_reminder ───────────────────────────────────────────────────

class TestFireReminder:
    """Tests for ``app.reminder.scheduler.fire_reminder()``."""

    @freeze_time("2026-06-19 10:00:00")
    def test_fire_pending_reminder(self, patched_session):
        """fire_reminder should create a notification and mark as fired."""
        from app.reminder.scheduler import fire_reminder

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        reminder = repo.create(ReminderCreate(
            title="喝水提醒",
            description="该喝水了",
            trigger_at=ut.now(),
        ))

        fire_reminder(reminder.id)
        unpatch()

        # Assert via a fresh session
        fired = repo.get_by_id(reminder.id)
        assert fired is not None
        assert fired.status == "fired"
        assert fired.fired_at is not None

        notif_repo = NotificationRepository(db=session)
        undelivered = notif_repo.get_undelivered()
        matching = [n for n in undelivered if n.reminder_id == reminder.id]
        assert len(matching) == 1
        assert matching[0].title == "喝水提醒"

    @freeze_time("2026-06-19 10:00:00")
    def test_fire_idempotent(self, patched_session):
        """Calling fire_reminder twice for the same reminder should be a no-op."""
        from app.reminder.scheduler import fire_reminder

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        reminder = repo.create(ReminderCreate(
            title="不要重复",
            trigger_at=ut.now(),
        ))

        # Act: call twice
        fire_reminder(reminder.id)
        fire_reminder(reminder.id)
        unpatch()

        # Assert: only one notification
        notif_repo = NotificationRepository(db=session)
        undelivered = notif_repo.get_undelivered()
        matching = [n for n in undelivered if n.reminder_id == reminder.id]
        assert len(matching) == 1, "fire_reminder should be idempotent"

    @freeze_time("2026-06-19 10:00:00")
    def test_fire_already_fired_reminder(self, patched_session):
        """Firing an already-fired reminder should not create *any* notification."""
        from app.reminder.scheduler import fire_reminder

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        reminder = repo.create(ReminderCreate(
            title="已触发",
            trigger_at=ut.now(),
        ))
        repo.mark_fired(reminder.id)  # pre-fire via repo

        fire_reminder(reminder.id)
        unpatch()

        notif_repo = NotificationRepository(db=session)
        assert len(notif_repo.get_undelivered()) == 0

    @freeze_time("2026-06-19 10:00:00")
    def test_fire_nonexistent_reminder(self, patched_session):
        """Calling fire_reminder with a nonexistent ID should not crash."""
        from app.reminder.scheduler import fire_reminder

        _, unpatch = patched_session
        try:
            fire_reminder(99999)  # should not raise
        finally:
            unpatch()

    @freeze_time("2026-06-19 10:00:00")
    def test_recurring_reminder_rescheduled(self, patched_session):
        """Recurring reminders remain pending and fire again at the next occurrence."""
        from app.reminder.scheduler import _scan_and_schedule, fire_reminder

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        reminder = repo.create(ReminderCreate(
            title="每分钟站会",
            trigger_at=ut.now(),
            recurring="*/1 * * * *",
        ))

        try:
            fire_reminder(reminder.id)
            first_next = repo.get_by_id(reminder.id)
            assert first_next.status == "pending"
            assert first_next.trigger_at > ut.now()

            # A safety scan before the next occurrence must not duplicate it.
            with freeze_time("2026-06-19 10:00:30"):
                _scan_and_schedule()

            with freeze_time("2026-06-19 10:01:01"):
                _scan_and_schedule()
                second_next = repo.get_by_id(reminder.id)
                assert second_next.status == "pending"
                assert second_next.trigger_at > ut.now()

            notes = NotificationRepository(db=session).get_undelivered()
            assert len([note for note in notes if note.reminder_id == reminder.id]) == 2
        finally:
            unpatch()


# ── safety net: _scan_and_schedule ────────────────────────────────────────

class TestScanAndSchedule:
    """Tests for ``app.reminder.scheduler._scan_and_schedule()``."""

    @freeze_time("2026-06-19 10:00:00")
    def test_fires_past_due_reminders(self, patched_session):
        """Safety net should fire reminders past their trigger_at."""
        from app.reminder.scheduler import _scan_and_schedule

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        # Past due (5 minutes ago)
        past = repo.create(ReminderCreate(
            title="已过期",
            trigger_at=ut.now() - timedelta(minutes=5),
        ))
        # Future (still valid)
        future = repo.create(ReminderCreate(
            title="未到期",
            trigger_at=ut.now() + timedelta(hours=1),
        ))

        _scan_and_schedule()
        unpatch()

        assert repo.get_by_id(past.id).status == "fired"
        assert repo.get_by_id(future.id).status == "pending"

    @freeze_time("2026-06-19 10:00:00")
    def test_safety_net_no_reminders(self, patched_session):
        """Safety net should not crash when there are no pending reminders."""
        from app.reminder.scheduler import _scan_and_schedule

        _, unpatch = patched_session
        try:
            _scan_and_schedule()  # should not raise
        finally:
            unpatch()

    @freeze_time("2026-06-19 10:00:00")
    def test_safety_net_idempotent(self, patched_session):
        """Running the safety net twice should not duplicate notifications."""
        from app.reminder.scheduler import _scan_and_schedule

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        reminder = repo.create(ReminderCreate(
            title="不要重复",
            trigger_at=ut.now() - timedelta(minutes=1),
        ))

        _scan_and_schedule()
        _scan_and_schedule()
        unpatch()

        notif_repo = NotificationRepository(db=session)
        undelivered = notif_repo.get_undelivered()
        matching = [n for n in undelivered if n.reminder_id == reminder.id]
        assert len(matching) == 1, "Safety net should not duplicate notifications"


# ── job lifecycle ─────────────────────────────────────────────────────────

class TestScheduleReminderJob:
    """Tests for ``app.reminder.scheduler.schedule_reminder_job()``."""

    def test_recurring_job_uses_configured_timezone(self, patched_session, monkeypatch):
        from app.reminder import scheduler as scheduler_module
        from app.reminder.scheduler import start_scheduler, stop_scheduler

        session, unpatch = patched_session
        reminder = ReminderRepository(db=session).create(
            ReminderCreate(
                title="东京每日提醒",
                trigger_at=ut.now() + timedelta(minutes=1),
                recurring="0 9 * * *",
            )
        )
        monkeypatch.setattr(scheduler_module.settings, "timezone", "Asia/Tokyo")
        try:
            scheduler = start_scheduler()
            scheduler_module._schedule_recurring(reminder)
            job = scheduler.get_job(f"reminder-{reminder.id}")
            assert str(job.trigger.timezone) == "Asia/Tokyo"
        finally:
            stop_scheduler()
            unpatch()

    @freeze_time("2026-06-19 10:00:00")
    def test_schedule_job_added(self, patched_session):
        """APScheduler job store should contain the new job after scheduling."""
        from app.reminder.scheduler import schedule_reminder_job, start_scheduler, stop_scheduler

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        reminder = repo.create(ReminderCreate(
            title="未来提醒",
            trigger_at=ut.now() + timedelta(minutes=30),
        ))

        try:
            scheduler = start_scheduler()
            schedule_reminder_job(reminder)

            job = scheduler.get_job(f"reminder-{reminder.id}")
            assert job is not None, "Job should be registered in APScheduler"
            assert job.id == f"reminder-{reminder.id}"
        finally:
            stop_scheduler()
            unpatch()

    @freeze_time("2026-06-19 10:00:00")
    def test_cancel_job(self, patched_session):
        """Cancelling a job should remove it from the job store."""
        from app.reminder.scheduler import (
            cancel_reminder_job,
            schedule_reminder_job,
            start_scheduler,
            stop_scheduler,
        )

        session, unpatch = patched_session
        repo = ReminderRepository(db=session)
        reminder = repo.create(ReminderCreate(
            title="可取消",
            trigger_at=ut.now() + timedelta(hours=1),
        ))

        try:
            scheduler = start_scheduler()
            schedule_reminder_job(reminder)
            cancel_reminder_job(reminder.id)
            assert scheduler.get_job(f"reminder-{reminder.id}") is None
        finally:
            stop_scheduler()
            unpatch()

    @freeze_time("2026-06-19 10:00:00")
    def test_scheduler_lifecycle(self, patched_session):
        """start_scheduler and stop_scheduler should be idempotent."""
        from app.reminder.scheduler import start_scheduler, stop_scheduler

        _, unpatch = patched_session
        try:
            s1 = start_scheduler()
            s2 = start_scheduler()  # should return same instance
            assert s1 is s2
        finally:
            stop_scheduler()
            stop_scheduler()  # should not crash
            unpatch()
