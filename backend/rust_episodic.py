"""
Rust Episodic Memory - Drop-in replacement using Rust backend.

This module provides a Python wrapper around the Rust EpisodicMemory implementation
for backwards compatibility with existing code.
"""

from typing import Any, Callable, Optional

try:
    from moose_core import EpisodicMemory as RustEpisodicMemory
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    RustEpisodicMemory = None


class EpisodicMemory:
    """
    Drop-in replacement for the Python EpisodicMemory using Rust backend.

    This wrapper provides the same interface as the original Python implementation
    but delegates all operations to the high-performance Rust implementation.

    Features:
    - SQLite-backed persistence with WAL mode
    - Vector similarity search with importance weighting
    - Automatic importance decay over time
    - Entity supersession for knowledge updates
    - Low-importance memory eviction
    """

    def __init__(self, db_path: str = "backend/episodic.db"):
        """
        Initialize the EpisodicMemory.

        Args:
            db_path: Path to SQLite database file
        """
        if not RUST_AVAILABLE:
            raise ImportError(
                "moose_core Rust extension not available. "
                "Build with: cd backend/rust_core && maturin develop --release"
            )

        self._inner = RustEpisodicMemory(db_path)

    def set_embedder(self, embedder: Callable[[str], list[float]]) -> None:
        """
        Set the embedder function.

        Args:
            embedder: A callable that takes text and returns embedding vector
        """
        self._inner.set_embedder(embedder)

    async def store(
        self,
        content: str,
        memory_type: str,
        domain: Optional[str] = None,
        importance: float = 1.0,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        supersedes: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Store a new episodic memory.

        Args:
            content: Memory content
            memory_type: Type of memory (fact, event, preference, skill, entity, relationship, context)
            domain: Optional domain/category
            importance: Initial importance score (0.0 to 1.0)
            entity_type: Type of entity this memory relates to
            entity_id: ID of entity this memory relates to
            supersedes: ID of memory this one supersedes
            metadata: Additional metadata

        Returns:
            ID of the stored memory
        """
        return await self._inner.store(
            content,
            memory_type,
            domain,
            importance,
            entity_type,
            entity_id,
            supersedes,
            metadata,
        )

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[dict[str, Any]] = None,
        include_superseded: bool = False,
    ) -> list[dict]:
        """
        Search episodic memories with optional filters.

        Args:
            query: Search query
            top_k: Number of results to return
            filters: Optional filters (memory_type, domain, entity_type, entity_id)
            include_superseded: Whether to include superseded memories

        Returns:
            List of matching memories with scores
        """
        results = await self._inner.search(query, top_k, filters, include_superseded)

        # Convert Rust results to Python dicts
        return [
            {
                "id": entry[0]["id"] if isinstance(entry, tuple) else entry.get("id", ""),
                "content": entry[0]["content"] if isinstance(entry, tuple) else entry.get("content", ""),
                "memory_type": entry[0]["memory_type"] if isinstance(entry, tuple) else entry.get("memory_type", ""),
                "domain": entry[0].get("domain") if isinstance(entry, tuple) else entry.get("domain"),
                "importance": entry[0]["importance"] if isinstance(entry, tuple) else entry.get("importance", 0.0),
                "access_count": entry[0]["access_count"] if isinstance(entry, tuple) else entry.get("access_count", 0),
                "last_accessed": entry[0]["last_accessed"] if isinstance(entry, tuple) else entry.get("last_accessed", ""),
                "created_at": entry[0]["created_at"] if isinstance(entry, tuple) else entry.get("created_at", ""),
                "entity_type": entry[0].get("entity_type") if isinstance(entry, tuple) else entry.get("entity_type"),
                "entity_id": entry[0].get("entity_id") if isinstance(entry, tuple) else entry.get("entity_id"),
                "supersedes": entry[0].get("supersedes") if isinstance(entry, tuple) else entry.get("supersedes"),
                "superseded_by": entry[0].get("superseded_by") if isinstance(entry, tuple) else entry.get("superseded_by"),
                "score": entry[1] if isinstance(entry, tuple) else entry.get("score", 0.0),
            }
            for entry in results
        ]

    def decay_importance(self, decay_rate: float = 0.05) -> int:
        """
        Apply importance decay to all memories.

        Args:
            decay_rate: Decay rate per day (default 5%)

        Returns:
            Number of memories updated
        """
        return self._inner.decay_importance(decay_rate)

    def evict_low_importance(
        self,
        min_age_days: int = 30,
        min_importance: float = 0.1,
    ) -> int:
        """
        Evict low-importance memories older than min_age_days.

        Args:
            min_age_days: Minimum age in days before eligible for eviction
            min_importance: Importance threshold below which to evict

        Returns:
            Number of memories evicted
        """
        return self._inner.evict_low_importance(min_age_days, min_importance)

    def count(self) -> int:
        """
        Get the total memory count.

        Returns:
            Number of stored memories
        """
        return self._inner.count()

    def get(self, memory_id: str) -> Optional[dict]:
        """
        Get a memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory dict or None if not found
        """
        return self._inner.get(memory_id)

    def update_importance(self, memory_id: str, importance: float) -> bool:
        """
        Update a memory's importance.

        Args:
            memory_id: Memory ID
            importance: New importance value

        Returns:
            True if updated, False if not found
        """
        return self._inner.update_importance(memory_id, importance)

    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            True if deleted, False if not found
        """
        return self._inner.delete(memory_id)

    def stats(self) -> dict:
        """
        Get statistics about the memory store.

        Returns:
            Dictionary with statistics
        """
        return self._inner.stats()

    def clear(self) -> None:
        """Clear all memories."""
        self._inner.clear()

    def get_entity_memories(
        self,
        entity_type: str,
        entity_id: str,
        include_superseded: bool = False,
    ) -> list[dict]:
        """
        Get all memories for a specific entity.

        Args:
            entity_type: Entity type
            entity_id: Entity ID
            include_superseded: Whether to include superseded memories

        Returns:
            List of memories for the entity
        """
        return list(self._inner.get_entity_memories(entity_type, entity_id, include_superseded))

    async def supersede(
        self,
        old_id: str,
        new_content: str,
        importance: float = 1.0,
    ) -> str:
        """
        Supersede an existing memory with new content.

        Args:
            old_id: ID of memory to supersede
            new_content: New memory content
            importance: Importance of new memory

        Returns:
            ID of the new memory
        """
        return await self._inner.supersede(old_id, new_content, importance)


# Export for backwards compatibility
__all__ = ["EpisodicMemory", "RUST_AVAILABLE"]
