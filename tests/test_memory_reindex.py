"""Tests for resilient background embedding reindexing."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.memory.embeddings import EmbeddingResult
from app.memory.models import Memory, MemoryCreate
from app.memory.reindex import ReindexManager
from app.memory.repository import MemoryRepository
from app.schedule.database import Base


def test_reindex_continues_after_one_embedding_failure(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("app.memory.repository.get_embedding_result", lambda _text: None)
    setup_session = Session()
    try:
        repo = MemoryRepository(session=setup_session)
        first = repo.create_memory(MemoryCreate(content="第一条记忆"))
        failed = repo.create_memory(MemoryCreate(content="失败的记忆"))
        last = repo.create_memory(MemoryCreate(content="最后一条记忆"))
        first_id, failed_id, last_id = first.id, failed.id, last.id
    finally:
        setup_session.close()

    monkeypatch.setattr("app.schedule.database.SessionLocal", Session)

    def fake_embedding(text: str):
        if text == "失败的记忆":
            raise RuntimeError("provider unavailable")
        return EmbeddingResult(
            vector=[0.1, 0.2],
            model="test-embedding",
            dimensions=2,
            fingerprint="test-provider",
            source="separate",
        )

    monkeypatch.setattr("app.memory.reindex.get_embedding_result", fake_embedding)
    manager = ReindexManager()
    manager._run()

    assert manager.status() == {
        "state": "completed",
        "total": 3,
        "indexed": 2,
        "failed": 1,
        "fingerprint": "test-provider",
    }

    verify_session = Session()
    try:
        rows = {row.id: row for row in verify_session.query(Memory).all()}
        assert rows[first_id].embedding_model == "test-embedding"
        assert rows[failed_id].embedding is None
        assert rows[last_id].embedding_dimensions == 2
    finally:
        verify_session.close()
