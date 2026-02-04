"""
Episodic Memory — Vector-based semantic memory with adaptive importance.

Stores memories with embeddings, handles deduplication via entity tracking,
and maintains importance scores that adapt based on access patterns.
"""

import json
import logging
import time
from typing import Optional, Callable, Awaitable, List, Dict, Any

import numpy as np

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """Episodic memory with vector search and adaptive importance."""

    def __init__(self, db, embedder: Callable[[str], Awaitable[List[float]]] = None):
        """
        Initialize episodic memory.

        Args:
            db: Database connection
            embedder: Async function to generate embeddings.
                     Signature: async (text: str) -> List[float]
        """
        self.db = db
        self._embedder = embedder
        self._vector_dim: Optional[int] = None

    def set_embedder(self, embedder: Callable[[str], Awaitable[List[float]]]):
        """Set the embedder function after initialization."""
        self._embedder = embedder

    async def store(self, content: str, memory_type: str, domain: str = None,
                   project_id: str = None, entity_type: str = None,
                   entity_id: str = None, source: str = "internal",
                   importance: float = 0.5, session_id: str = None,
                   valid_from: float = None, metadata: dict = None) -> int:
        """
        Store a memory with embedding.

        Args:
            content: The memory content
            memory_type: Type of memory (interaction, fact, decision, outcome, observation, summary)
            domain: Domain area (engineering, health, communication, etc.)
            project_id: Associated project ID
            entity_type: For deduplication (e.g., "user_employer", "project_status")
            entity_id: For deduplication (e.g., "current", "sara-rover")
            source: Origin (internal, user, external, system)
            importance: Initial importance score (0-1)
            session_id: Associated session ID
            valid_from: When this fact becomes valid (default: now)
            metadata: Additional metadata dict

        Returns:
            Memory ID
        """
        # Generate embedding
        embedding_blob = None
        if self._embedder:
            try:
                embedding = await self._embedder(content)
                embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
                if self._vector_dim is None:
                    self._vector_dim = len(embedding)
            except Exception as e:
                logger.warning("Failed to generate embedding: %s", e)

        # Check for supersession
        supersedes_id = None
        if entity_type and entity_id:
            existing = self.db.execute("""
                SELECT id FROM memories
                WHERE entity_type = ? AND entity_id = ?
                AND superseded_by IS NULL AND valid_to IS NULL
            """, (entity_type, entity_id)).fetchone()

            if existing:
                supersedes_id = existing[0]

        # Build insert data
        data = {
            "content": content,
            "embedding": embedding_blob,
            "memory_type": memory_type,
            "domain": domain,
            "project_id": project_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "source": source,
            "importance": importance,
            "session_id": session_id,
            "valid_from": valid_from or time.time(),
        }

        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))

        self.db.execute(
            f"INSERT INTO memories ({columns}) VALUES ({placeholders})",
            tuple(data.values())
        )
        memory_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Mark superseded memory
        if supersedes_id:
            self.db.execute("""
                UPDATE memories SET
                    superseded_by = ?,
                    valid_to = unixepoch()
                WHERE id = ?
            """, (memory_id, supersedes_id))
            logger.debug("Memory %d supersedes %d", memory_id, supersedes_id)

        self.db.commit()
        return memory_id

    async def search(self, query: str, top_k: int = 10,
                    filters: Dict[str, Any] = None,
                    include_superseded: bool = False) -> List[Dict]:
        """
        Search memories by semantic similarity with optional filters.

        Args:
            query: Search query
            top_k: Maximum results to return
            filters: Optional filters dict with keys:
                - domain: Single domain string
                - domains: List of domains
                - memory_type: Single type string
                - memory_types: List of types
                - project_id: Project ID
                - min_importance: Minimum importance threshold
                - since: Timestamp - only memories after this time
            include_superseded: Include superseded memories

        Returns:
            List of memory dicts with scores
        """
        if not self._embedder:
            logger.warning("No embedder configured - cannot search")
            return []

        # Get query embedding
        try:
            query_embedding = np.array(
                await self._embedder(query),
                dtype=np.float32
            )
        except Exception as e:
            logger.error("Failed to embed query: %s", e)
            return []

        # Build filter clause
        where_clauses = []
        params = []

        if not include_superseded:
            where_clauses.append("superseded_by IS NULL")
            where_clauses.append("valid_to IS NULL")

        filters = filters or {}

        if filters.get("domain"):
            where_clauses.append("domain = ?")
            params.append(filters["domain"])
        elif filters.get("domains"):
            placeholders = ",".join("?" * len(filters["domains"]))
            where_clauses.append(f"domain IN ({placeholders})")
            params.extend(filters["domains"])

        if filters.get("memory_type"):
            where_clauses.append("memory_type = ?")
            params.append(filters["memory_type"])
        elif filters.get("memory_types"):
            placeholders = ",".join("?" * len(filters["memory_types"]))
            where_clauses.append(f"memory_type IN ({placeholders})")
            params.extend(filters["memory_types"])

        if filters.get("project_id"):
            where_clauses.append("project_id = ?")
            params.append(filters["project_id"])

        if filters.get("min_importance"):
            where_clauses.append("importance >= ?")
            params.append(filters["min_importance"])

        if filters.get("since"):
            where_clauses.append("created_at >= ?")
            params.append(filters["since"])

        # Always require embedding
        where_clauses.append("embedding IS NOT NULL")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Fetch candidates
        rows = self.db.execute(f"""
            SELECT id, content, embedding, memory_type, domain,
                   importance, created_at, project_id, source
            FROM memories
            WHERE {where_sql}
        """, params).fetchall()

        if not rows:
            return []

        # Compute similarities
        results = []
        for row in rows:
            mem_id, content, embedding_blob, mem_type, domain, \
                importance, created_at, project_id, source = row

            if not embedding_blob:
                continue

            mem_embedding = np.frombuffer(embedding_blob, dtype=np.float32)

            # Cosine similarity
            dot_product = np.dot(query_embedding, mem_embedding)
            norm_product = np.linalg.norm(query_embedding) * np.linalg.norm(mem_embedding)
            similarity = dot_product / (norm_product + 1e-10)

            # Combined score: similarity weighted with importance
            # Higher importance gives a boost to the similarity score
            score = similarity * 0.7 + importance * 0.3

            results.append({
                "id": mem_id,
                "content": content,
                "memory_type": mem_type,
                "domain": domain,
                "importance": importance,
                "similarity": float(similarity),
                "score": float(score),
                "created_at": created_at,
                "project_id": project_id,
                "source": source,
            })

        # Sort by combined score
        results.sort(key=lambda x: x["score"], reverse=True)

        # Record access for top results (boosts importance)
        for r in results[:top_k]:
            self._record_access(r["id"])

        return results[:top_k]

    def _record_access(self, memory_id: int):
        """Record access and boost importance."""
        self.db.execute("""
            UPDATE memories SET
                access_count = access_count + 1,
                last_accessed = unixepoch(),
                importance = MIN(0.95, importance + 0.03)
            WHERE id = ?
        """, (memory_id,))
        # Don't commit here - will be committed by caller

    async def search_by_entity(self, entity_type: str, entity_id: str = None) -> List[Dict]:
        """Search memories by entity type and optionally ID."""
        if entity_id:
            rows = self.db.execute("""
                SELECT id, content, memory_type, domain, importance, created_at
                FROM memories
                WHERE entity_type = ? AND entity_id = ?
                AND superseded_by IS NULL
                ORDER BY created_at DESC
            """, (entity_type, entity_id)).fetchall()
        else:
            rows = self.db.execute("""
                SELECT id, content, memory_type, domain, importance, created_at
                FROM memories
                WHERE entity_type = ?
                AND superseded_by IS NULL
                ORDER BY created_at DESC
            """, (entity_type,)).fetchall()

        return [
            {
                "id": r[0], "content": r[1], "memory_type": r[2],
                "domain": r[3], "importance": r[4], "created_at": r[5]
            }
            for r in rows
        ]

    async def get_recent(self, limit: int = 20, domain: str = None,
                        memory_type: str = None) -> List[Dict]:
        """Get recent memories."""
        where_clauses = ["superseded_by IS NULL"]
        params = []

        if domain:
            where_clauses.append("domain = ?")
            params.append(domain)
        if memory_type:
            where_clauses.append("memory_type = ?")
            params.append(memory_type)

        where_sql = " AND ".join(where_clauses)
        params.append(limit)

        rows = self.db.execute(f"""
            SELECT id, content, memory_type, domain, importance, created_at
            FROM memories
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
        """, params).fetchall()

        return [
            {
                "id": r[0], "content": r[1], "memory_type": r[2],
                "domain": r[3], "importance": r[4], "created_at": r[5]
            }
            for r in rows
        ]

    def decay_importance(self):
        """Decay importance of unaccessed memories. Call daily."""
        self.db.execute("""
            UPDATE memories SET
                importance = MAX(0.05, importance * 0.995)
            WHERE last_accessed < unixepoch() - 86400
            AND is_summary = 0
            AND importance > 0.05
        """)
        self.db.commit()

        decayed = self.db.execute("SELECT changes()").fetchone()[0]
        if decayed > 0:
            logger.info("Decayed importance of %d memories", decayed)

    async def consolidate(self, llm_client: Callable = None,
                         min_age_days: int = 30,
                         min_count: int = 5,
                         max_importance: float = 0.4):
        """
        Consolidate old low-importance memories into summaries.

        Args:
            llm_client: Async LLM function for summarization
            min_age_days: Only consolidate memories older than this
            min_count: Minimum memories to consolidate at once
            max_importance: Only consolidate memories below this importance
        """
        if not llm_client:
            logger.warning("No LLM client provided for consolidation")
            return

        # Find consolidation candidates grouped by domain
        candidates = self.db.execute("""
            SELECT domain, COUNT(*) as count FROM memories
            WHERE created_at < unixepoch() - (? * 86400)
            AND is_summary = 0
            AND superseded_by IS NULL
            AND importance < ?
            GROUP BY domain
            HAVING count >= ?
        """, (min_age_days, max_importance, min_count)).fetchall()

        for domain, count in candidates:
            await self._consolidate_domain(
                domain, min_age_days, max_importance, llm_client
            )

    async def _consolidate_domain(self, domain: str, min_age_days: int,
                                  max_importance: float,
                                  llm_client: Callable):
        """Consolidate memories for a specific domain."""
        memories = self.db.execute("""
            SELECT id, content, memory_type FROM memories
            WHERE domain = ?
            AND created_at < unixepoch() - (? * 86400)
            AND is_summary = 0
            AND superseded_by IS NULL
            AND importance < ?
            ORDER BY created_at
            LIMIT 20
        """, (domain, min_age_days, max_importance)).fetchall()

        if len(memories) < 5:
            return

        # Create summary using LLM
        content = "\n".join(f"- {m[1]}" for m in memories)

        try:
            summary = await llm_client(
                model="primary",
                messages=[{
                    "role": "user",
                    "content": f"""Summarize these {domain or 'general'} observations into key points.
Preserve important facts, patterns, and decisions. Be concise but complete.

Observations:
{content}

Summary:"""
                }]
            )
        except Exception as e:
            logger.error("Consolidation LLM call failed: %s", e)
            return

        # Store summary
        summary_id = await self.store(
            content=summary,
            memory_type="summary",
            domain=domain,
            importance=0.6,  # Summaries start moderately important
            source="consolidation"
        )

        # Mark original memories for potential eviction
        memory_ids = [m[0] for m in memories]
        placeholders = ",".join("?" * len(memory_ids))
        self.db.execute(f"""
            UPDATE memories SET importance = 0.02 WHERE id IN ({placeholders})
        """, memory_ids)

        # Record what was summarized
        self.db.execute("""
            UPDATE memories SET summarizes = ? WHERE id = ?
        """, (json.dumps(memory_ids), summary_id))

        self.db.commit()
        logger.info("Consolidated %d %s memories into summary %d",
                   len(memories), domain or "general", summary_id)

    def evict_low_importance(self, min_age_days: int = 90,
                            max_importance: float = 0.05,
                            keep_summaries: bool = True):
        """
        Permanently delete very low importance old memories.

        Args:
            min_age_days: Only evict memories older than this
            max_importance: Only evict memories below this importance
            keep_summaries: Never evict summary memories
        """
        where_clauses = [
            "created_at < unixepoch() - (? * 86400)",
            "importance < ?",
        ]
        params = [min_age_days, max_importance]

        if keep_summaries:
            where_clauses.append("is_summary = 0")

        where_sql = " AND ".join(where_clauses)

        self.db.execute(f"DELETE FROM memories WHERE {where_sql}", params)
        evicted = self.db.execute("SELECT changes()").fetchone()[0]
        self.db.commit()

        if evicted > 0:
            logger.info("Evicted %d low-importance memories", evicted)

    def count(self) -> int:
        """Count active (non-superseded) memories."""
        result = self.db.execute(
            "SELECT COUNT(*) FROM memories WHERE superseded_by IS NULL"
        ).fetchone()
        return result[0] if result else 0

    def stats(self) -> Dict:
        """Get memory statistics."""
        total = self.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        active = self.count()
        summaries = self.db.execute(
            "SELECT COUNT(*) FROM memories WHERE is_summary = 1"
        ).fetchone()[0]

        # By domain
        domain_rows = self.db.execute("""
            SELECT domain, COUNT(*) FROM memories
            WHERE superseded_by IS NULL
            GROUP BY domain
        """).fetchall()
        by_domain = {r[0] or "unspecified": r[1] for r in domain_rows}

        # By type
        type_rows = self.db.execute("""
            SELECT memory_type, COUNT(*) FROM memories
            WHERE superseded_by IS NULL
            GROUP BY memory_type
        """).fetchall()
        by_type = {r[0]: r[1] for r in type_rows}

        # Importance distribution
        importance_dist = {}
        for threshold, label in [(0.2, "low"), (0.5, "medium"), (0.8, "high"), (1.0, "very_high")]:
            prev = list(importance_dist.values())[-1] if importance_dist else 0
            count = self.db.execute("""
                SELECT COUNT(*) FROM memories
                WHERE superseded_by IS NULL AND importance <= ?
            """, (threshold,)).fetchone()[0]
            importance_dist[label] = count - sum(importance_dist.values())

        return {
            "total": total,
            "active": active,
            "superseded": total - active,
            "summaries": summaries,
            "by_domain": by_domain,
            "by_type": by_type,
            "importance_distribution": importance_dist,
        }

    def get_memory(self, memory_id: int) -> Optional[Dict]:
        """Get a specific memory by ID."""
        row = self.db.execute("""
            SELECT id, content, memory_type, domain, importance,
                   created_at, project_id, source, entity_type, entity_id,
                   is_summary, superseded_by
            FROM memories WHERE id = ?
        """, (memory_id,)).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "content": row[1],
            "memory_type": row[2],
            "domain": row[3],
            "importance": row[4],
            "created_at": row[5],
            "project_id": row[6],
            "source": row[7],
            "entity_type": row[8],
            "entity_id": row[9],
            "is_summary": bool(row[10]),
            "superseded_by": row[11],
        }

    def update_importance(self, memory_id: int, importance: float):
        """Manually update a memory's importance."""
        importance = max(0.0, min(1.0, importance))
        self.db.execute(
            "UPDATE memories SET importance = ? WHERE id = ?",
            (importance, memory_id)
        )
        self.db.commit()

    def supersede(self, old_id: int, new_content: str, **kwargs) -> int:
        """
        Create a new memory that supersedes an existing one.
        Useful for corrections or updates.
        """
        old = self.get_memory(old_id)
        if not old:
            raise ValueError(f"Memory {old_id} not found")

        # Inherit properties from old memory unless overridden
        new_kwargs = {
            "memory_type": old["memory_type"],
            "domain": old["domain"],
            "project_id": old["project_id"],
            "entity_type": old["entity_type"],
            "entity_id": old["entity_id"],
            "source": old["source"],
            "importance": max(old["importance"], 0.5),  # At least as important
        }
        new_kwargs.update(kwargs)

        # entity_type and entity_id will trigger automatic supersession
        return self.store(new_content, **new_kwargs)
