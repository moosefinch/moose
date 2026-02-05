"""
CognitiveLoop — OODA-based always-on background process.

Drives the agent system: observes events from all subsystems,
orients by identifying patterns and content angles, decides on actions,
and acts by dispatching content drafts, outreach emails, voice alerts,
and memory entries.

Runs as an asyncio task from AgentCore.start().
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from db import db_connection_row

logger = logging.getLogger(__name__)


class CognitiveLoop:
    """Always-on OODA cognitive loop — the brain of the agent system."""

    _MAX_THOUGHT_JOURNAL = 500     # Cap thought journal to prevent unbounded growth
    _MAX_CONTENT_ANGLES = 100      # Cap content angles
    _MAX_MEMORY_WRITES_PER_DAY = 50  # Cap memory writes to avoid polluting search

    def __init__(self, core):
        self._core = core
        self.cycle_interval = 120       # seconds between cycles (2 min default)
        self.min_interval = 30          # accelerate when events are hot
        self.running = False
        self.cycle_count = 0
        self.observations: list[dict] = []
        self.thought_journal: list[dict] = []
        self.content_angles: list[dict] = []
        self._last_observation_time = 0.0
        self._last_reflection_time = 0.0
        self._reflection_every_n = 10   # reflect every N cycles
        self._morning_briefing_hour = 9
        self._evening_briefing_hour = 18
        self._last_briefing_date: Optional[str] = None
        self._last_briefing_type: Optional[str] = None
        self._phase = "idle"             # idle, observe, orient, decide, act
        self._task: Optional[asyncio.Task] = None
        self._memory_writes_today = 0
        self._memory_writes_reset_date: Optional[str] = None

    async def start(self):
        """Start the cognitive loop as a background task."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[CognitiveLoop] Started (interval: %ds, min: %ds)", self.cycle_interval, self.min_interval)

    async def stop(self):
        """Stop the cognitive loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[CognitiveLoop] Stopped")

    @property
    def phase(self) -> str:
        return self._phase

    # ── Main Loop ──

    async def _run_loop(self):
        """Core loop: OBSERVE → ORIENT → DECIDE → ACT → sleep → repeat."""
        # Brief startup delay to let subsystems initialize
        await asyncio.sleep(5)

        while self.running:
            try:
                self.cycle_count += 1

                self._phase = "observe"
                await self._broadcast_status()
                observations = await self._observe()

                self._phase = "orient"
                await self._broadcast_status()
                insights = await self._orient(observations)

                # Advocacy phase — pattern detection and goal tracking
                self._phase = "advocate"
                await self._broadcast_status()
                await self._advocate(observations, insights)

                self._phase = "decide"
                await self._broadcast_status()
                actions = await self._decide(insights)

                self._phase = "act"
                await self._broadcast_status()
                await self._act(actions)

                # Periodic reflection
                if self.cycle_count % self._reflection_every_n == 0:
                    await self._reflect()

                # Check scheduled briefings
                await self._check_scheduled_briefings()

                self._phase = "idle"
                await self._broadcast_status()

                interval = self._adaptive_interval(observations)
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[CognitiveLoop] Cycle error: %s", e, exc_info=True)
                self._phase = "idle"
                await asyncio.sleep(self.cycle_interval)

    # ── OBSERVE Phase ──

    async def _observe(self) -> list[dict]:
        """Gather raw data from all subsystems."""
        observations = []
        now = time.time()

        # 1. Security audit queue
        try:
            security_agent = self._core.registry.get("security") if self._core.registry else None
            if security_agent:
                queue, flags = security_agent.get_and_clear_audit_data()
                if flags:
                    for flag in flags:
                        observations.append({
                            "source": "security",
                            "type": "security_flag",
                            "category": flag.category,
                            "confidence": flag.confidence,
                            "summary": flag.summary,
                            "timestamp": now,
                        })
                if queue:
                    observations.append({
                        "source": "security",
                        "type": "audit_queue_size",
                        "count": len(queue),
                        "timestamp": now,
                    })
        except Exception as e:
            logger.warning("[CognitiveLoop] Security observe error: %s", e)

        # 2. Marketing stats
        try:
            with db_connection_row() as conn:
                # Email stats
                email_rows = conn.execute(
                    "SELECT status, COUNT(*) as c FROM marketing_emails GROUP BY status"
                ).fetchall()
                email_stats = {r["status"]: r["c"] for r in email_rows}

                # Content stats
                content_rows = conn.execute(
                    "SELECT status, COUNT(*) as c FROM content_drafts GROUP BY status"
                ).fetchall()
                content_stats = {r["status"]: r["c"] for r in content_rows}

                # Recent outreach responses
                recent_outreach = conn.execute(
                    "SELECT COUNT(*) as c FROM outreach_attempts WHERE status IN ('opened', 'replied') AND updated_at > ?",
                    (now - 86400,)
                ).fetchone()

                # Pending content count
                pending_content = conn.execute(
                    "SELECT COUNT(*) as c FROM content_drafts WHERE status = 'drafted'"
                ).fetchone()

            observations.append({
                "source": "marketing",
                "type": "stats",
                "email_stats": email_stats,
                "content_stats": content_stats,
                "recent_responses": recent_outreach["c"] if recent_outreach else 0,
                "pending_content": pending_content["c"] if pending_content else 0,
                "timestamp": now,
            })
        except Exception as e:
            logger.warning("[CognitiveLoop] Marketing observe error: %s", e)

        # 3. Channel messages since last observation
        try:
            if self._core.channel_manager:
                channels = self._core.channel_manager.get_all_channels()
                new_messages = 0
                for ch in channels:
                    msgs = self._core.channel_manager.get_channel_messages(
                        ch.get("name", ""), limit=10
                    )
                    for msg in msgs:
                        msg_time = msg.get("timestamp", "")
                        if msg_time and msg_time > datetime.fromtimestamp(
                            self._last_observation_time, tz=timezone.utc
                        ).isoformat():
                            new_messages += 1
                if new_messages > 0:
                    observations.append({
                        "source": "channels",
                        "type": "new_messages",
                        "count": new_messages,
                        "timestamp": now,
                    })
        except Exception as e:
            logger.warning("[CognitiveLoop] Channel observe error: %s", e)

        # 4. System health
        try:
            active_tasks = sum(1 for t in self._core._tasks.values() if t.status == "running")
            memory_count = self._core.memory.count()
            ws_clients = len(self._core.ws_clients)
            observations.append({
                "source": "system",
                "type": "health",
                "active_tasks": active_tasks,
                "memory_entries": memory_count,
                "connected_clients": ws_clients,
                "timestamp": now,
            })
        except Exception as e:
            logger.warning("[CognitiveLoop] System health observe error: %s", e)

        # 5. Moltbook engagement (if configured)
        try:
            from integrations.moltbook import get_moltbook_client
            client = get_moltbook_client()
            if client and client.is_configured():
                with db_connection_row() as conn:
                    published = conn.execute(
                        "SELECT id, platform_post_id FROM content_drafts WHERE status = 'published' AND platform = 'moltbook' AND platform_post_id IS NOT NULL ORDER BY updated_at DESC LIMIT 5"
                    ).fetchall()
                for post in published:
                    if post["platform_post_id"]:
                        try:
                            stats = await client.get_post_stats(post["platform_post_id"])
                            if stats:
                                observations.append({
                                    "source": "moltbook",
                                    "type": "engagement",
                                    "draft_id": post["id"],
                                    "platform_post_id": post["platform_post_id"],
                                    "stats": stats,
                                    "timestamp": now,
                                })
                        except Exception:
                            pass
        except ImportError:
            pass
        except Exception as e:
            logger.warning("[CognitiveLoop] Moltbook observe error: %s", e)

        self._last_observation_time = now
        self.observations = observations
        return observations

    # ── ORIENT Phase ──

    async def _orient(self, observations: list[dict]) -> list[dict]:
        """Process observations, identify patterns and content angles."""
        insights = []

        if not observations:
            return insights

        # Summarize observations
        obs_summary = self._summarize_observations(observations)

        # Search memory for related past observations
        related_memories = []
        if self._core.memory._api_base and obs_summary:
            try:
                related_memories = await self._core.memory.search(
                    obs_summary[:500], top_k=5
                )
            except Exception as e:
                logger.warning("[CognitiveLoop] Memory search error: %s", e)

        # Identify content angles from security events
        security_obs = [o for o in observations if o["source"] == "security" and o["type"] == "security_flag"]
        for sec in security_obs:
            insights.append({
                "type": "content_angle",
                "source": "security",
                "urgency": sec.get("confidence", 0.5),
                "summary": f"Security finding: {sec.get('summary', '')}",
                "content_suggestion": f"Moltbook post analyzing {sec.get('category', 'security event')}: {sec.get('summary', '')}",
                "platform": "moltbook",
            })

        # Identify content angles from marketing stats
        marketing_obs = [o for o in observations if o["source"] == "marketing" and o["type"] == "stats"]
        for mkt in marketing_obs:
            responses = mkt.get("recent_responses", 0)
            if responses > 0:
                insights.append({
                    "type": "engagement_signal",
                    "source": "marketing",
                    "urgency": 0.5,
                    "summary": f"{responses} outreach responses in last 24h",
                })
            pending = mkt.get("pending_content", 0)
            if pending > 3:
                insights.append({
                    "type": "queue_alert",
                    "source": "marketing",
                    "urgency": 0.4,
                    "summary": f"{pending} content drafts pending approval",
                })

        # Identify engagement patterns from Moltbook
        engagement_obs = [o for o in observations if o["source"] == "moltbook" and o["type"] == "engagement"]
        for eng in engagement_obs:
            stats = eng.get("stats", {})
            views = stats.get("views", 0)
            if views > 100:
                insights.append({
                    "type": "content_performance",
                    "source": "moltbook",
                    "urgency": 0.6,
                    "summary": f"Post {eng.get('draft_id', '')} has {views} views — high engagement",
                    "stats": stats,
                })

        # Match insights to ICP personas
        try:
            with db_connection_row() as conn:
                personas = conn.execute("SELECT id, name, pain_points, preferred_platforms FROM icp_personas").fetchall()
            for insight in insights:
                if insight["type"] == "content_angle":
                    summary_lower = insight.get("summary", "").lower()
                    for persona in personas:
                        pain = (persona["pain_points"] or "").lower()
                        if any(term in summary_lower for term in pain.split(",")[:3] if term.strip()):
                            insight["matched_persona_id"] = persona["id"]
                            insight["matched_persona_name"] = persona["name"]
                            break
        except Exception as e:
            logger.warning("[CognitiveLoop] Persona matching error: %s", e)

        # Detect patterns from memory
        if related_memories:
            memory_texts = [m.get("text", "") for m in related_memories]
            pattern_hint = self._detect_patterns(memory_texts, observations)
            if pattern_hint:
                insights.append({
                    "type": "pattern",
                    "source": "memory",
                    "urgency": 0.3,
                    "summary": pattern_hint,
                })

        return insights

    # ── ADVOCATE Phase ──

    async def _advocate(self, observations: list[dict], insights: list[dict]):
        """Run advocacy pattern detection if the subsystem is enabled."""
        advocacy = getattr(self._core, 'advocacy_system', None)
        if not advocacy or not advocacy.enabled:
            return

        try:
            await advocacy.run_advocacy_cycle(observations)
        except Exception as e:
            logger.warning("[CognitiveLoop] Advocacy phase error: %s", e)

    # ── DECIDE Phase ──

    async def _decide(self, insights: list[dict]) -> list[dict]:
        """Rank insights, filter, and route to actions."""
        actions = []

        if not insights:
            return actions

        # Sort by urgency
        insights.sort(key=lambda x: x.get("urgency", 0), reverse=True)

        # Check user presence
        user_present = len(self._core.ws_clients) > 0

        # Deduplicate against recent content
        recent_titles = set()
        try:
            with db_connection_row() as conn:
                recent = conn.execute(
                    "SELECT title FROM content_drafts WHERE created_at > ? ORDER BY created_at DESC LIMIT 20",
                    (time.time() - 86400,)
                ).fetchall()
                recent_titles = {r["title"].lower() for r in recent if r["title"]}
        except Exception:
            pass

        for insight in insights:
            urgency = insight.get("urgency", 0)

            # Content angle → draft content
            if insight["type"] == "content_angle":
                suggestion = insight.get("content_suggestion", "")
                if suggestion and suggestion.lower() not in recent_titles:
                    actions.append({
                        "action": "draft_content",
                        "insight": insight,
                        "urgency": urgency,
                    })
                    # If persona matched → also draft outreach
                    if insight.get("matched_persona_id"):
                        actions.append({
                            "action": "draft_outreach",
                            "insight": insight,
                            "urgency": urgency,
                        })

            # Queue alerts
            if insight["type"] == "queue_alert" and user_present:
                actions.append({
                    "action": "notify_user",
                    "insight": insight,
                    "urgency": urgency,
                })

            # Engagement signals
            if insight["type"] == "engagement_signal" and user_present:
                actions.append({
                    "action": "notify_user",
                    "insight": insight,
                    "urgency": urgency,
                })

            # High-performance content → suggest more
            if insight["type"] == "content_performance":
                actions.append({
                    "action": "content_series",
                    "insight": insight,
                    "urgency": urgency,
                })

            # Patterns → store to memory
            if insight["type"] == "pattern":
                actions.append({
                    "action": "store_pattern",
                    "insight": insight,
                    "urgency": urgency,
                })

            # Urgent security → immediate notification
            if insight["type"] == "content_angle" and insight["source"] == "security" and urgency > 0.8:
                actions.append({
                    "action": "urgent_notify",
                    "insight": insight,
                    "urgency": urgency,
                })

        return actions

    # ── ACT Phase ──

    def _cap_collections(self):
        """Enforce size caps on in-memory collections."""
        if len(self.thought_journal) > self._MAX_THOUGHT_JOURNAL:
            self.thought_journal = self.thought_journal[-self._MAX_THOUGHT_JOURNAL:]
        if len(self.content_angles) > self._MAX_CONTENT_ANGLES:
            self.content_angles = self.content_angles[-self._MAX_CONTENT_ANGLES:]

    def _can_write_memory(self) -> bool:
        """Check if we're under the daily memory write cap."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._memory_writes_reset_date != today:
            self._memory_writes_today = 0
            self._memory_writes_reset_date = today
        return self._memory_writes_today < self._MAX_MEMORY_WRITES_PER_DAY

    def _record_memory_write(self):
        """Increment the daily memory write counter."""
        self._memory_writes_today += 1

    async def _act(self, actions: list[dict]):
        """Execute actions across all subsystems."""
        self._cap_collections()
        for action in actions:
            try:
                action_type = action["action"]
                insight = action.get("insight", {})

                if action_type == "draft_content":
                    await self._act_draft_content(insight)

                elif action_type == "draft_outreach":
                    await self._act_draft_outreach(insight)

                elif action_type == "notify_user":
                    await self._act_notify_user(insight)

                elif action_type == "urgent_notify":
                    await self._act_urgent_notify(insight)

                elif action_type == "store_pattern":
                    await self._act_store_pattern(insight)

                elif action_type == "content_series":
                    await self._act_content_series(insight)

            except Exception as e:
                logger.warning("[CognitiveLoop] Action error (%s): %s", action.get("action"), e)

    async def _act_draft_content(self, insight: dict):
        """Dispatch Content Agent to draft a Moltbook post or social content."""
        suggestion = insight.get("content_suggestion", "")
        platform = insight.get("platform", "moltbook")

        if not suggestion:
            return

        # Use tools_content directly to create a draft placeholder
        from tools_content import draft_content
        content_type = "moltbook_post" if platform == "moltbook" else "social_post"
        result = draft_content(
            content_type=content_type,
            title=suggestion[:200],
            body=f"[AUTO-DRAFTED by cognitive loop]\n\n{suggestion}",
            platform=platform,
            tags="cognitive_loop,auto_drafted",
        )

        result_data = json.loads(result)
        draft_id = result_data.get("draft_id")

        if draft_id:
            await self._core.broadcast({
                "type": "content_drafted",
                "draft_id": draft_id,
                "title": suggestion[:200],
                "platform": platform,
                "source": "cognitive_loop",
            })

            # Record in thought journal
            self.thought_journal.append({
                "type": "content_drafted",
                "draft_id": draft_id,
                "summary": suggestion[:200],
                "timestamp": time.time(),
            })

        logger.info("[CognitiveLoop] Drafted content: %s", suggestion[:100])

    async def _act_draft_outreach(self, insight: dict):
        """Queue outreach email draft when persona match found."""
        persona_id = insight.get("matched_persona_id", "")
        persona_name = insight.get("matched_persona_name", "")
        summary = insight.get("summary", "")

        if not persona_id:
            return

        # Store a thought about the match for future use
        self.thought_journal.append({
            "type": "persona_match",
            "persona_id": persona_id,
            "persona_name": persona_name,
            "insight_summary": summary,
            "timestamp": time.time(),
        })

        # Broadcast notification about the match
        await self._core.broadcast({
            "type": "proactive_insight",
            "category": "outreach_opportunity",
            "message": f"Content angle matches persona '{persona_name}' — outreach opportunity identified.",
            "persona_id": persona_id,
        })

    async def _act_notify_user(self, insight: dict):
        """Send proactive notification to the user."""
        message = insight.get("summary", "")
        if not message:
            return

        await self._core.broadcast({
            "type": "proactive_insight",
            "category": insight.get("type", "observation"),
            "message": message,
            "urgency": insight.get("urgency", 0.5),
        })

    async def _act_urgent_notify(self, insight: dict):
        """Send urgent notification — security or critical event."""
        message = insight.get("summary", "")
        await self._core.broadcast({
            "type": "proactive_insight",
            "category": "urgent",
            "message": f"[URGENT] {message}",
            "urgency": insight.get("urgency", 0.9),
        })


    async def _act_store_pattern(self, insight: dict):
        """Store identified pattern to memory (rate-limited)."""
        summary = insight.get("summary", "")
        if not summary or not self._core.memory._api_base:
            return
        if not self._can_write_memory():
            return

        try:
            await self._core.memory.store(
                f"[Pattern detected] {summary}",
                tags="cognitive_loop,pattern,insight",
            )
            self._record_memory_write()
        except Exception as e:
            logger.warning("[CognitiveLoop] Memory store error: %s", e)

    async def _act_content_series(self, insight: dict):
        """Note high-performing content for series suggestion."""
        self.thought_journal.append({
            "type": "content_series_candidate",
            "insight": insight.get("summary", ""),
            "stats": insight.get("stats", {}),
            "timestamp": time.time(),
        })

    # ── Reflection ──

    async def _reflect(self):
        """Periodic self-reflection — organize thoughts, identify themes."""
        now = time.time()

        if not self._core.memory._api_base:
            return

        if not self._can_write_memory():
            logger.info("[CognitiveLoop] Skipping reflection — daily memory write cap reached")
            return

        # Query recent memories
        try:
            recent = await self._core.memory.search(
                "recent observations insights patterns", top_k=10
            )
        except Exception:
            recent = []

        if not recent and not self.thought_journal:
            return

        # Build reflection summary from thought journal
        journal_summary = ""
        if self.thought_journal:
            recent_thoughts = self.thought_journal[-20:]
            types = {}
            for t in recent_thoughts:
                types[t["type"]] = types.get(t["type"], 0) + 1
            journal_summary = f"Recent thoughts ({len(recent_thoughts)}): " + ", ".join(
                f"{k}: {v}" for k, v in types.items()
            )

        # Identify recurring content themes
        content_themes = []
        content_thoughts = [t for t in self.thought_journal if t["type"] in ("content_drafted", "content_series_candidate")]
        if len(content_thoughts) >= 3:
            summaries = [t.get("summary", t.get("insight", "")) for t in content_thoughts[-10:]]
            content_themes = summaries

        # Store reflection as a memory entry
        reflection_text = f"[Reflection — cycle {self.cycle_count}]\n"
        reflection_text += f"Observations this period: {len(self.observations)}\n"
        reflection_text += f"Thought journal entries: {len(self.thought_journal)}\n"
        if journal_summary:
            reflection_text += f"{journal_summary}\n"
        if content_themes:
            reflection_text += f"Content themes identified: {', '.join(t[:80] for t in content_themes[:5])}\n"

        try:
            await self._core.memory.store(
                reflection_text,
                tags="cognitive_loop,reflection,meta",
            )
            self._record_memory_write()
        except Exception as e:
            logger.warning("[CognitiveLoop] Reflection store error: %s", e)

        self._last_reflection_time = now
        logger.info("[CognitiveLoop] Reflection complete (cycle %d)", self.cycle_count)

    # ── Scheduled Briefings ──

    async def _check_scheduled_briefings(self):
        """Check if a morning or evening briefing is due."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hour = now.hour

        # Morning briefing
        if hour >= self._morning_briefing_hour and (
            self._last_briefing_date != today or self._last_briefing_type != "morning"
        ):
            if self._last_briefing_date != today:
                await self._generate_briefing("morning")
                self._last_briefing_date = today
                self._last_briefing_type = "morning"

        # Evening briefing
        elif hour >= self._evening_briefing_hour and self._last_briefing_type == "morning":
            await self._generate_briefing("evening")
            self._last_briefing_type = "evening"

    async def _generate_briefing(self, briefing_type: str):
        """Generate and broadcast a scheduled briefing."""
        now = time.time()

        # Gather briefing data
        try:
            with db_connection_row() as conn:
                # Pending content
                pending_content = conn.execute(
                    "SELECT COUNT(*) as c FROM content_drafts WHERE status = 'drafted'"
                ).fetchone()["c"]

                # Published today
                published_today = conn.execute(
                    "SELECT COUNT(*) as c FROM content_drafts WHERE status = 'published' AND updated_at > ?",
                    (now - 86400,)
                ).fetchone()["c"]

                # Email stats
                pending_emails = conn.execute(
                    "SELECT COUNT(*) as c FROM marketing_emails WHERE status = 'pending'"
                ).fetchone()["c"]

                sent_emails = conn.execute(
                    "SELECT COUNT(*) as c FROM outreach_attempts WHERE status = 'sent' AND updated_at > ?",
                    (now - 86400,)
                ).fetchone()["c"]

                # Responses
                responses = conn.execute(
                    "SELECT COUNT(*) as c FROM outreach_attempts WHERE status IN ('opened', 'replied') AND updated_at > ?",
                    (now - 86400,)
                ).fetchone()["c"]

        except Exception as e:
            logger.warning("[CognitiveLoop] Briefing data error: %s", e)
            return

        if briefing_type == "morning":
            content = (
                f"**Morning Briefing**\n\n"
                f"Content: {pending_content} drafts pending approval, {published_today} published in last 24h\n"
                f"Outreach: {pending_emails} emails pending, {sent_emails} sent, {responses} responses\n"
                f"Cognitive loop: {self.cycle_count} cycles completed, {len(self.thought_journal)} thoughts recorded"
            )
        else:
            content = (
                f"**Evening Summary**\n\n"
                f"Today's activity: {published_today} pieces published, {sent_emails} emails sent\n"
                f"Engagement: {responses} responses received\n"
                f"Pending: {pending_content} content drafts, {pending_emails} emails awaiting approval\n"
                f"Cognitive loop: {self.cycle_count} total cycles"
            )

        # Store as briefing
        briefing = {
            "id": str(uuid.uuid4())[:12],
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "briefing_type": briefing_type,
        }
        self._core._briefings.append(briefing)

        await self._core.broadcast({
            "type": "briefing_ready",
            "briefing": briefing,
        })

        logger.info("[CognitiveLoop] Generated %s briefing", briefing_type)

    # ── Helpers ──

    def _adaptive_interval(self, observations: list[dict]) -> float:
        """Shorten interval when there's more activity."""
        if not observations:
            return self.cycle_interval

        # Count high-urgency items
        urgent_count = sum(
            1 for o in observations
            if o.get("source") == "security" and o.get("type") == "security_flag"
        )

        # More active system → shorter intervals
        total = len(observations)
        if urgent_count > 0:
            return self.min_interval
        elif total > 5:
            return max(self.min_interval, self.cycle_interval // 2)
        else:
            return self.cycle_interval

    def _summarize_observations(self, observations: list[dict]) -> str:
        """Create a text summary of current observations."""
        parts = []
        for obs in observations[:10]:
            source = obs.get("source", "unknown")
            obs_type = obs.get("type", "unknown")
            summary = obs.get("summary", "")
            if summary:
                parts.append(f"[{source}/{obs_type}] {summary}")
            elif obs_type == "stats":
                parts.append(f"[{source}] stats update")
            elif obs_type == "health":
                parts.append(f"[system] {obs.get('active_tasks', 0)} active tasks, {obs.get('memory_entries', 0)} memories")
        return "; ".join(parts)

    def _detect_patterns(self, memory_texts: list[str], observations: list[dict]) -> Optional[str]:
        """Simple keyword-based pattern detection across memory and observations."""
        # Count recurring terms across memory and observations
        all_text = " ".join(memory_texts + [o.get("summary", "") for o in observations]).lower()

        keywords = ["breach", "privacy", "compliance", "security", "engagement", "outreach"]
        found = [k for k in keywords if all_text.count(k) >= 2]

        if found:
            return f"Recurring themes detected: {', '.join(found)}"
        return None

    async def _broadcast_status(self):
        """Broadcast current cognitive loop phase to UI."""
        try:
            await self._core.broadcast({
                "type": "cognitive_status",
                "phase": self._phase,
                "cycle": self.cycle_count,
                "observations": len(self.observations),
                "thoughts": len(self.thought_journal),
            })
        except Exception:
            pass

    def get_status(self) -> dict:
        """Return current loop status."""
        return {
            "running": self.running,
            "phase": self._phase,
            "cycle_count": self.cycle_count,
            "observations": len(self.observations),
            "thought_journal_size": len(self.thought_journal),
            "content_angles": len(self.content_angles),
            "cycle_interval": self.cycle_interval,
        }
