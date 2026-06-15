"""REST API routes for reminders and SSE notifications."""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.reminder.models import ReminderCreate, ReminderResponse
from app.reminder.notifier import sse_event_stream
from app.reminder.repository import ReminderRepository
from app.reminder.scheduler import cancel_reminder_job, schedule_reminder_job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reminder"])


@router.get("/notifications/stream")
async def notification_stream():
    """SSE endpoint: push reminders and other notifications to connected clients."""
    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/reminders", response_model=ReminderResponse)
async def create_reminder(data: ReminderCreate):
    """Create a new reminder and schedule it in APScheduler."""
    repo = ReminderRepository()
    reminder = repo.create(data)
    schedule_reminder_job(reminder)
    logger.info("Reminder created: %s (id=%d, trigger=%s)", reminder.title, reminder.id, reminder.trigger_at)
    return reminder


@router.get("/reminders", response_model=list[ReminderResponse])
async def list_reminders():
    """List all reminders (newest first)."""
    repo = ReminderRepository()
    return repo.list_all()


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int):
    """Delete a reminder and cancel its APScheduler job."""
    repo = ReminderRepository()
    success = repo.delete(reminder_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reminder not found")
    cancel_reminder_job(reminder_id)
    logger.info("Reminder %d deleted", reminder_id)
    return {"status": "ok"}


@router.post("/reminders/{reminder_id}/cancel")
async def cancel_reminder(reminder_id: int):
    """Cancel a pending reminder (mark as cancelled + remove APScheduler job)."""
    repo = ReminderRepository()
    success = repo.cancel(reminder_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reminder not found")
    cancel_reminder_job(reminder_id)
    logger.info("Reminder %d cancelled", reminder_id)
    return {"status": "ok"}
