"""Calendar API timezone boundary tests."""

from datetime import datetime

from app.api import schedule as schedule_api
from app.schedule.models import Event, EventCreate, EventResponse


def _event_from(data: EventCreate) -> Event:
    return Event(
        id=1,
        title=data.title,
        description=data.description,
        start_time=data.start_time,
        end_time=data.end_time,
        status=data.status,
        priority=data.priority,
        category=data.category,
    )


def test_create_event_interprets_naive_browser_time_in_app_timezone(monkeypatch):
    class CapturingRepository:
        received: EventCreate | None = None

        def create_event(self, data: EventCreate) -> Event:
            self.received = data
            return _event_from(data)

    repo = CapturingRepository()
    monkeypatch.setattr(schedule_api, "repo", repo)
    monkeypatch.setattr(schedule_api.settings, "timezone", "Asia/Shanghai")

    schedule_api.create_event(EventCreate(
        title="本地九点会议",
        start_time=datetime(2029, 6, 14, 9, 0),
    ))

    assert repo.received is not None
    assert repo.received.start_time == datetime(2029, 6, 14, 1, 0)


def test_event_response_displays_utc_storage_in_configured_local_time(monkeypatch):
    monkeypatch.setattr("app.schedule.models.settings.timezone", "Asia/Shanghai")
    event = Event(
        id=1,
        title="本地九点会议",
        description="",
        start_time=datetime(2029, 6, 14, 1, 0),
        end_time=None,
        status="pending",
        priority="normal",
        category="",
    )

    payload = EventResponse.model_validate(event).model_dump(mode="json")

    assert payload["start_time"] == "2029-06-14T09:00:00"
