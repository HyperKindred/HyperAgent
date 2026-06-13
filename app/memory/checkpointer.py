import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import settings


def get_checkpointer() -> SqliteSaver:
    """Create a SqliteSaver checkpoint instance backed by a local SQLite file.

    The checkpointer persists:
    - Full conversation message history
    - Agent state (tool calls, intermediate results)
    - Thread-specific isolation via ``thread_id``
    """
    db_path: Path = settings.data_dir / "checkpoints.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)
