"""
GPUScheduler — Manages agent execution with uniform dispatch.

All models are always loaded (Hermes 70B + small MLX fleet). No GPU swapping needed.
Hermes handles concurrent requests via llama.cpp continuous batching.

Architecture:
  - Hermes 4 70B Q8 (llama.cpp): Central engine, continuous batching
  - Small MLX models: Classifier 0.6B, Voice 4B, Security 7B, Embedder
  - All agents dispatch uniformly via asyncio.create_task
  - Security monitoring: WhiteRabbitNeo V3 7B (always loaded), escalates to user
  - Synthesis: voice agent presents results
"""

import asyncio
import json
import logging
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from agents.base import BaseAgent, AgentState
from agents.registry import AgentRegistry
from orchestration.messages import (
    AgentMessage, MessageBus, MessageType, MessagePriority,
)
from orchestration.workspace import SharedWorkspace
from config import ALWAYS_LOADED_MODELS, MODEL_LABELS, SECURITY_MONITOR_CONFIG, SECURITY_HEARTBEAT_CONFIG


class GPUScheduler:
    """Schedules agent execution with uniform dispatch via asyncio."""

    def __init__(self, registry: AgentRegistry, bus: MessageBus,
                 workspace: SharedWorkspace, agent_core):
        self.registry = registry
        self.bus = bus
        self.workspace = workspace
        self._core = agent_core
        self._missions: dict[str, dict] = {}  # mission_id -> {status, tasks, results, ...}
        self._mission_locks: dict[str, asyncio.Lock] = {}  # mission_id -> lock for level advancement
        self._current_large_agent: Optional[str] = None
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._waiting_agents: dict[str, dict] = {}  # agent_id -> saved state for resume
        self._inflight: dict[str, int] = {}  # agent_id -> running task count
        self._poll_interval = 0.05  # 50ms
        # Security monitor (WhiteRabbitNeo V3 7B — always loaded)
        self._security_monitor: Optional[BaseAgent] = None

    # ── Mission Management ──

    def submit_mission(self, mission_id: str, tasks: list[dict],
                       synthesize: bool = True, user_message: str = "",
                       history: list = None):
        """Convert planner tasks to AgentMessages and submit to bus."""
        self._missions[mission_id] = {
            "status": "running",
            "tasks": {t["id"]: t for t in tasks},
            "results": {},
            "synthesize": synthesize,
            "user_message": user_message,
            "history": history,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_tasks": len(tasks),
            "completed_tasks": 0,
        }
        self._mission_locks[mission_id] = asyncio.Lock()

        # Build dependency levels
        task_map = {t["id"]: t for t in tasks}
        completed = set()
        levels = []
        remaining = list(tasks)

        while remaining:
            ready = [t for t in remaining if all(dep in completed for dep in t.get("depends_on", []))]
            if not ready:
                ready = remaining[:1]
            levels.append(ready)
            for t in ready:
                completed.add(t["id"])
                remaining.remove(t)

        # Send messages for first level immediately, rest will be sent as dependencies complete
        self._missions[mission_id]["levels"] = levels
        self._missions[mission_id]["current_level"] = 0

        self._send_level_tasks(mission_id, 0)

    def _send_level_tasks(self, mission_id: str, level_idx: int):
        """Send AgentMessages for all tasks in a dependency level."""
        mission = self._missions[mission_id]
        if level_idx >= len(mission["levels"]):
            return

        level = mission["levels"][level_idx]
        for task in level:
            model_key = task.get("model", "coder")
            agent_id = model_key

            # Determine action
            if task.get("security_consultation") and model_key == "hermes":
                action = "security_consultation"
            else:
                action = "execution"

            msg = AgentMessage.create(
                msg_type=MessageType.TASK,
                sender="scheduler",
                recipient=agent_id,
                mission_id=mission_id,
                content=task.get("task", ""),
                payload={
                    "action": action,
                    "task_id": task["id"],
                    "tools_needed": task.get("tools_needed", True),
                    "tool_plan": task.get("tool_plan"),
                    "depends_on": task.get("depends_on", []),
                },
                priority=MessagePriority.HIGH if task.get("security_consultation") else MessagePriority.NORMAL,
            )
            self.bus.send(msg)

    async def await_mission(self, mission_id: str, timeout: float = 600) -> dict:
        """Block until a mission completes, return results."""
        start = time.time()
        while time.time() - start < timeout:
            mission = self._missions.get(mission_id)
            if not mission:
                return {"error": "Mission not found"}
            if mission["status"] in ("completed", "failed"):
                return mission
            await asyncio.sleep(0.1)
        return {"error": "Mission timeout", "status": "timeout"}

    # ── Scheduler Loop ──

    def set_security_monitor(self, monitor_agent):
        """Set the security agent reference for security monitoring."""
        self._security_monitor = monitor_agent

    def start_loop(self):
        """Start the scheduler polling loop if not already running."""
        if not self._running:
            self._running = True
            self._loop_task = asyncio.create_task(self._run_loop())

    def stop_loop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

    async def _run_loop(self):
        """Main scheduling loop — polls for pending messages, dispatches agents.

        All models are always loaded. Uniform dispatch via asyncio.create_task.
        Hermes handles concurrent requests via llama.cpp continuous batching.
        """
        while self._running:
            try:
                agents_with_work = self.bus.agents_with_pending_messages()
                if not agents_with_work:
                    await asyncio.sleep(self._poll_interval)
                    continue

                for agent_id in agents_with_work:
                    agent = self.registry.get(agent_id)
                    if not agent:
                        # Consume and discard messages for unknown agents
                        while self.bus.has_pending(agent_id):
                            msg = self.bus.pop_next(agent_id)
                            if msg:
                                self.bus.mark_processed(msg.id)
                        continue

                    if agent.state == AgentState.SUSPENDED:
                        continue

                    # Dispatch up to 4 concurrent tasks per agent
                    max_dispatch = 4
                    dispatched = 0
                    while dispatched < max_dispatch and self.bus.has_pending(agent_id):
                        msg = self.bus.pop_next(agent_id)
                        if not msg:
                            break
                        dispatched += 1
                        asyncio.create_task(self._run_agent(agent, msg))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Loop error: %s", e)
                await asyncio.sleep(self._poll_interval)

    async def _run_agent(self, agent: BaseAgent, message: AgentMessage):
        """Run an agent on a message, handle the response."""
        agent.state = AgentState.RUNNING
        mission_id = message.mission_id

        # Track inflight count for concurrent dispatch
        self._inflight[agent.agent_id] = self._inflight.get(agent.agent_id, 0) + 1

        await self._core.broadcast({
            "type": "agent_event",
            "event": "agent_running",
            "agent": agent.agent_id,
            "mission_id": mission_id,
            "task_preview": message.content[:100],
        })

        try:
            response = await agent.run(message, self.bus, self.workspace)

            self.bus.mark_processed(message.id)

            if response:
                self._handle_agent_response(agent, response)

        except Exception as e:
            logger.error("Agent %s error: %s", agent.agent_id, e)
            agent.state = AgentState.ERROR
            error_msg = AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=agent.agent_id,
                recipient="scheduler",
                mission_id=mission_id,
                content=f"Agent error: {e}",
                payload={"error": True, "task_id": message.payload.get("task_id", "")},
            )
            self._handle_agent_response(agent, error_msg)
        finally:
            self._inflight[agent.agent_id] = max(0, self._inflight.get(agent.agent_id, 1) - 1)

        await self._core.broadcast({
            "type": "agent_event",
            "event": "agent_completed" if agent.state != AgentState.WAITING else "agent_waiting",
            "agent": agent.agent_id,
            "mission_id": mission_id,
        })

        # Check if security monitor has critical flags
        await self._check_critical_flags()

    def _handle_agent_response(self, agent: BaseAgent, response: AgentMessage):
        """Process an agent's response message."""
        mission_id = response.mission_id
        mission = self._missions.get(mission_id)

        if response.msg_type == MessageType.RESULT:
            # Task complete — record result
            task_id = response.payload.get("task_id", "")
            if mission and task_id:
                mission["results"][task_id] = {
                    "id": task_id,
                    "model": response.payload.get("model", agent.agent_id),
                    "task": response.content[:200],
                    "result": response.content,
                    "tool_calls": response.payload.get("tool_calls", []),
                    "consultations": response.payload.get("consultations", []),
                }
                mission["completed_tasks"] = len(mission["results"])

                # Broadcast progress
                asyncio.create_task(self._core.broadcast({
                    "type": "mission_update",
                    "mission_id": mission_id,
                    "status": "running",
                    "completed": mission["completed_tasks"],
                    "total": mission["total_tasks"],
                    "active_agent": agent.agent_id,
                }))

                # Check if current level is complete (async, uses per-mission lock)
                asyncio.create_task(self._check_level_completion(mission_id))

        elif response.msg_type == MessageType.PROGRESS:
            if response.payload.get("waiting_for"):
                self._waiting_agents[agent.agent_id] = response.payload

        elif response.msg_type == MessageType.RESPONSE:
            self.bus.send(response)

        elif response.msg_type in (MessageType.REQUEST, MessageType.QUERY):
            self.bus.send(response)

        elif response.msg_type == MessageType.OBSERVATION:
            pass

    async def _check_level_completion(self, mission_id: str):
        """Check if all tasks in the current level are complete. If so, advance.

        Uses a per-mission lock to prevent race conditions where concurrent
        task completions both trigger level advancement.
        """
        lock = self._mission_locks.get(mission_id)
        if not lock:
            return

        async with lock:
            mission = self._missions.get(mission_id)
            if not mission or mission["status"] != "running":
                return

            current_level_idx = mission.get("current_level", 0)
            levels = mission.get("levels", [])

            if current_level_idx >= len(levels):
                return

            current_level = levels[current_level_idx]
            level_task_ids = {t["id"] for t in current_level}
            completed_ids = set(mission["results"].keys())

            if level_task_ids.issubset(completed_ids):
                # Current level complete — advance
                next_level = current_level_idx + 1
                mission["current_level"] = next_level

                if next_level < len(levels):
                    # Send next level's tasks
                    self._send_level_tasks(mission_id, next_level)
                else:
                    # All levels complete — synthesis is handled by core.py via presentation layer
                    mission["status"] = "completed"
                    # Clean up the lock and evict old missions
                    self._mission_locks.pop(mission_id, None)
                    self._evict_old_missions()
                    asyncio.create_task(self._core.broadcast({
                        "type": "mission_update",
                        "mission_id": mission_id,
                        "status": "completed",
                    }))

    # ── Security Monitor ──

    async def _check_critical_flags(self):
        """Check if security monitor has critical flags and notify user."""
        if not self._security_monitor:
            return

        from agents.security import SecurityAgent
        if not isinstance(self._security_monitor, SecurityAgent):
            return

        critical_threshold = SECURITY_MONITOR_CONFIG.get("critical_threshold", 0.9)
        critical_flags = self._security_monitor.get_flags(min_confidence=critical_threshold)

        if not critical_flags:
            return

        logger.warning("CRITICAL security flags detected (%d) — notifying user", len(critical_flags))

        # Escalate to user — no automatic 70B loading
        flag_summaries = [f.summary for f in critical_flags[:5]]
        await self._core.broadcast({
            "type": "security_alert",
            "severity": "critical",
            "flags": [{"id": f.id, "category": f.category, "confidence": f.confidence, "summary": f.summary}
                      for f in critical_flags],
            "message": f"Security monitor detected {len(critical_flags)} critical flag(s)",
        })

    # ── Status ──

    MAX_CACHED_MISSIONS = 200  # evict oldest completed missions beyond this limit

    def _evict_old_missions(self):
        """Evict oldest completed missions from in-memory cache when limit exceeded."""
        if len(self._missions) <= self.MAX_CACHED_MISSIONS:
            return
        completed = [(mid, m) for mid, m in self._missions.items()
                     if m.get("status") in ("completed", "failed")]
        completed.sort(key=lambda x: x[1].get("created_at", ""))
        to_remove = len(self._missions) - self.MAX_CACHED_MISSIONS
        for mid, _ in completed[:to_remove]:
            self._missions.pop(mid, None)
            self._mission_locks.pop(mid, None)

    def get_mission(self, mission_id: str) -> Optional[dict]:
        return self._missions.get(mission_id)

    def get_all_missions(self) -> dict:
        return dict(self._missions)


class SecurityHeartbeat:
    """Proactive security scanning on a recurring schedule.

    Runs scan_processes(), scan_network(), and scan_file_integrity() at a
    configurable interval. Feeds raw scan data to WhiteRabbitNeo for analysis.
    Broadcasts alerts via WebSocket and updates persistent state.
    """

    def __init__(self, agent_core):
        self._core = agent_core
        self._config = SECURITY_HEARTBEAT_CONFIG
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._scan_count = 0

    def start(self):
        """Start the heartbeat loop."""
        if not self._config.get("enabled", True):
            logger.info("SecurityHeartbeat disabled by config")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("SecurityHeartbeat started (interval=%ds)", self._config['interval_seconds'])

    def stop(self):
        """Stop the heartbeat loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self):
        """Main heartbeat loop."""
        interval = self._config.get("interval_seconds", 600)
        # Short initial delay to let the system stabilize
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._run_scan()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("SecurityHeartbeat scan error: %s", e)
            await asyncio.sleep(interval)

    async def _run_scan(self):
        """Execute all configured scans and feed results to WhiteRabbitNeo."""
        from tools_system import scan_processes, scan_network, scan_file_integrity

        scan_data = {"timestamp": datetime.now(timezone.utc).isoformat()}

        if self._config.get("scan_processes", True):
            scan_data["processes"] = scan_processes()

        if self._config.get("scan_network", True):
            scan_data["network"] = scan_network()

        if self._config.get("scan_file_integrity", True):
            scan_data["file_integrity"] = scan_file_integrity(
                self._config.get("watched_paths", []),
                self._config.get("baseline_path", ""),
            )

        self._scan_count += 1

        # Feed to WhiteRabbitNeo for analysis
        security_agent = self._core.registry.get("security") if self._core.registry else None
        anomalies = []

        if security_agent:
            try:
                analysis = await self._analyze_scan(security_agent, scan_data)
                anomalies = self._extract_anomalies(analysis, scan_data)
            except Exception as e:
                logger.error("SecurityHeartbeat analysis error: %s", e)

        # Update persistent state
        if hasattr(self._core, '_state'):
            hb_state = self._core._state.get("security_heartbeat", {})
            hb_state["last_scan"] = scan_data["timestamp"]
            hb_state["scan_count"] = self._scan_count
            hb_state["anomalies_found"] = hb_state.get("anomalies_found", 0) + len(anomalies)
            self._core._state["security_heartbeat"] = hb_state

        # Alert on anomalies
        if anomalies:
            await self._core.broadcast({
                "type": "security_alert",
                "severity": "warning",
                "source": "heartbeat",
                "message": f"Security heartbeat detected {len(anomalies)} anomaly(ies)",
                "anomalies": anomalies,
            })

        logger.info("SecurityHeartbeat scan #%d complete — %d anomalies", self._scan_count, len(anomalies))

    async def _analyze_scan(self, security_agent, scan_data: dict) -> str:
        """Send scan data to WhiteRabbitNeo for analysis."""
        # Build a concise summary for the LLM
        summary_parts = []

        proc_data = scan_data.get("processes", {})
        if proc_data and not proc_data.get("error"):
            # Only include notable processes (high CPU/mem, non-system)
            notable = [p for p in proc_data.get("processes", [])
                       if float(p.get("cpu", 0)) > 5 or float(p.get("mem", 0)) > 5]
            summary_parts.append(
                f"PROCESSES: {proc_data.get('process_count', 0)} total, "
                f"{len(notable)} notable (high CPU/mem):\n"
                + "\n".join(f"  {p['pid']} {p['user']} CPU={p['cpu']}% MEM={p['mem']}% {p['command'][:80]}"
                            for p in notable[:20])
            )

        net_data = scan_data.get("network", {})
        if net_data and not net_data.get("error"):
            summary_parts.append(
                f"NETWORK: {net_data.get('connection_count', 0)} connections\n"
                + "\n".join(f"  {c['command']} (PID {c['pid']}) {c.get('name', '')}"
                            for c in net_data.get("connections", [])[:30])
            )

        fi_data = scan_data.get("file_integrity", {})
        if fi_data and not fi_data.get("error"):
            changes = fi_data.get("changes", [])
            new_files = fi_data.get("new_files", [])
            removed = fi_data.get("removed_files", [])
            fi_summary = f"FILE INTEGRITY: {fi_data.get('files_scanned', 0)} files scanned"
            if changes:
                fi_summary += f"\n  CHANGED: {', '.join(changes[:10])}"
            if new_files:
                fi_summary += f"\n  NEW: {', '.join(new_files[:10])}"
            if removed:
                fi_summary += f"\n  REMOVED: {', '.join(removed[:10])}"
            if not changes and not new_files and not removed:
                fi_summary += " — no changes"
            summary_parts.append(fi_summary)

        prompt = (
            "Analyze this system scan for security anomalies. Focus on:\n"
            "- Suspicious processes (crypto miners, reverse shells, unusual network tools)\n"
            "- Unexpected network connections (unknown outbound, unusual ports)\n"
            "- File integrity changes in system directories\n\n"
            "Respond with ONLY a JSON object: {\"anomalies\": [{\"type\": \"...\", \"detail\": \"...\", "
            "\"severity\": \"low|medium|high|critical\"}], \"summary\": \"...\"}\n"
            "If everything looks normal, return {\"anomalies\": [], \"summary\": \"All clear.\"}\n\n"
            + "\n\n".join(summary_parts)
        )

        result = await security_agent.call_llm([{"role": "user", "content": prompt}])
        return result["choices"][0]["message"].get("content", "")

    def _extract_anomalies(self, analysis: str, scan_data: dict) -> list[dict]:
        """Parse WhiteRabbitNeo's response for anomalies."""
        anomalies = []

        # Try to parse JSON response
        try:
            # Find JSON in the response
            import re
            json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                for a in parsed.get("anomalies", []):
                    anomalies.append({
                        "type": a.get("type", "unknown"),
                        "detail": a.get("detail", ""),
                        "severity": a.get("severity", "medium"),
                    })
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug("Could not parse security analysis JSON: %s", e)

        # Also check file integrity changes directly
        fi_data = scan_data.get("file_integrity", {})
        if fi_data and not fi_data.get("is_first_run"):
            if fi_data.get("changes") and self._config.get("alert_on_file_change", True):
                anomalies.append({
                    "type": "file_change",
                    "detail": f"Modified files: {', '.join(fi_data['changes'][:5])}",
                    "severity": "medium",
                })
            if fi_data.get("new_files") and self._config.get("alert_on_file_change", True):
                anomalies.append({
                    "type": "new_file",
                    "detail": f"New files: {', '.join(fi_data['new_files'][:5])}",
                    "severity": "low",
                })

        return anomalies

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "interval_seconds": self._config.get("interval_seconds", 600),
        }


class CronScheduler:
    """Cron-like self-scheduler. Agents can schedule future tasks.

    Stores jobs in SQLite. Supports interval-based, cron expressions, and one-shot scheduling.
    On each tick, checks for due jobs and dispatches them via the mission system.
    """

    def __init__(self, agent_core, db_path: str):
        self._core = agent_core
        self._db_path = db_path
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tick_interval = 30  # check every 30 seconds

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("CronScheduler started")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self):
        """Main scheduler tick loop."""
        await asyncio.sleep(10)  # initial delay
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("CronScheduler tick error: %s", e)
            await asyncio.sleep(self._tick_interval)

    async def _tick(self):
        """Check for due jobs and dispatch them."""
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE enabled = 1 AND next_run <= ? ORDER BY next_run",
                (now,),
            ).fetchall()

            for row in rows:
                job = dict(row)
                await self._dispatch_job(job)

                # Update last_run, run_count, compute next_run
                run_count = job["run_count"] + 1
                next_run = self._compute_next_run(job)

                if next_run is None:
                    # One-shot job — disable after execution
                    conn.execute(
                        "UPDATE scheduled_jobs SET last_run = ?, run_count = ?, enabled = 0 WHERE id = ?",
                        (now, run_count, job["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE scheduled_jobs SET last_run = ?, run_count = ?, next_run = ? WHERE id = ?",
                        (now, run_count, next_run, job["id"]),
                    )
                conn.commit()
        finally:
            conn.close()

    async def _dispatch_job(self, job: dict):
        """Dispatch a scheduled job via the task system."""
        description = job.get("description", "Scheduled job")
        payload = {}
        if job.get("task_payload"):
            try:
                payload = json.loads(job["task_payload"])
            except (json.JSONDecodeError, TypeError):
                pass

        plan = payload.get("plan")
        logger.info("CronScheduler dispatching job '%s' (id=%s)", description, job['id'])

        try:
            await self._core.start_task(description, plan=plan)
        except Exception as e:
            logger.error("CronScheduler job dispatch failed: %s", e)

    def _compute_next_run(self, job: dict) -> Optional[str]:
        """Compute the next run time based on schedule_type."""
        schedule_type = job.get("schedule_type", "")
        schedule_value = job.get("schedule_value", "")

        if schedule_type == "once":
            return None  # one-shot, no next run

        if schedule_type == "interval":
            try:
                interval_seconds = int(schedule_value)
                from datetime import timedelta
                next_dt = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
                return next_dt.isoformat()
            except (ValueError, TypeError):
                return None

        if schedule_type == "cron":
            return self._next_cron_run(schedule_value)

        return None

    def _next_cron_run(self, cron_expr: str) -> Optional[str]:
        """Simple cron expression parser for next run time.

        Supports: minute hour day_of_month month day_of_week
        Only handles: *, specific numbers, and */N (step) patterns.
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return None

        from datetime import timedelta
        now = datetime.now(timezone.utc)

        # Try each minute for the next 48 hours
        candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        end = now + timedelta(hours=48)

        while candidate < end:
            if self._cron_matches(parts, candidate):
                return candidate.isoformat()
            candidate += timedelta(minutes=1)

        return None

    def _cron_matches(self, parts: list[str], dt: datetime) -> bool:
        """Check if a datetime matches a cron expression."""
        values = [dt.minute, dt.hour, dt.day, dt.month, dt.isoweekday() % 7]

        for field_val, pattern in zip(values, parts):
            if pattern == "*":
                continue
            if "/" in pattern:
                base, step = pattern.split("/", 1)
                try:
                    step = int(step)
                    base_val = 0 if base == "*" else int(base)
                    if (field_val - base_val) % step != 0:
                        return False
                except (ValueError, ZeroDivisionError):
                    return False
            elif "," in pattern:
                allowed = {int(x) for x in pattern.split(",") if x.isdigit()}
                if field_val not in allowed:
                    return False
            else:
                try:
                    if field_val != int(pattern):
                        return False
                except ValueError:
                    return False
        return True

    # ── Job CRUD ──

    def create_job(self, description: str, schedule_type: str, schedule_value: str,
                   agent_id: str = "", task_payload: str = "") -> dict:
        """Create a new scheduled job."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # Compute initial next_run
        if schedule_type == "once":
            next_run = schedule_value  # ISO timestamp
        elif schedule_type == "interval":
            from datetime import timedelta
            try:
                next_dt = datetime.now(timezone.utc) + timedelta(seconds=int(schedule_value))
                next_run = next_dt.isoformat()
            except (ValueError, TypeError):
                next_run = now
        elif schedule_type == "cron":
            next_run = self._next_cron_run(schedule_value) or now
        else:
            next_run = now

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """INSERT INTO scheduled_jobs
                   (id, description, schedule_type, schedule_value, agent_id,
                    task_payload, enabled, last_run, next_run, created_at, run_count)
                   VALUES (?, ?, ?, ?, ?, ?, 1, NULL, ?, ?, 0)""",
                (job_id, description, schedule_type, schedule_value,
                 agent_id, task_payload, next_run, now),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "id": job_id,
            "description": description,
            "schedule_type": schedule_type,
            "schedule_value": schedule_value,
            "next_run": next_run,
            "created_at": now,
        }

    def list_jobs(self) -> list[dict]:
        """List all scheduled jobs."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM scheduled_jobs ORDER BY next_run").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_job(self, job_id: str) -> bool:
        """Delete a scheduled job."""
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get a single scheduled job."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_job(self, job_id: str, **kwargs) -> Optional[dict]:
        """Partial update of a scheduled job. Recomputes next_run if schedule changes."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            job = dict(row)

            allowed = {"description", "schedule_type", "schedule_value", "enabled", "agent_id", "task_payload"}
            updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
            if not updates:
                return job

            # Apply updates to local copy for next_run recomputation
            for k, v in updates.items():
                job[k] = v

            # Recompute next_run if schedule changed
            if "schedule_type" in updates or "schedule_value" in updates:
                next_run = self._compute_next_run(job)
                if next_run is None and job["schedule_type"] != "once":
                    next_run = datetime.now(timezone.utc).isoformat()
                updates["next_run"] = next_run

            # Convert enabled bool to int for SQLite
            if "enabled" in updates:
                updates["enabled"] = 1 if updates["enabled"] else 0

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [job_id]
            conn.execute(f"UPDATE scheduled_jobs SET {set_clause} WHERE id = ?", values)
            conn.commit()

            # Return updated job
            row = conn.execute("SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
