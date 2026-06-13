"""Schedule REST endpoints – direct CRUD (bypasses LLM agent)."""

from datetime import date

from fastapi import APIRouter, HTTPException

from app.schedule.models import EventCreate, EventResponse, EventUpdate
from app.schedule.repository import ScheduleRepository

router = APIRouter(prefix="/events")
repo = ScheduleRepository()


@router.get("")
def list_events(q: str | None = None, dt: date | None = None):
    """List events.  Optionally filter by date (?dt=2026-06-14) or keyword (?q=meeting)."""
    if q:
        events = repo.search_events(q)
    elif dt:
        events = repo.list_events_by_date(dt)
    else:
        from datetime import datetime

        now = datetime.now()
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
    event = repo.create_event(data)
    return EventResponse.model_validate(event)


@router.put("/{event_id}")
def update_event(event_id: int, data: EventUpdate) -> EventResponse:
    event = repo.update_event(event_id, data)
    if not event:
        raise HTTPException(404, "Event not found")
    return EventResponse.model_validate(event)


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int):
    ok = repo.delete_event(event_id)
    if not ok:
        raise HTTPException(404, "Event not found")
