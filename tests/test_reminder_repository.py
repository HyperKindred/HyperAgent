"""Tests for ReminderRepository — CRUD + status transitions."""

from datetime import datetime, timedelta

import pytest

from app.reminder.models import ReminderCreate
from app.reminder.repository import ReminderRepository, NotificationRepository


class TestCreateReminder:
    def test_create_basic(self, session):
        repo = ReminderRepository(db=session)
        data = ReminderCreate(
            title="喝水提醒",
            description="记得喝水",
            trigger_at=datetime.utcnow() + timedelta(minutes=5),
        )
        reminder = repo.create(data)
        assert reminder.id is not None
        assert reminder.title == "喝水提醒"
        assert reminder.status == "pending"
        assert reminder.fired_at is None

    def test_create_with_recurring(self, session):
        repo = ReminderRepository(db=session)
        data = ReminderCreate(
            title="站会",
            trigger_at=datetime.utcnow() + timedelta(hours=1),
            recurring="0 9 * * 1-5",
        )
        reminder = repo.create(data)
        assert reminder.recurring == "0 9 * * 1-5"
        assert reminder.status == "pending"

    def test_create_defaults(self, session):
        repo = ReminderRepository(db=session)
        data = ReminderCreate(
            title="测试",
            trigger_at=datetime.utcnow() + timedelta(minutes=10),
        )
        reminder = repo.create(data)
        assert reminder.description == ""
        assert reminder.recurring is None


class TestGetReminder:
    def test_get_by_id(self, session):
        repo = ReminderRepository(db=session)
        data = ReminderCreate(title="测试", trigger_at=datetime.utcnow() + timedelta(minutes=5))
        created = repo.create(data)
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.title == "测试"

    def test_get_nonexistent(self, session):
        repo = ReminderRepository(db=session)
        assert repo.get_by_id(99999) is None


class TestListPending:
    def test_list_pending_reminders(self, session):
        repo = ReminderRepository(db=session)
        now = datetime.utcnow()
        r1 = repo.create(ReminderCreate(title="A", trigger_at=now + timedelta(minutes=10)))
        r2 = repo.create(ReminderCreate(title="B", trigger_at=now + timedelta(minutes=5)))
        repo.mark_fired(r1.id)
        pending = repo.list_pending()
        assert len(pending) == 1
        assert pending[0].id == r2.id

    def test_list_pending_empty(self, session):
        repo = ReminderRepository(db=session)
        assert repo.list_pending() == []


class TestMarkFired:
    def test_mark_fired(self, session):
        repo = ReminderRepository(db=session)
        data = ReminderCreate(title="测试", trigger_at=datetime.utcnow() - timedelta(minutes=1))
        reminder = repo.create(data)
        fired = repo.mark_fired(reminder.id)
        assert fired.status == "fired"
        assert fired.fired_at is not None

        # Should no longer appear in pending
        pending = repo.list_pending()
        assert len(pending) == 0

    def test_mark_fired_nonexistent(self, session):
        repo = ReminderRepository(db=session)
        result = repo.mark_fired(99999)
        assert result is None


class TestCancelReminder:
    def test_cancel(self, session):
        repo = ReminderRepository(db=session)
        data = ReminderCreate(title="测试", trigger_at=datetime.utcnow() + timedelta(hours=1))
        reminder = repo.create(data)
        success = repo.cancel(reminder.id)
        assert success is True
        fetched = repo.get_by_id(reminder.id)
        assert fetched.status == "cancelled"

    def test_cancel_nonexistent(self, session):
        repo = ReminderRepository(db=session)
        assert repo.cancel(99999) is False


class TestDeleteReminder:
    def test_delete(self, session):
        repo = ReminderRepository(db=session)
        data = ReminderCreate(title="测试", trigger_at=datetime.utcnow() + timedelta(hours=1))
        reminder = repo.create(data)
        success = repo.delete(reminder.id)
        assert success is True
        assert repo.get_by_id(reminder.id) is None

    def test_delete_cleans_up_pending_notifications(self, session):
        """Deleting a reminder should also remove its undelivered PendingNotifications."""
        repo = ReminderRepository(db=session)
        notif_repo = NotificationRepository(db=session)

        data = ReminderCreate(title="测试", trigger_at=datetime.utcnow() + timedelta(hours=1))
        reminder = repo.create(data)

        # Enqueue a notification (simulating fire_reminder)
        note = notif_repo.enqueue(reminder)
        assert note.delivered is False

        # Delete the reminder — notification should be cleaned up
        repo.delete(reminder.id)

        undelivered = notif_repo.get_undelivered()
        assert all(n.id != note.id for n in undelivered), "PendingNotification should be removed on reminder delete"

    def test_delete_nonexistent(self, session):
        repo = ReminderRepository(db=session)
        assert repo.delete(99999) is False


class TestNotifications:
    def test_enqueue_notification(self, session):
        repo = ReminderRepository(db=session)
        notif_repo = NotificationRepository(db=session)

        data = ReminderCreate(title="测试", trigger_at=datetime.utcnow() + timedelta(minutes=5))
        reminder = repo.create(data)
        notification = notif_repo.enqueue(reminder)

        assert notification.reminder_id == reminder.id
        assert notification.event_type == "reminder"
        assert notification.delivered is False

    def test_get_undelivered(self, session):
        notif_repo = NotificationRepository(db=session)
        repo = ReminderRepository(db=session)

        reminder = repo.create(ReminderCreate(
            title="测试", trigger_at=datetime.utcnow() + timedelta(minutes=5)
        ))
        notif_repo.enqueue(reminder)

        undelivered = notif_repo.get_undelivered()
        assert len(undelivered) >= 1

    def test_mark_delivered(self, session):
        notif_repo = NotificationRepository(db=session)
        repo = ReminderRepository(db=session)

        reminder = repo.create(ReminderCreate(
            title="测试", trigger_at=datetime.utcnow() + timedelta(minutes=5)
        ))
        note = notif_repo.enqueue(reminder)
        notif_repo.mark_delivered(note.id)

        undelivered = notif_repo.get_undelivered()
        assert all(n.id != note.id for n in undelivered)
