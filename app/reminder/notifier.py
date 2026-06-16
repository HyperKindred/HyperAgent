"""SSE (Server-Sent Events) notification manager.

Maintains a set of active SSE client queues.
When a reminder fires, it enqueues a notification that gets pushed
to all connected SSE clients.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.reminder.repository import NotificationRepository

logger = logging.getLogger(__name__)

# Active SSE client queues
_sse_clients: set[asyncio.Queue] = set()


async def sse_event_stream() -> AsyncGenerator[str, None]:
    """SSE generator — yields incoming notifications as SSE-formatted events.

    Each connected client gets its own queue. When a new notification arrives,
    it's pushed to all active clients.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _sse_clients.add(queue)

    try:
        # Flush any undelivered notifications from DB first
        repo = NotificationRepository()
        undelivered = repo.get_undelivered()
        for note in undelivered:
            data = {
                "id": note.id,
                "event_type": note.event_type,
                "title": note.title,
                "body": note.body,
                "created_at": note.created_at.isoformat(),
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            repo.mark_delivered(note.id)

        # Then listen for new ones + periodically sweep undelivered
        while True:
            try:
                notification = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {notification}\n\n"
            except asyncio.TimeoutError:
                # Periodic sweep: flush any undelivered notifications (safety net)
                repo = NotificationRepository()
                undelivered = repo.get_undelivered()
                for note in undelivered:
                    data = {
                        "id": note.id,
                        "event_type": note.event_type,
                        "title": note.title,
                        "body": note.body,
                        "created_at": note.created_at.isoformat(),
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    repo.mark_delivered(note.id)
                # Send keepalive to prevent connection timeout
                yield ": keepalive\n\n"
    finally:
        _sse_clients.discard(queue)
        logger.debug("SSE client disconnected")


async def broadcast_notification(title: str, body: str, event_type: str = "reminder") -> None:
    """Enqueue a notification and push to all connected SSE clients.

    Args:
        title: Notification title
        body: Notification body text
        event_type: Type of event (reminder, suggestion, third_party, etc.)
    """
    # Persist to DB
    from app.reminder.models import Reminder
    from app.reminder.repository import ReminderRepository, NotificationRepository

    repo = NotificationRepository()
    # Create a minimal reminder-like object for enqueue
    # (or directly insert into PendingNotification)

    from app.schedule.database import SessionLocal
    from app.reminder.models import PendingNotification

    db = SessionLocal()
    try:
        note = PendingNotification(
            reminder_id=None,
            event_type=event_type,
            title=title,
            body=body,
        )
        db.add(note)
        db.commit()
        db.refresh(note)

        payload = json.dumps({
            "id": note.id,
            "event_type": note.event_type,
            "title": note.title,
            "body": note.body,
            "created_at": note.created_at.isoformat(),
        }, ensure_ascii=False)

        # Push to all connected SSE clients
        if _sse_clients:
            logger.info("Broadcasting notification '%s' to %d SSE clients", title, len(_sse_clients))
            for queue in _sse_clients.copy():
                await queue.put(payload)
    finally:
        db.close()
