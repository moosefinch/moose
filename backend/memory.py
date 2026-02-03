"""
Agent Vector Memory — embeddings-based semantic store.
Uses Nomic Embed via LM Studio HTTP API + numpy for similarity search.
Persists to memory.jsonl.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

logger = logging.getLogger(__name__)

MEMORY_PATH = Path(__file__).parent / "memory.jsonl"
MAX_MEMORY_ENTRIES = 10_000  # Evict oldest entries beyond this limit


class VectorMemory:
    def __init__(self):
        self.entries: list[dict] = []  # {text, vector, tags, timestamp}
        self.vectors: Optional[np.ndarray] = None
        self._api_base: Optional[str] = None
        self._embed_model: Optional[str] = None
        self._lock = asyncio.Lock()
        self._load()

    def set_embedder(self, api_base: str, model_id: str):
        """Configure the embedding endpoint."""
        self._api_base = api_base
        self._embed_model = model_id

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text via LM Studio HTTP API."""
        if not self._api_base or not self._embed_model:
            raise RuntimeError("Embedder not configured")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._api_base}/v1/embeddings",
                    json={"model": self._embed_model, "input": text},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Embedding API returned {e.response.status_code}: {e.response.text[:200]}")
        except httpx.ConnectError as e:
            raise RuntimeError(f"Cannot connect to embedding API at {self._api_base}: {e}")
        except Exception as e:
            raise RuntimeError(f"Embedding failed: {e}")

    # Allowed metadata keys — prevents pollution from untrusted input
    _ALLOWED_METADATA_KEYS = {
        "temporal_type", "valid_from", "valid_to", "entity_type", "entity_id",
        "source", "confidence", "category",
    }
    _MAX_TAGS = 20
    _MAX_TAG_LENGTH = 50
    _TAG_PATTERN = None  # Lazy compiled

    @staticmethod
    def _validate_tags(tags: str) -> str:
        """Validate tags: alphanumeric + underscore only, max 20 tags, max 50 chars each."""
        import re
        if not tags:
            return ""
        parts = [t.strip() for t in tags.split(",") if t.strip()]
        valid = []
        for tag in parts[:20]:  # max 20 tags
            tag = tag[:50]  # max 50 chars each
            if re.match(r'^[a-zA-Z0-9_\-]+$', tag):
                valid.append(tag)
        return ",".join(valid)

    async def store(self, text: str, tags: str = "", metadata: dict = None,
                    temporal_type: str = "", valid_from: float = 0.0, valid_to: float = 0.0,
                    entity_type: str = "", entity_id: str = "",
                    source: str = "internal"):
        """Store text with its embedding. Evicts oldest entries when exceeding MAX_MEMORY_ENTRIES.

        Args:
            source: Origin of the entry — "internal", "external", or "user".
        """
        # Validate tags
        tags = self._validate_tags(tags)

        # Validate source
        if source not in ("internal", "external", "user"):
            source = "internal"

        vector = await self.embed(text)

        # Filter metadata to allowed keys only
        safe_metadata = {}
        if metadata:
            for k, v in metadata.items():
                if k in self._ALLOWED_METADATA_KEYS:
                    safe_metadata[k] = v

        entry = {
            "text": text,
            "vector": vector,
            "tags": tags,
            "timestamp": time.time(),
            "source": source,
            "temporal_type": temporal_type,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "entity_type": entity_type,
            "entity_id": entity_id,
            **safe_metadata,
        }
        async with self._lock:
            self.entries.append(entry)
            # Evict oldest entries if over capacity
            if len(self.entries) > MAX_MEMORY_ENTRIES:
                evict_count = len(self.entries) - MAX_MEMORY_ENTRIES
                self.entries = self.entries[evict_count:]
                logger.info("Memory evicted %d oldest entries (now %d)", evict_count, len(self.entries))
                self._compact_persistence()
            self._rebuild_matrix()
            self._persist_entry(entry)
            return len(self.entries) - 1

    async def search(self, query: str, top_k: int = 5, temporal_filter: str = "") -> list[dict]:
        """Search memory by semantic similarity. Returns top_k results."""
        if not self.entries:
            return []

        query_vec = np.array(await self.embed(query), dtype=np.float32)
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)

        norms = np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-10
        normed = self.vectors / norms
        scores = normed @ query_norm

        k = min(top_k, len(self.entries))
        top_idx = np.argsort(scores)[-k:][::-1]

        results = []
        for i in top_idx:
            e = self.entries[i]
            results.append({
                "text": e["text"],
                "tags": e.get("tags", ""),
                "timestamp": e.get("timestamp", 0),
                "score": float(scores[i]),
            })
        if temporal_filter:
            results = [r for r in results if r.get("temporal_type", "") == temporal_filter]
        return results

    def _rebuild_matrix(self):
        """Rebuild numpy matrix from entries."""
        if self.entries:
            self.vectors = np.array(
                [e["vector"] for e in self.entries], dtype=np.float32
            )
        else:
            self.vectors = None

    def _persist_entry(self, entry: dict):
        """Append one entry to disk."""
        row = {
            "text": entry["text"],
            "vector": entry["vector"],
            "tags": entry.get("tags", ""),
            "timestamp": entry.get("timestamp", 0),
            "temporal_type": entry.get("temporal_type", ""),
            "valid_from": entry.get("valid_from", 0),
            "valid_to": entry.get("valid_to", 0),
            "entity_type": entry.get("entity_type", ""),
            "entity_id": entry.get("entity_id", ""),
        }
        with open(MEMORY_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")

    def _compact_persistence(self):
        """Rewrite the persistence file to match current in-memory entries (after eviction)."""
        try:
            tmp_path = MEMORY_PATH.with_suffix(".jsonl.tmp")
            with open(tmp_path, "w") as f:
                for entry in self.entries:
                    row = {
                        "text": entry["text"],
                        "vector": entry["vector"],
                        "tags": entry.get("tags", ""),
                        "timestamp": entry.get("timestamp", 0),
                        "temporal_type": entry.get("temporal_type", ""),
                        "valid_from": entry.get("valid_from", 0),
                        "valid_to": entry.get("valid_to", 0),
                        "entity_type": entry.get("entity_type", ""),
                        "entity_id": entry.get("entity_id", ""),
                    }
                    f.write(json.dumps(row) + "\n")
            tmp_path.replace(MEMORY_PATH)
            logger.info("Memory compacted to %d entries", len(self.entries))
        except Exception as e:
            logger.warning("Memory compaction failed: %s", e)

    def _load(self):
        """Load persisted memory from disk. Skips corrupt lines."""
        if not MEMORY_PATH.exists():
            return
        skipped = 0
        with open(MEMORY_PATH) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    self.entries.append(entry)
                except (json.JSONDecodeError, KeyError) as e:
                    skipped += 1
                    logger.warning("[Memory] Skipped corrupt entry at line %d: %s", line_num, e)
        if skipped:
            logger.warning("[Memory] Skipped %d corrupt entries during load", skipped)
        self._rebuild_matrix()

    def count(self) -> int:
        return len(self.entries)

    def clear(self):
        """Clear all memory."""
        self.entries = []
        self.vectors = None
        if MEMORY_PATH.exists():
            os.remove(MEMORY_PATH)
