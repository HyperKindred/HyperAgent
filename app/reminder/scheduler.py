"""APScheduler integration for reminder dispatch.

Uses BackgroundScheduler + MemoryJobStore.
On startup, reloads all pending reminders from DB and schedules them.
"""

import asyncio
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.reminder.models import Reminder
from app.reminder.repository import ReminderRepository, NotificationRepository

logger = logging.getLogger(__name__)

tz = pytz.timezone(settings.timezone)

# Singleton
scheduler: BackgroundScheduler | None = None
_event_loop: asyncio.AbstractEventLoop | None = None


def fire_reminder(reminder_id: int) -> None:
    """Callback when a reminder's trigger time arrives."""
    logger.info("Reminder %s fired", reminder_id)
    reminder_repo = ReminderRepository()
    notif_repo = NotificationRepository()

    reminder = reminder_repo.get_by_id(reminder_id)
    if reminder is None or reminder.status != "pending":
        return

    # Enqueue a notification for SSE delivery
    notification = notif_repo.enqueue(reminder)

    # Mark as fired
    reminder_repo.mark_fired(reminder_id)

    # If recurring, schedule the next occurrence
    if reminder.recurring:
        _schedule_recurring(reminder)

    logger.info("Notification %s enqueued for reminder '%s'", notification.id, reminder.title)

    # Push to SSE clients in real-time
    _push_notification_to_sse(notification)


def _push_notification_to_sse(notification) -> None:
    """Push a PendingNotification to all connected SSE clients."""
    global _event_loop
    loop = _event_loop
    if loop is None or not loop.is_running():
        return
    try:
        import json

        from app.reminder.notifier import _sse_clients

        payload = json.dumps({
            "id": notification.id,
            "event_type": notification.event_type,
            "title": notification.title,
            "body": notification.body,
            "created_at": notification.created_at.isoformat(),
        }, ensure_ascii=False)

        if _sse_clients:
            for queue in _sse_clients.copy():
                asyncio.run_coroutine_threadsafe(queue.put(payload), loop)
    except Exception as e:
        logger.warning("Failed to push notification to SSE: %s", e)


def _schedule_recurring(reminder: Reminder) -> None:
    """Schedule the next occurrence of a recurring reminder."""
    global scheduler
    if scheduler is None:
        return
    try:
        scheduler.add_job(
            fire_reminder,
            CronTrigger.from_crontab(reminder.recurring),
            args=[reminder.id],
            id=f"reminder-{reminder.id}",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Recurring reminder %s scheduled with cron: %s", reminder.id, reminder.recurring)
    except Exception as e:
        logger.error("Failed to schedule recurring reminder %s: %s", reminder.id, e)


def schedule_reminder_job(reminder: Reminder) -> None:
    """Schedule a single reminder job in APScheduler."""
    global scheduler
    if scheduler is None:
        logger.warning("Scheduler not initialized")
        return

    trigger = DateTrigger(run_date=reminder.trigger_at)
    scheduler.add_job(
        fire_reminder,
        trigger,
        args=[reminder.id],
        id=f"reminder-{reminder.id}",
        replace_existing=True,
        misfire_grace_time=60,
    )
    logger.info("Reminder %s scheduled for %s", reminder.id, reminder.trigger_at)


def cancel_reminder_job(reminder_id: int) -> None:
    """Remove a job from APScheduler."""
    global scheduler
    if scheduler is None:
        return
    try:
        scheduler.remove_job(f"reminder-{reminder_id}")
        logger.info("Reminder job %s cancelled", reminder_id)
    except Exception:
        pass  # Job may not exist


def _scan_and_schedule() -> None:
    """Periodic scan: check DB for pending reminders that should have fired already.

    Acts as a safety net in case the DateTrigger missed something.
    Fires off reminders that are past their trigger_at time.
    """
    repo = ReminderRepository()
    reminders = repo.list_pending()
    now = datetime.now(tz).replace(tzinfo=None)  # naive local time, matching stored trigger_at

    for r in reminders:
        if r.trigger_at <= now:
            logger.info("Safety net: firing reminder %s (triggered at %s)", r.id, r.trigger_at)
            fire_reminder(r.id)


def start_scheduler() -> BackgroundScheduler:
    """Initialize and start the APScheduler background scheduler."""
    global scheduler, _event_loop

    if scheduler is not None:
        return scheduler

    # Save reference to the main event loop for SSE pushing from scheduler thread
    try:
        _event_loop = asyncio.get_running_loop()
    except RuntimeError:
        _event_loop = None
        logger.warning("No running event loop found; SSE push disabled")

    scheduler = BackgroundScheduler(
        job_defaults={"misfire_grace_time": 60},
    )

    # Safety net: scan every 30 seconds
    scheduler.add_job(
        _scan_and_schedule,
        IntervalTrigger(seconds=30),
        id="safety-scan",
        replace_existing=True,
    )

    # Load pending reminders from DB and schedule them
    repo = ReminderRepository()
    pending = repo.list_pending()
    now = datetime.now(tz).replace(tzinfo=None)  # naive local time
    for r in pending:
        if r.trigger_at > now:
            schedule_reminder_job(r)
        elif r.recurring:
            # Past due recurring — schedule anyway (next occurrence logic)
            _schedule_recurring(r)

    scheduler.start()
    logger.info("APScheduler started with %d pending reminders", len(pending))
    return scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("APScheduler stopped")
