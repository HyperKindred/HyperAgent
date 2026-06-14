"""Tests for ScheduleRepository CRUD operations."""

from datetime import date, datetime

from app.schedule.models import EventCreate, EventUpdate


class TestCreateEvent:
    def test_create_basic_event(self, repo):
        event = repo.create_event(
            EventCreate(
                title="部门周会",
                start_time=datetime(2029, 6, 14, 9, 0),
            )
        )
        assert event.id is not None
        assert event.title == "部门周会"
        assert event.status == "pending"
        assert event.priority == "normal"

    def test_create_event_with_all_fields(self, repo):
        event = repo.create_event(
            EventCreate(
                title="完整事件",
                description="带描述的完整事件",
                start_time=datetime(2029, 6, 14, 14, 0),
                end_time=datetime(2029, 6, 14, 15, 0),
                status="pending",
                priority="high",
                category="工作会议",
            )
        )
        assert event.title == "完整事件"
        assert event.description == "带描述的完整事件"
        assert event.priority == "high"


class TestGetEvent:
    def test_get_existing_event(self, repo, sample_event):
        event = repo.get_event(sample_event.id)
        assert event is not None
        assert event.title == "测试会议"

    def test_get_nonexistent_event(self, repo):
        assert repo.get_event(999) is None


class TestListEventsByDate:
    def test_list_on_date_with_events(self, repo, sample_event):
        events = repo.list_events_by_date(date(2029, 6, 14))
        assert len(events) == 1
        assert events[0].title == "测试会议"

    def test_list_on_date_without_events(self, repo):
        events = repo.list_events_by_date(date(2026, 6, 15))
        assert len(events) == 0

    def test_list_multiple_events_same_day(self, repo):
        repo.create_event(
            EventCreate(
                title="事件A", start_time=datetime(2029, 6, 14, 9, 0)
            )
        )
        repo.create_event(
            EventCreate(
                title="事件B", start_time=datetime(2029, 6, 14, 10, 0)
            )
        )
        events = repo.list_events_by_date(date(2029, 6, 14))
        assert len(events) == 2


class TestUpdateEvent:
    def test_update_title(self, repo, sample_event):
        updated = repo.update_event(
            sample_event.id, EventUpdate(title="更新后的标题")
        )
        assert updated is not None
        assert updated.title == "更新后的标题"

    def test_update_start_time(self, repo, sample_event):
        new_time = datetime(2029, 6, 14, 15, 0)
        updated = repo.update_event(
            sample_event.id, EventUpdate(start_time=new_time)
        )
        assert updated is not None
        assert updated.start_time == new_time

    def test_update_nonexistent(self, repo):
        updated = repo.update_event(999, EventUpdate(title="nope"))
        assert updated is None


class TestDeleteEvent:
    def test_delete_existing(self, repo, sample_event):
        assert repo.delete_event(sample_event.id) is True
        assert repo.get_event(sample_event.id) is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete_event(999) is False


class TestSearchEvents:
    def test_search_by_title(self, repo, sample_event):
        results = repo.search_events("测试")
        assert len(results) == 1

    def test_search_by_description(self, repo, sample_event):
        results = repo.search_events("进度")
        assert len(results) == 1

    def test_search_no_match(self, repo):
        assert len(repo.search_events("不存在的关键词")) == 0


class TestUpcomingEvents:
    def test_upcoming_events(self, repo, sample_event):
        events = repo.get_upcoming_events()
        assert len(events) >= 1
