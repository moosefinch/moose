"""
MarketingEngine — cadence-based autonomous marketing loops.
Wraps OutreachEngine (composition). Checks marketing_cadence table every 60s
and dispatches due loops as background tasks.

All cadences disabled by default — user enables when ready.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Optional

from db import db_connection_row
from outreach_engine import OutreachEngine, get_outreach_engine

logger = logging.getLogger(__name__)

# Rate limits (per hour)
_MAX_EMAILS_PER_HOUR = 20
_MAX_CONTENT_PER_HOUR = 10
_MAX_PROSPECTS_PER_HOUR = 15

# Cadence loop task descriptions
_CADENCE_TASKS = {
    "content": "Generate 1 blog post and 2-3 social posts (Twitter/X + Moltbook) targeting ICP personas. Use list_personas() to select target persona, then draft_content() to store each piece. Match content to persona pain points.",
    "prospect_research": "Research 3-5 new prospects matching ICP personas. Use list_personas() to understand target profiles, then web_search to find matching individuals/firms. Use add_prospect() and research_company() to store findings.",
    "email_draft": "Draft personalized emails for researched prospects that don't have outreach yet. Use match_prospect_to_persona() and get_persona() before drafting. Store as pending via draft_email(). Keep emails peer-to-peer, 2-4 sentences, first-name basis.",
    "follow_up": "Check for follow-ups due using get_next_actions(). Draft follow-up emails for any that are overdue. Keep follow-ups shorter than initial emails — 1-2 sentences, reference the original.",
    "social_post": "Generate 2-3 Twitter/X posts (280 char max, provocative observations, no hashtags) and 1-2 Moltbook posts (posting security research, breach analysis, privacy comparisons). Use draft_content() with appropriate content_type and platform.",
}


def _gen_id(prefix=""):
    return prefix + hashlib.sha256(f"{prefix}{time.time()}".encode()).hexdigest()[:12]


class MarketingEngine:
    """Cadence-based marketing automation that wraps OutreachEngine."""

    def __init__(self, check_interval: float = 60.0):
        self.check_interval = check_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._ws_broadcast = None
        self._task_creator = None
        self.outreach_engine = get_outreach_engine()

        # Cognitive context — updated by cognitive loop each cycle
        self._cognitive_context: Optional[str] = None

        # Rate limit tracking (timestamps of recent actions per type)
        self._rate_counters: dict[str, list[float]] = {
            "email": [],
            "content": [],
            "prospect": [],
        }

    def set_ws_broadcast(self, callback):
        self._ws_broadcast = callback
        self.outreach_engine.set_ws_broadcast(callback)

    def set_task_creator(self, callback):
        self._task_creator = callback
        self.outreach_engine.set_task_creator(callback)

    async def start(self):
        """Start both the marketing engine and the underlying outreach engine."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        await self.outreach_engine.start()
        logger.info("[MarketingEngine] Started (check interval: %ds)", self.check_interval)

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.outreach_engine.stop()
        logger.info("[MarketingEngine] Stopped")

    def _check_rate_limit(self, action_type: str, max_per_hour: int) -> bool:
        """Check if we're within rate limits for a given action type."""
        now = time.time()
        hour_ago = now - 3600
        timestamps = self._rate_counters.get(action_type, [])
        # Clean old entries
        timestamps = [t for t in timestamps if t > hour_ago]
        self._rate_counters[action_type] = timestamps
        return len(timestamps) < max_per_hour

    def _record_rate(self, action_type: str):
        """Record an action for rate limiting."""
        self._rate_counters.setdefault(action_type, []).append(time.time())

    async def _run_loop(self):
        """Main loop — checks cadence table for due loops every check_interval seconds."""
        while self.running:
            try:
                await self._check_cadences()
            except Exception as e:
                logger.error("[MarketingEngine] Error in cadence check: %s", e)
            await asyncio.sleep(self.check_interval)

    async def _check_cadences(self):
        """Query marketing_cadence table for enabled cadences that are due."""
        now = time.time()
        with db_connection_row() as conn:
            due = conn.execute(
                "SELECT * FROM marketing_cadence WHERE enabled = 1 AND (next_run IS NULL OR next_run <= ?)",
                (now,)
            ).fetchall()

        for cadence in due:
            loop_type = cadence["loop_type"]
            task_desc = _CADENCE_TASKS.get(loop_type)
            if not task_desc:
                logger.warning("[MarketingEngine] Unknown loop_type: %s", loop_type)
                continue

            # Check rate limits
            rate_type = self._get_rate_type(loop_type)
            rate_limit = self._get_rate_limit(loop_type)
            if not self._check_rate_limit(rate_type, rate_limit):
                logger.info("[MarketingEngine] Rate limited: %s (%s/hr)", loop_type, rate_type)
                continue

            # Create background task with cognitive context
            if self._task_creator:
                try:
                    desc = f"[Marketing/{loop_type}] {task_desc}"
                    if self._cognitive_context:
                        desc += f"\n\nCognitive context: {self._cognitive_context}"
                    await self._task_creator(desc)
                    self._record_rate(rate_type)
                    logger.info("[MarketingEngine] Dispatched cadence: %s", loop_type)
                except Exception as e:
                    logger.error("[MarketingEngine] Failed to create task for %s: %s", loop_type, e)
                    continue

            # Update next_run
            interval = cadence["interval_seconds"]
            next_run = now + interval
            with db_connection_row() as conn:
                conn.execute(
                    "UPDATE marketing_cadence SET last_run = ?, next_run = ?, updated_at = ? WHERE id = ?",
                    (now, next_run, now, cadence["id"])
                )
                conn.commit()

            # Broadcast notification
            if self._ws_broadcast:
                await self._ws_broadcast({
                    "type": "marketing_notification",
                    "loop_type": loop_type,
                    "message": f"Marketing cadence triggered: {loop_type}",
                })

    def _get_rate_type(self, loop_type: str) -> str:
        """Map loop type to rate limit category."""
        mapping = {
            "content": "content",
            "social_post": "content",
            "prospect_research": "prospect",
            "email_draft": "email",
            "follow_up": "email",
        }
        return mapping.get(loop_type, "content")

    def _get_rate_limit(self, loop_type: str) -> int:
        """Get hourly rate limit for a loop type."""
        rate_type = self._get_rate_type(loop_type)
        limits = {
            "email": _MAX_EMAILS_PER_HOUR,
            "content": _MAX_CONTENT_PER_HOUR,
            "prospect": _MAX_PROSPECTS_PER_HOUR,
        }
        return limits.get(rate_type, 10)

    def set_cognitive_context(self, context: str):
        """Update cognitive context from the cognitive loop.

        Called by CognitiveLoop during the ACT phase to pass current insights
        so cadence tasks are dispatched with relevant context.
        """
        self._cognitive_context = context

    async def handle_inbound_lead(self, lead_data: dict):
        """Delegate inbound leads to the outreach engine."""
        await self.outreach_engine.handle_inbound_lead(lead_data)


_engine: Optional[MarketingEngine] = None


def get_marketing_engine() -> MarketingEngine:
    global _engine
    if _engine is None:
        _engine = MarketingEngine()
    return _engine
