"""APScheduler integration for reminder dispatch.

Uses BackgroundScheduler + MemoryJobStore.
On startup, reloads all pending reminders from DB and schedules them.
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.reminder.models import Reminder
from app.reminder.repository import ReminderRepository, NotificationRepository
from app.utils.time import ensure_utc, now as utc_now

logger = logging.getLogger(__name__)

# Singleton
scheduler: BackgroundScheduler | None = None
_event_loop: asyncio.AbstractEventLoop | None = None
# Thread lock for _sse_clients access from APScheduler background thread
_sse_lock = threading.Lock()


def fire_reminder(reminder_id: int) -> None:
    """Callback when a reminder's trigger time arrives.

    Uses an atomic ``UPDATE ... WHERE status='pending'`` check in
    ``mark_fired()`` to prevent duplicate delivery when both the
    APScheduler ``DateTrigger`` and the periodic safety-net scan
    call this function for the same reminder.
    """
    logger.info("Reminder %s fired", reminder_id)
    reminder_repo = ReminderRepository()
    notif_repo = NotificationRepository()

    # Atomic: mark_fired now filters by status='pending' and returns
    # None if the reminder was already fired/cancelled.
    reminder = reminder_repo.mark_fired(reminder_id)
    if reminder is None:
        logger.debug("Reminder %s already fired or cancelled, skipping", reminder_id)
        return

    # Enqueue a notification for SSE delivery
    notification = notif_repo.enqueue(reminder)

    # A recurring reminder must become pending again after its delivery.
    # Persist the next time first so the safety scan and an application restart
    # agree on the same future occurrence.
    if reminder.recurring:
        next_trigger = _schedule_recurring(reminder)
        if next_trigger is not None:
            reminder_repo.reschedule_recurring(reminder.id, next_trigger)

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
        from app.reminder.notifier import _sse_clients

        payload = json.dumps({
            "id": notification.id,
            "event_type": notification.event_type,
            "title": notification.title,
            "body": notification.body,
            "created_at": notification.created_at.isoformat(),
        }, ensure_ascii=False)

        with _sse_lock:
            clients = list(_sse_clients)

        for queue in clients:
            asyncio.run_coroutine_threadsafe(queue.put(payload), loop)
    except Exception as e:
        logger.warning("Failed to push notification to SSE: %s", e)


def _recurring_cron_trigger(reminder: Reminder) -> CronTrigger:
    """Build the application's timezone-aware trigger for a recurring reminder."""
    return CronTrigger.from_crontab(
        reminder.recurring,
        timezone=pytz.timezone(settings.timezone),
    )


def _schedule_recurring(reminder: Reminder) -> datetime | None:
    """Schedule a recurring reminder and return its next naive-UTC occurrence."""
    global scheduler
    try:
        trigger = _recurring_cron_trigger(reminder)
        # The callback may run exactly on a cron boundary. Advance a second so
        # a just-delivered occurrence is never persisted as the next one.
        reference_time = datetime.now(trigger.timezone) + timedelta(seconds=1)
        next_run = trigger.get_next_fire_time(None, reference_time)
        next_trigger = ensure_utc(next_run)
        if next_trigger is None:
            logger.error("Recurring reminder %s has no future occurrence", reminder.id)
            return None
        if scheduler is not None:
            scheduler.add_job(
                fire_reminder,
                trigger,
                args=[reminder.id],
                id=f"reminder-{reminder.id}",
                replace_existing=True,
                misfire_grace_time=60,
            )
            logger.info(
                "Recurring reminder %s scheduled with cron: %s",
                reminder.id,
                reminder.recurring,
            )
        return next_trigger
    except Exception as e:
        logger.error("Failed to schedule recurring reminder %s: %s", reminder.id, e)
        return None


def schedule_reminder_job(reminder: Reminder) -> None:
    """Schedule a single reminder job in APScheduler."""
    global scheduler
    if reminder.recurring:
        next_trigger = _schedule_recurring(reminder)
        if next_trigger is not None:
            ReminderRepository().reschedule_recurring(reminder.id, next_trigger)
        return
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
    Uses atomic ``mark_fired()`` to avoid duplicate delivery with DateTrigger.
    """
    repo = ReminderRepository()
    pending = repo.list_pending()
    now = utc_now()  # stored trigger_at is naive UTC

    for r in pending:
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
    for r in pending:
        if r.recurring:
            next_trigger = _schedule_recurring(r)
            if next_trigger is not None:
                repo.reschedule_recurring(r.id, next_trigger)
        elif r.trigger_at > utc_now():
            schedule_reminder_job(r)

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
