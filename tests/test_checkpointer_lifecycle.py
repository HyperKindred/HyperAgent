"""Lifecycle tests for the cached LangGraph checkpoint connection."""

from app.agent import graph


def test_close_checkpointer_closes_cached_connection(monkeypatch):
    class FakeConnection:
        closed = False

        def close(self):
            self.closed = True

    class FakeCheckpointer:
        def __init__(self):
            self.conn = FakeConnection()

    saver = FakeCheckpointer()
    monkeypatch.setattr(graph, "_checkpointer", saver)

    graph.close_checkpointer()

    assert saver.conn.closed is True
    assert graph._checkpointer is None
