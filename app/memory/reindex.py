"""Background embedding reindex for existing narrative memories."""

from __future__ import annotations

import json
import logging
from threading import RLock, Thread

from app.memory.embeddings import get_embedding_result

logger = logging.getLogger(__name__)


class ReindexManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state = "idle"
        self._total = 0
        self._indexed = 0
        self._failed = 0
        self._fingerprint: str | None = None
        self._restart_requested = False

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "total": self._total,
                "indexed": self._indexed,
                "failed": self._failed,
                "fingerprint": self._fingerprint,
            }

    def start(self, *, restart_if_running: bool = False) -> dict:
        with self._lock:
            if self._state == "running":
                if restart_if_running:
                    self._restart_requested = True
                return self.status()
            self._state = "running"
            self._total = self._indexed = self._failed = 0
            self._fingerprint = None
        Thread(target=self._run, daemon=True, name="memory-reindex").start()
        return self.status()

    def _run(self) -> None:
        from app.memory.models import Memory
        from app.schedule.database import SessionLocal

        db = SessionLocal()
        try:
            memories = db.query(Memory).order_by(Memory.id.asc()).all()
            with self._lock:
                self._total = len(memories)
            for memory in memories:
                try:
                    result = get_embedding_result(memory.content)
                    if result is None:
                        with self._lock:
                            self._failed += 1
                        continue
                    memory.embedding = json.dumps(result.vector)
                    memory.embedding_fingerprint = result.fingerprint
                    memory.embedding_model = result.model
                    memory.embedding_dimensions = result.dimensions
                    db.commit()
                    with self._lock:
                        self._indexed += 1
                        self._fingerprint = result.fingerprint
                except Exception as exc:
                    db.rollback()
                    logger.warning(
                        "Failed to rebuild embedding for memory %s: %s",
                        memory.id,
                        exc,
                    )
                    with self._lock:
                        self._failed += 1
            with self._lock:
                self._state = "completed"
        except Exception as exc:
            db.rollback()
            logger.warning("Memory embedding reindex failed: %s", exc)
            with self._lock:
                self._state = "failed"
        finally:
            db.close()
            with self._lock:
                restart = self._restart_requested
                self._restart_requested = False
                if restart:
                    self._state = "idle"
            if restart:
                self.start()


reindex_manager = ReindexManager()
