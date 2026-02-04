"""
Context Builder — Assembles tiered context for prompts.

Builds context from:
1. Core identity (~500 tokens, always included)
2. Session context (current conversation)
3. Retrieved context (relevant memories for this query)

Total context is bounded by adaptive budget based on system resources.
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Assembles tiered context for prompts."""

    def __init__(self, db, user_model, episodic_memory, system_awareness):
        """
        Initialize context builder.

        Args:
            db: Database connection
            user_model: UserModel instance
            episodic_memory: EpisodicMemory instance
            system_awareness: SystemAwareness instance
        """
        self.db = db
        self.user_model = user_model
        self.memory = episodic_memory
        self.system = system_awareness

    async def build_context(self, query: str, session_id: str = None,
                           project_id: str = None) -> Dict:
        """
        Build complete context for a query.

        Args:
            query: The user's query
            session_id: Current session ID (optional)
            project_id: Override project ID (optional)

        Returns:
            Dict with:
                - context: Full context string
                - tokens: Token counts by tier
                - budget_info: Budget allocation details
        """
        # Get adaptive budget based on current resources
        budget = self.system.get_adaptive_context_budget()

        # Tier 1: Core identity (always included)
        core = self.user_model.get_core_context()
        core_tokens = self._count_tokens(core)

        # Tier 2: Session context
        session = ""
        session_project_id = None
        if session_id:
            session, session_project_id = self._build_session_context(
                session_id, budget["session"]
            )
        session_tokens = self._count_tokens(session)

        # Determine active project
        active_project_id = project_id or session_project_id

        # Tier 3: Retrieved context
        # Adjust budget based on what core and session used
        core_overage = max(0, core_tokens - budget["core"])
        remaining_budget = budget["retrieved"] - core_overage

        retrieved = await self._retrieve_context(
            query,
            session_id=session_id,
            project_id=active_project_id,
            max_tokens=remaining_budget
        )
        retrieved_tokens = self._count_tokens(retrieved)

        # Assemble full context
        parts = []
        if core:
            parts.append(core)
        if session:
            parts.append(session)
        if retrieved:
            parts.append(retrieved)

        full_context = "\n\n".join(parts)

        total_tokens = core_tokens + session_tokens + retrieved_tokens

        return {
            "context": full_context,
            "tokens": {
                "core": core_tokens,
                "session": session_tokens,
                "retrieved": retrieved_tokens,
                "total": total_tokens,
                "budget": budget["total"],
            },
            "budget_info": budget,
            "active_project_id": active_project_id,
        }

    def _build_session_context(self, session_id: str, max_tokens: int) -> tuple:
        """
        Build context from current session.

        Returns:
            Tuple of (context_string, active_project_id)
        """
        session = self.db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

        if not session:
            return "", None

        # Get column names
        columns = [desc[0] for desc in self.db.execute(
            "SELECT * FROM sessions LIMIT 0"
        ).description]
        session_dict = dict(zip(columns, session))

        parts = []
        active_project_id = session_dict.get("active_project_id")

        # Session summary if available
        if session_dict.get("summary"):
            parts.append(f"## Conversation So Far\n{session_dict['summary']}")

        # Active project context
        if active_project_id:
            project_ctx = self._get_project_context(active_project_id)
            if project_ctx:
                parts.append(f"## Active Project\n{project_ctx}")

        # Recent messages
        messages = self.db.execute("""
            SELECT role, content FROM session_messages
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """, (session_id,)).fetchall()

        if messages:
            parts.append("## Recent Exchange")
            for role, content in reversed(messages):
                # Truncate very long messages
                truncated = content[:500] + "..." if len(content) > 500 else content
                parts.append(f"**{role}**: {truncated}")

        # Build context respecting budget
        context = "\n\n".join(parts)

        # If over budget, remove parts from the beginning (less important)
        while self._count_tokens(context) > max_tokens and len(parts) > 1:
            parts.pop(0)
            context = "\n\n".join(parts)

        return context, active_project_id

    async def _retrieve_context(self, query: str, session_id: str = None,
                                project_id: str = None,
                                max_tokens: int = 4000) -> str:
        """Retrieve relevant context for query."""
        parts = []
        token_count = 0

        # 1. Detect domains in query
        domains = self._classify_domains(query)

        # 2. Vector search for similar memories
        try:
            memories = await self.memory.search(
                query,
                top_k=15,
                filters={"domains": domains} if domains else None
            )

            if memories:
                memory_parts = ["## Relevant Context"]
                for mem in memories:
                    content = f"- [{mem['memory_type']}] {mem['content']}"
                    content_tokens = self._count_tokens(content)
                    if token_count + content_tokens > max_tokens * 0.5:
                        break
                    memory_parts.append(content)
                    token_count += content_tokens

                if len(memory_parts) > 1:
                    parts.append("\n".join(memory_parts))
        except Exception as e:
            logger.warning("Memory search failed: %s", e)

        # 3. Project-specific knowledge
        if project_id:
            project_knowledge = self.db.execute("""
                SELECT content, knowledge_type FROM project_knowledge
                WHERE project_id = ? AND valid_to IS NULL
                ORDER BY importance DESC LIMIT 5
            """, (project_id,)).fetchall()

            if project_knowledge:
                pk_parts = ["\n## Project Knowledge"]
                for content, knowledge_type in project_knowledge:
                    line = f"- [{knowledge_type}] {content}"
                    line_tokens = self._count_tokens(line)
                    if token_count + line_tokens > max_tokens * 0.7:
                        break
                    pk_parts.append(line)
                    token_count += line_tokens

                if len(pk_parts) > 1:
                    parts.append("\n".join(pk_parts))

            # Debug history for this project's domain
            project = self.db.execute(
                "SELECT domain FROM projects WHERE id = ?", (project_id,)
            ).fetchone()

            if project and project[0]:
                debug_history = self.db.execute("""
                    SELECT symptom, solution FROM debug_history
                    WHERE domain = ? AND worked = 1
                    ORDER BY created_at DESC LIMIT 3
                """, (project[0],)).fetchall()

                if debug_history:
                    dh_parts = ["\n## Past Solutions"]
                    for symptom, solution in debug_history:
                        line = f"- {symptom}: {solution}"
                        line_tokens = self._count_tokens(line)
                        if token_count + line_tokens > max_tokens * 0.85:
                            break
                        dh_parts.append(line)
                        token_count += line_tokens

                    if len(dh_parts) > 1:
                        parts.append("\n".join(dh_parts))

        # 4. Relevant patterns
        patterns = self.db.execute("""
            SELECT description, pattern_type FROM patterns
            WHERE active = 1 AND confidence > 0.5
            ORDER BY confidence DESC LIMIT 5
        """).fetchall()

        if patterns:
            pattern_parts = ["\n## Known Patterns"]
            for description, pattern_type in patterns:
                line = f"- [{pattern_type}] {description}"
                line_tokens = self._count_tokens(line)
                if token_count + line_tokens > max_tokens:
                    break
                pattern_parts.append(line)
                token_count += line_tokens

            if len(pattern_parts) > 1:
                parts.append("\n".join(pattern_parts))

        # 5. Tool preferences if engineering domain
        if "engineering" in domains or "code" in domains:
            tools = self.db.execute("""
                SELECT category, tool FROM tool_preferences
                ORDER BY confidence DESC LIMIT 5
            """).fetchall()

            if tools:
                tool_parts = ["\n## Tool Preferences"]
                for category, tool in tools:
                    tool_parts.append(f"- {category}: {tool}")
                parts.append("\n".join(tool_parts))

        return "\n".join(parts)

    def _classify_domains(self, query: str) -> List[str]:
        """Classify which domains a query relates to."""
        query_lower = query.lower()

        domain_keywords = {
            "engineering": [
                "code", "bug", "error", "function", "class", "api", "build",
                "compile", "test", "debug", "fix", "implement", "refactor"
            ],
            "robotics": [
                "ros", "robot", "sensor", "motor", "actuator", "slam",
                "navigation", "lidar", "imu", "odometry", "urdf"
            ],
            "embedded": [
                "arduino", "esp32", "stm32", "firmware", "microcontroller",
                "gpio", "uart", "spi", "i2c", "pwm", "interrupt"
            ],
            "web": [
                "http", "api", "endpoint", "frontend", "backend", "database",
                "react", "vue", "node", "django", "fastapi"
            ],
            "ml": [
                "model", "training", "neural", "tensor", "pytorch", "tensorflow",
                "dataset", "inference", "embedding", "transformer"
            ],
            "health": [
                "sleep", "exercise", "energy", "tired", "health", "workout",
                "calories", "steps", "heart rate"
            ],
            "communication": [
                "email", "message", "write", "draft", "respond", "reply",
                "meeting", "schedule", "calendar"
            ],
        }

        domains = []
        for domain, keywords in domain_keywords.items():
            if any(kw in query_lower for kw in keywords):
                domains.append(domain)

        return domains or ["general"]

    def _get_project_context(self, project_id: str) -> str:
        """Get context for a specific project."""
        project = self.db.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()

        if not project:
            return ""

        columns = [desc[0] for desc in self.db.execute(
            "SELECT * FROM projects LIMIT 0"
        ).description]
        project_dict = dict(zip(columns, project))

        lines = [f"**{project_dict['name']}**"]

        if project_dict.get("description"):
            lines.append(project_dict["description"][:200])

        if project_dict.get("domain"):
            lines.append(f"Domain: {project_dict['domain']}")

        if project_dict.get("languages"):
            try:
                languages = json.loads(project_dict["languages"])
                if languages:
                    lines.append(f"Languages: {', '.join(languages)}")
            except Exception:
                pass

        if project_dict.get("frameworks"):
            try:
                frameworks = json.loads(project_dict["frameworks"])
                if frameworks:
                    lines.append(f"Frameworks: {', '.join(frameworks)}")
            except Exception:
                pass

        if project_dict.get("build_system"):
            lines.append(f"Build: {project_dict['build_system']}")

        return "\n".join(lines)

    def _count_tokens(self, text: str) -> int:
        """Estimate token count. ~4 chars per token for English."""
        if not text:
            return 0
        return len(text) // 4

    # ========================================================================
    # Session Management
    # ========================================================================

    def create_session(self, session_id: str = None) -> str:
        """Create a new session."""
        import uuid
        session_id = session_id or str(uuid.uuid4())[:12]

        self.db.execute(
            "INSERT INTO sessions (id) VALUES (?)",
            (session_id,)
        )
        self.db.commit()
        return session_id

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to a session."""
        self.db.execute("""
            INSERT INTO session_messages (session_id, role, content)
            VALUES (?, ?, ?)
        """, (session_id, role, content))

        self.db.execute("""
            UPDATE sessions SET
                last_message_at = unixepoch(),
                message_count = message_count + 1
            WHERE id = ?
        """, (session_id,))

        self.db.commit()

    def set_session_project(self, session_id: str, project_id: str):
        """Set the active project for a session."""
        self.db.execute("""
            UPDATE sessions SET active_project_id = ? WHERE id = ?
        """, (project_id, session_id))
        self.db.commit()

    async def update_session_summary(self, session_id: str,
                                     llm_client=None,
                                     max_messages: int = 20):
        """
        Update session summary using LLM.
        Call periodically when conversation gets long.
        """
        if not llm_client:
            return

        messages = self.db.execute("""
            SELECT role, content FROM session_messages
            WHERE session_id = ?
            ORDER BY timestamp
            LIMIT ?
        """, (session_id, max_messages)).fetchall()

        if len(messages) < 5:
            return

        # Get existing summary
        existing = self.db.execute(
            "SELECT summary FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        existing_summary = existing[0] if existing else ""

        # Build conversation text
        conv_text = "\n".join(f"{role}: {content[:200]}" for role, content in messages)

        prompt = f"""Summarize this conversation concisely, preserving key decisions, requests, and context.

{"Previous summary: " + existing_summary if existing_summary else ""}

Conversation:
{conv_text}

Summary (2-3 sentences):"""

        try:
            summary = await llm_client(
                model="classifier",
                messages=[{"role": "user", "content": prompt}]
            )

            self.db.execute(
                "UPDATE sessions SET summary = ? WHERE id = ?",
                (summary.strip(), session_id)
            )
            self.db.commit()
        except Exception as e:
            logger.warning("Failed to update session summary: %s", e)

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session info."""
        row = self.db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

        if not row:
            return None

        columns = [desc[0] for desc in self.db.execute(
            "SELECT * FROM sessions LIMIT 0"
        ).description]
        return dict(zip(columns, row))

    def end_session(self, session_id: str):
        """Mark a session as ended."""
        self.db.execute("""
            UPDATE sessions SET ended_at = unixepoch() WHERE id = ?
        """, (session_id,))
        self.db.commit()

    def cleanup_old_sessions(self, max_age_days: int = 7):
        """Clean up old session messages (keep session records)."""
        # Delete old messages
        self.db.execute("""
            DELETE FROM session_messages
            WHERE session_id IN (
                SELECT id FROM sessions
                WHERE ended_at IS NOT NULL
                AND ended_at < unixepoch() - (? * 86400)
            )
        """, (max_age_days,))

        deleted = self.db.execute("SELECT changes()").fetchone()[0]
        self.db.commit()

        if deleted > 0:
            logger.info("Cleaned up %d old session messages", deleted)
