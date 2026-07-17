"""Schedule REST endpoints – direct CRUD (bypasses LLM agent)."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException
import pytz

from app.config import settings
from app.schedule.models import EventCreate, EventResponse, EventUpdate
from app.schedule.notifier import notify_created, notify_deleted, notify_updated
from app.schedule.repository import ScheduleRepository
from app.reminder.repository import ReminderRepository
from app.reminder.scheduler import cancel_reminder_job
from app.utils.time import from_local

router = APIRouter(prefix="/events")
repo = ScheduleRepository()


@router.get("")
def list_events(q: str | None = None, dt: date | None = None, month: str | None = None):
    if q:
        events = repo.search_events(q)
    elif month:
        # Parse YYYY-MM and get all events in that month
        year, m = int(month[:4]), int(month[5:7])
        start = date(year, m, 1)
        if m == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, m + 1, 1)
        events = repo.list_events_by_date_range(start, end)
    elif dt:
        events = repo.list_events_by_date(dt)
    else:
        now = datetime.now(pytz.timezone(settings.timezone))
        events = repo.list_events_by_date(now.date())
    return [EventResponse.model_validate(e) for e in events]


@router.get("/{event_id}")
def get_event(event_id: int) -> EventResponse:
    event = repo.get_event(event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    return EventResponse.model_validate(event)


@router.post("", status_code=201)
def create_event(data: EventCreate) -> EventResponse:
    event = repo.create_event(
        data.model_copy(
            update={
                "start_time": from_local(data.start_time, settings.timezone),
                "end_time": (
                    from_local(data.end_time, settings.timezone)
                    if data.end_time is not None
                    else None
                ),
            }
        )
    )
    notify_created(event.title, event.id)
    return EventResponse.model_validate(event)


@router.put("/{event_id}")
def update_event(event_id: int, data: EventUpdate) -> EventResponse:
    values = data.model_dump(exclude_unset=True)
    for field in ("start_time", "end_time"):
        if field in values and values[field] is not None:
            values[field] = from_local(values[field], settings.timezone)
    event = repo.update_event(event_id, EventUpdate(**values))
    if not event:
        raise HTTPException(404, "Event not found")
    notify_updated(event.title, event.id)
    return EventResponse.model_validate(event)


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int):
    event = repo.get_event(event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    title = event.title

    # Delete linked reminder, if any
    try:
        linked = ReminderRepository().get_by_event_id(event_id)
        if linked:
            cancel_reminder_job(linked.id)
            ReminderRepository().delete(linked.id)
    except Exception:
        pass

    repo.delete_event(event_id)
    notify_deleted(title, event_id)
