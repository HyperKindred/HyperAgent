import sqlite3
import asyncio
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import settings


class _AsyncCompatSqliteSaver(SqliteSaver):
    """SqliteSaver that adds async support by delegating to sync methods
    via a thread-pool executor.

    No extra dependencies needed — we just wrap ``aget_tuple`` / ``aput`` /
    ``aput_writes`` with ``asyncio.to_thread`` so ``astream_events`` works.
    """

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config, checkpoint, metadata, new_versions=None):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        return await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)


def get_checkpointer() -> _AsyncCompatSqliteSaver:
    """Create a SqliteSaver checkpoint instance backed by a local SQLite file.

    The checkpointer persists:
    - Full conversation message history
    - Agent state (tool calls, intermediate results)
    - Thread-specific isolation via ``thread_id``
    """
    db_path: Path = settings.data_dir / "checkpoints.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return _AsyncCompatSqliteSaver(conn)
