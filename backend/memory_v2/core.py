"""
Memory V2 Core — Main interface coordinating all memory components.

Provides a unified interface for:
- System awareness and resource monitoring
- User model management
- Episodic memory storage and retrieval
- Context building for prompts
- Maintenance tasks (decay, consolidation, cleanup)
"""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Optional, Callable, Awaitable, Dict, List, Any

from .system_awareness import SystemAwareness
from .user_model import UserModel
from .episodic import EpisodicMemory
from .context import ContextBuilder

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent / "memory_v2.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class MemoryV2:
    """
    Main Memory V2 interface.

    Coordinates system awareness, user model, episodic memory, and context building.
    Provides a unified API for the rest of Moose to interact with.
    """

    def __init__(self, db_path: str = None,
                 embedder: Callable[[str], Awaitable[List[float]]] = None,
                 llm_client: Callable[..., Awaitable[str]] = None,
                 inference_url: str = "http://localhost:1234"):
        """
        Initialize Memory V2.

        Args:
            db_path: Path to SQLite database (default: backend/memory_v2.db)
            embedder: Async function to generate embeddings
            llm_client: Async function to call LLM for extraction/summarization
            inference_url: URL of inference backend (for model queries)
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._embedder = embedder
        self._llm_client = llm_client
        self._inference_url = inference_url

        # Initialize database
        self._init_database()

        # Initialize components
        self.system = SystemAwareness(self.db)
        self.system.set_inference_url(inference_url)

        self.user_model = UserModel(self.db, llm_client)
        self.memory = EpisodicMemory(self.db, embedder)
        self.context = ContextBuilder(self.db, self.user_model, self.memory, self.system)

        # Maintenance task handle
        self._maintenance_task: Optional[asyncio.Task] = None
        self._running = False

    def _init_database(self):
        """Initialize SQLite database with schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row

        # Enable foreign keys
        self.db.execute("PRAGMA foreign_keys = ON")

        # Load and execute schema
        if SCHEMA_PATH.exists():
            schema = SCHEMA_PATH.read_text()
            self.db.executescript(schema)
            self.db.commit()
            logger.debug("Database schema initialized")
        else:
            logger.warning("Schema file not found: %s", SCHEMA_PATH)

    def set_embedder(self, embedder: Callable[[str], Awaitable[List[float]]]):
        """Set the embedder function (can be set after init)."""
        self._embedder = embedder
        self.memory.set_embedder(embedder)

    def set_llm_client(self, llm_client: Callable[..., Awaitable[str]]):
        """Set the LLM client function (can be set after init)."""
        self._llm_client = llm_client
        self.user_model.set_llm_client(llm_client)

    async def start(self):
        """
        Start Memory V2 system.

        - Detects hardware
        - Starts resource monitoring
        - Starts maintenance loop
        """
        self._running = True

        # Detect hardware
        profile = self.system.detect_hardware()
        logger.info(
            "Memory V2 started: %s, %.1fGB RAM, context budget: %d tokens",
            profile.get("cpu_model", "Unknown")[:30],
            profile.get("ram_total_gb", 0),
            profile.get("recommended_context_tokens", 8000)
        )

        # Start maintenance loop
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

        return profile

    async def stop(self):
        """Stop Memory V2 system."""
        self._running = False

        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass

        self.db.close()
        logger.info("Memory V2 stopped")

    async def _maintenance_loop(self):
        """Background maintenance tasks."""
        # Initial delay
        await asyncio.sleep(60)

        cycle = 0
        while self._running:
            try:
                cycle += 1

                # Resource snapshot every cycle (1 min)
                self.system.snapshot_resources()

                # Process inventory every 5 cycles
                if cycle % 5 == 0:
                    self.system.inventory_processes()

                # Process extraction queue every 2 cycles
                if cycle % 2 == 0 and self._llm_client:
                    await self.user_model.process_extraction_queue(batch_size=3)

                # Importance decay daily (every ~1440 cycles at 1 min interval)
                # Check every 60 cycles (~1 hour) but only decay once per day
                if cycle % 60 == 0:
                    self.memory.decay_importance()

                # Consolidation weekly (check every 360 cycles, ~6 hours)
                if cycle % 360 == 0 and self._llm_client:
                    await self.memory.consolidate(
                        llm_client=self._llm_client,
                        min_age_days=30,
                        min_count=10
                    )

                # Session cleanup daily
                if cycle % 1440 == 0:
                    self.context.cleanup_old_sessions(max_age_days=7)

                # Evict very old low-importance memories monthly
                if cycle % 43200 == 0:  # ~30 days
                    self.memory.evict_low_importance(
                        min_age_days=90,
                        max_importance=0.05
                    )

                await asyncio.sleep(60)  # 1 minute cycles

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Maintenance loop error: %s", e, exc_info=True)
                await asyncio.sleep(60)

    # ========================================================================
    # Main API
    # ========================================================================

    async def process_interaction(self, user_msg: str, assistant_msg: str,
                                  session_id: str = None,
                                  context: Dict = None):
        """
        Process a completed interaction.

        - Learns from the interaction (user model)
        - Stores in episodic memory
        - Updates session

        Call this after every user<->assistant exchange.
        """
        # Learn from interaction (identity, preferences, projects)
        await self.user_model.learn_from_interaction(
            user_msg, assistant_msg, context
        )

        # Store interaction in episodic memory
        summary = f"User: {user_msg[:200]}\nAssistant: {assistant_msg[:300]}"
        await self.memory.store(
            content=summary,
            memory_type="interaction",
            session_id=session_id,
            source="internal"
        )

        # Update session if provided
        if session_id:
            self.context.add_message(session_id, "user", user_msg)
            self.context.add_message(session_id, "assistant", assistant_msg)

    async def build_context(self, query: str, session_id: str = None,
                           project_id: str = None) -> Dict:
        """
        Build context for a query.

        Returns dict with:
            - context: Full context string for system prompt
            - tokens: Token counts by tier
            - budget_info: Budget allocation details
        """
        return await self.context.build_context(query, session_id, project_id)

    async def store_memory(self, content: str, memory_type: str,
                          domain: str = None, **kwargs) -> int:
        """Store a memory. Returns memory ID."""
        return await self.memory.store(
            content=content,
            memory_type=memory_type,
            domain=domain,
            **kwargs
        )

    async def search_memory(self, query: str, top_k: int = 10,
                           filters: Dict = None) -> List[Dict]:
        """Search memories by semantic similarity."""
        return await self.memory.search(query, top_k, filters)

    async def store_fact(self, content: str, entity_type: str = None,
                        entity_id: str = None, domain: str = None,
                        importance: float = 0.6) -> int:
        """
        Store a durable fact.

        If entity_type and entity_id are provided, will automatically
        supersede any existing fact with the same entity.
        """
        return await self.memory.store(
            content=content,
            memory_type="fact",
            domain=domain,
            entity_type=entity_type,
            entity_id=entity_id,
            importance=importance,
            source="user"
        )

    async def store_decision(self, content: str, project_id: str = None,
                            domain: str = None) -> int:
        """Store a decision for future reference."""
        return await self.memory.store(
            content=content,
            memory_type="decision",
            domain=domain,
            project_id=project_id,
            importance=0.7,
            source="internal"
        )

    async def store_debug_solution(self, symptom: str, solution: str,
                                   root_cause: str = None,
                                   domain: str = None,
                                   project_id: str = None,
                                   worked: bool = True):
        """Store a debug solution for future reference."""
        self.db.execute("""
            INSERT INTO debug_history
            (symptom, solution, root_cause, domain, project_id, worked)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symptom, solution, root_cause, domain, project_id, int(worked)))
        self.db.commit()

        # Also store in episodic memory for semantic search
        content = f"Debug: {symptom} -> {solution}"
        if root_cause:
            content += f" (cause: {root_cause})"

        await self.memory.store(
            content=content,
            memory_type="outcome",
            domain=domain,
            project_id=project_id,
            importance=0.7 if worked else 0.4
        )

    # ========================================================================
    # Session Management
    # ========================================================================

    def create_session(self, session_id: str = None) -> str:
        """Create a new session."""
        return self.context.create_session(session_id)

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session info."""
        return self.context.get_session(session_id)

    def set_session_project(self, session_id: str, project_id: str):
        """Set the active project for a session."""
        self.context.set_session_project(session_id, project_id)

    def end_session(self, session_id: str):
        """End a session."""
        self.context.end_session(session_id)

    # ========================================================================
    # User Model Access
    # ========================================================================

    def get_user_identity(self) -> Optional[Dict]:
        """Get current user identity."""
        return self.user_model.get_identity()

    def get_user_preferences(self, domain: str = None) -> List[Dict]:
        """Get user preferences."""
        return self.user_model.get_preferences(domain)

    def set_user_preference(self, domain: str, key: str, value: str):
        """Explicitly set a user preference."""
        self.user_model.set_preference(domain, key, value)

    def set_user_identity(self, field: str, value: str):
        """Explicitly set a user identity field."""
        self.user_model.set_identity_field(field, value)

    def get_active_projects(self) -> List[Dict]:
        """Get active projects."""
        return self.user_model.get_active_projects()

    # ========================================================================
    # System Info
    # ========================================================================

    def get_system_profile(self) -> Optional[Dict]:
        """Get system hardware profile."""
        return self.system.get_profile()

    def get_resource_summary(self) -> Dict:
        """Get current resource summary."""
        return self.system.get_resource_summary()

    def get_context_budget(self) -> Dict:
        """Get current context budget."""
        return self.system.get_adaptive_context_budget()

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self) -> Dict:
        """Get overall memory statistics."""
        memory_stats = self.memory.stats()
        system_profile = self.system.get_profile() or {}
        budget = self.system.get_adaptive_context_budget()

        # Count other entities
        identity = self.user_model.get_identity()
        prefs_count = len(self.user_model.get_preferences())
        projects_count = len(self.user_model.get_active_projects())

        # Pattern count
        patterns_count = self.db.execute(
            "SELECT COUNT(*) FROM patterns WHERE active = 1"
        ).fetchone()[0]

        # Extraction queue
        pending_extractions = self.db.execute(
            "SELECT COUNT(*) FROM extraction_queue WHERE status = 'pending'"
        ).fetchone()[0]

        return {
            "memory": memory_stats,
            "user": {
                "identity_established": identity is not None and identity.get("name"),
                "preferences_count": prefs_count,
                "projects_count": projects_count,
                "patterns_count": patterns_count,
            },
            "system": {
                "cpu": system_profile.get("cpu_model", "Unknown"),
                "ram_gb": system_profile.get("ram_total_gb", 0),
                "gpu": system_profile.get("gpu_model"),
                "context_budget": budget["total"],
            },
            "queue": {
                "pending_extractions": pending_extractions,
            },
        }

    # ========================================================================
    # Project Knowledge
    # ========================================================================

    async def store_project_knowledge(self, project_id: str, content: str,
                                      knowledge_type: str,
                                      file_path: str = None,
                                      importance: float = 0.5) -> int:
        """Store project-specific knowledge."""
        self.db.execute("""
            INSERT INTO project_knowledge
            (project_id, content, knowledge_type, file_path, importance)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, content, knowledge_type, file_path, importance))
        self.db.commit()
        return self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_project_knowledge(self, project_id: str,
                             knowledge_type: str = None) -> List[Dict]:
        """Get knowledge for a project."""
        if knowledge_type:
            rows = self.db.execute("""
                SELECT id, content, knowledge_type, file_path, importance, created_at
                FROM project_knowledge
                WHERE project_id = ? AND knowledge_type = ? AND valid_to IS NULL
                ORDER BY importance DESC
            """, (project_id, knowledge_type)).fetchall()
        else:
            rows = self.db.execute("""
                SELECT id, content, knowledge_type, file_path, importance, created_at
                FROM project_knowledge
                WHERE project_id = ? AND valid_to IS NULL
                ORDER BY importance DESC
            """, (project_id,)).fetchall()

        return [
            {
                "id": r[0], "content": r[1], "knowledge_type": r[2],
                "file_path": r[3], "importance": r[4], "created_at": r[5]
            }
            for r in rows
        ]

    # ========================================================================
    # Patterns
    # ========================================================================

    def store_pattern(self, pattern_type: str, description: str,
                     confidence: float = 0.5) -> int:
        """Store an observed pattern."""
        # Check for similar existing pattern
        existing = self.db.execute("""
            SELECT id, evidence_count, confidence FROM patterns
            WHERE pattern_type = ? AND active = 1
            AND description LIKE ?
        """, (pattern_type, f"%{description[:50]}%")).fetchone()

        if existing:
            # Strengthen existing pattern
            self.db.execute("""
                UPDATE patterns SET
                    evidence_count = evidence_count + 1,
                    confidence = MIN(0.95, confidence + 0.05),
                    last_observed = unixepoch()
                WHERE id = ?
            """, (existing[0],))
            self.db.commit()
            return existing[0]

        # New pattern
        self.db.execute("""
            INSERT INTO patterns (pattern_type, description, confidence)
            VALUES (?, ?, ?)
        """, (pattern_type, description, confidence))
        self.db.commit()
        return self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_patterns(self, pattern_type: str = None,
                    min_confidence: float = 0.5) -> List[Dict]:
        """Get observed patterns."""
        if pattern_type:
            rows = self.db.execute("""
                SELECT id, pattern_type, description, confidence, evidence_count
                FROM patterns
                WHERE active = 1 AND pattern_type = ? AND confidence >= ?
                ORDER BY confidence DESC
            """, (pattern_type, min_confidence)).fetchall()
        else:
            rows = self.db.execute("""
                SELECT id, pattern_type, description, confidence, evidence_count
                FROM patterns
                WHERE active = 1 AND confidence >= ?
                ORDER BY confidence DESC
            """, (min_confidence,)).fetchall()

        return [
            {
                "id": r[0], "pattern_type": r[1], "description": r[2],
                "confidence": r[3], "evidence_count": r[4]
            }
            for r in rows
        ]
