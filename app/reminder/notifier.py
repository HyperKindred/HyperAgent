"""SSE (Server-Sent Events) notification manager.

Maintains a set of active SSE client queues.
When a reminder fires, it enqueues a notification that gets pushed
to all connected SSE clients.
"""

import asyncio
import json
import logging
import threading
from typing import AsyncGenerator

from app.reminder.models import PendingNotification
from app.reminder.repository import NotificationRepository

logger = logging.getLogger(__name__)

# Active SSE client queues (thread-safe via _sse_lock)
_sse_clients: set[asyncio.Queue] = set()
_sse_lock = threading.Lock()


async def sse_event_stream() -> AsyncGenerator[str, None]:
    """SSE generator — yields incoming notifications as SSE-formatted events.

    Each connected client gets its own queue. When a new notification arrives,
    it's pushed to all active clients.  Notifications are marked ``delivered``
    immediately on push to prevent duplicate delivery by the periodic sweep.
    """
    queue: asyncio.Queue = asyncio.Queue()
    with _sse_lock:
        _sse_clients.add(queue)

    try:
        # Flush any undelivered notifications from DB first
        repo = NotificationRepository()
        undelivered = repo.get_undelivered()
        for note in undelivered:
            data = _notification_data(note)
            yield f"data: {data}\n\n"
            repo.mark_delivered(note.id)

        # Then listen for new ones + periodically sweep undelivered
        repo = NotificationRepository()
        while True:
            try:
                notification = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {notification}\n\n"
            except asyncio.TimeoutError:
                # Periodic sweep: flush any undelivered notifications (safety net)
                undelivered = repo.get_undelivered()
                for note in undelivered:
                    data = _notification_data(note)
                    yield f"data: {data}\n\n"
                    repo.mark_delivered(note.id)
                # Send keepalive to prevent connection timeout
                yield ": keepalive\n\n"
    finally:
        with _sse_lock:
            _sse_clients.discard(queue)
        logger.debug("SSE client disconnected")


async def broadcast_notification(title: str, body: str, event_type: str = "reminder") -> None:
    """Enqueue a notification and push to all connected SSE clients.

    Args:
        title: Notification title
        body: Notification body text
        event_type: Type of event (reminder, suggestion, third_party, etc.)
    """
    repo = NotificationRepository()
    note = PendingNotification(
        reminder_id=None,
        event_type=event_type,
        title=title,
        body=body,
    )

    # Use the repository to persist
    from app.reminder.repository import ReminderRepository

    # We need a minimal Reminder-like object to use NotificationRepository.enqueue
    # but broadcast has no reminder, so we insert directly
    db = repo._session()
    try:
        db.add(note)
        db.commit()
        db.refresh(note)
    except Exception:
        db.rollback()
        raise
    finally:
        if repo._db is None:
            db.close()

    payload = json.dumps({
        "id": note.id,
        "event_type": note.event_type,
        "title": note.title,
        "body": note.body,
        "created_at": note.created_at.isoformat(),
    }, ensure_ascii=False)

    # Push to all connected SSE clients
    with _sse_lock:
        clients = list(_sse_clients)

    if clients:
        logger.info("Broadcasting notification '%s' to %d SSE clients", title, len(clients))
        for queue in clients:
            await queue.put(payload)


def _notification_data(note) -> str:
    """Format a PendingNotification as a JSON string for SSE."""
    return json.dumps({
        "id": note.id,
        "event_type": note.event_type,
        "title": note.title,
        "body": note.body,
        "created_at": note.created_at.isoformat() if note.created_at else "",
    }, ensure_ascii=False)
