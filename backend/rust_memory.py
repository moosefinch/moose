"""
Rust Vector Memory - Drop-in replacement using Rust backend.

This module provides a Python wrapper around the Rust VectorMemory implementation
for backwards compatibility with existing code.
"""

from typing import Any, Optional

try:
    from moose_core import VectorMemory as RustVectorMemory
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    RustVectorMemory = None


class VectorMemory:
    """
    Drop-in replacement for the Python VectorMemory using Rust backend.

    This wrapper provides the same interface as the original Python implementation
    but delegates all operations to the high-performance Rust implementation.

    Features:
    - SIMD-accelerated cosine similarity search
    - Pre-normalized vectors for efficient search
    - Connection pooling for embedding HTTP requests
    - JSONL persistence
    """

    def __init__(self, persistence_path: Optional[str] = None):
        """
        Initialize the VectorMemory.

        Args:
            persistence_path: Optional path for JSONL persistence.
                            Defaults to "backend/memory.jsonl"
        """
        if not RUST_AVAILABLE:
            raise ImportError(
                "moose_core Rust extension not available. "
                "Build with: cd backend/rust_core && maturin develop --release"
            )

        self._inner = RustVectorMemory(persistence_path)

    def set_embedder(self, api_base: str, model_id: str) -> None:
        """
        Configure the embedding endpoint.

        Args:
            api_base: Base URL for the embedding API (e.g., "http://localhost:1234")
            model_id: Model identifier for embeddings
        """
        self._inner.set_embedder(api_base, model_id)

    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        return await self._inner.embed(text)

    async def store(
        self,
        text: str,
        tags: str = "",
        metadata: Optional[dict[str, Any]] = None,
        temporal_type: str = "",
        valid_from: float = 0.0,
        valid_to: float = 0.0,
        entity_type: str = "",
        entity_id: str = "",
        source: str = "internal",
    ) -> int:
        """
        Store text with embedding in memory.

        Args:
            text: Text to store
            tags: Comma-separated tags (validated, max 20 tags, 50 chars each)
            metadata: Optional metadata dictionary
            temporal_type: Type of temporal validity
            valid_from: Start of validity period (Unix timestamp)
            valid_to: End of validity period (Unix timestamp)
            entity_type: Type of entity this memory relates to
            entity_id: ID of entity this memory relates to
            source: Source of memory ("internal", "external", "user")

        Returns:
            Index of stored entry
        """
        return await self._inner.store(
            text,
            tags,
            metadata,
            temporal_type,
            valid_from,
            valid_to,
            entity_type,
            entity_id,
            source,
        )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        temporal_filter: str = "",
    ) -> list[dict]:
        """
        Search memory by semantic similarity.

        Args:
            query: Query text
            top_k: Number of results to return
            temporal_filter: Optional temporal filter ("current" or "historical")

        Returns:
            List of matching entries with scores
        """
        results = await self._inner.search(query, top_k, temporal_filter)

        # Convert Rust results to Python dicts
        return [
            {
                "text": entry[0]["text"] if isinstance(entry, tuple) else entry.get("text", ""),
                "tags": entry[0]["tags"] if isinstance(entry, tuple) else entry.get("tags", ""),
                "timestamp": entry[0]["timestamp"] if isinstance(entry, tuple) else entry.get("timestamp", 0.0),
                "score": entry[1] if isinstance(entry, tuple) else entry.get("score", 0.0),
                "source": entry[0].get("source", "internal") if isinstance(entry, tuple) else entry.get("source", "internal"),
                "temporal_type": entry[0].get("temporal_type", "") if isinstance(entry, tuple) else entry.get("temporal_type", ""),
                "valid_from": entry[0].get("valid_from", 0.0) if isinstance(entry, tuple) else entry.get("valid_from", 0.0),
                "valid_to": entry[0].get("valid_to", 0.0) if isinstance(entry, tuple) else entry.get("valid_to", 0.0),
                "entity_type": entry[0].get("entity_type", "") if isinstance(entry, tuple) else entry.get("entity_type", ""),
                "entity_id": entry[0].get("entity_id", "") if isinstance(entry, tuple) else entry.get("entity_id", ""),
            }
            for entry in results
        ]

    def count(self) -> int:
        """
        Get the number of entries in memory.

        Returns:
            Number of stored entries
        """
        return self._inner.count()

    def clear(self) -> None:
        """Clear all memory entries and delete persistence file."""
        self._inner.clear()

    def get_all(self) -> list[dict]:
        """
        Get all entries (for debugging/export).

        Returns:
            List of all memory entries
        """
        return list(self._inner.get_all())

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Batch embed multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        return await self._inner.embed_batch(texts)


# Export for backwards compatibility
__all__ = ["VectorMemory", "RUST_AVAILABLE"]
