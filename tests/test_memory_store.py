"""Memory-store contract and default implementation tests."""

from app.memory.repository import MemoryRepository
from app.memory.store import MemoryStore, get_memory_store


def test_default_memory_store_implements_contract():
    store = get_memory_store()

    assert isinstance(store, MemoryStore)
    assert isinstance(store, MemoryRepository)
