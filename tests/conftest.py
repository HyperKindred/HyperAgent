"""Shared test fixtures: in-memory SQLite and repository."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.memory.models import MemoryCreate
from app.memory.repository import MemoryRepository
from app.schedule.database import Base
from app.schedule.models import EventCreate
from app.schedule.repository import ScheduleRepository


@pytest.fixture
def session():
    """Provide an in-memory SQLite session for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    yield db
    db.close()


@pytest.fixture
def repo(session):
    """Repository backed by in-memory SQLite."""
    return ScheduleRepository(session=session)


@pytest.fixture
def sample_event(repo):
    """Insert a single sample event and return it."""
    return repo.create_event(
        EventCreate(
            title="测试会议",
            description="项目进度讨论",
            start_time=datetime(2029, 6, 14, 10, 0),
            end_time=datetime(2029, 6, 14, 11, 0),
            priority="high",
        )
    )


@pytest.fixture
def memory_repo(session):
    """MemoryRepository backed by in-memory SQLite."""
    return MemoryRepository(session=session)
