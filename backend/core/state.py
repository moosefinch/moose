"""
State persistence — load/save state.json and SOUL.md context.
Extracted from agent_core.py for modularity.
"""

import json
import logging
import time
from datetime import datetime, timezone

from config import STATE_DIR, STATE_FILE_PATH, SOUL_FILE_PATH
from profile import get_profile

logger = logging.getLogger(__name__)


class _StateMixin:
    """Mixin providing persistent state and SOUL.md management for AgentCore."""

    def _load_state(self) -> dict:
        """Load persistent state from state.json."""
        try:
            if STATE_FILE_PATH.exists():
                return json.loads(STATE_FILE_PATH.read_text())
        except Exception as e:
            logger.warning("[Core] Failed to load state: %s", e)
        return {
            "last_shutdown": None,
            "last_startup": None,
            "uptime_seconds": 0,
            "active_monitors": [],
            "last_5_tasks": [],
            "security_heartbeat": {
                "last_scan": None,
                "anomalies_found": 0,
                "scan_count": 0,
            },
            "cognitive_loop": {
                "cycle_count": 0,
                "last_briefing_type": None,
                "last_briefing_date": None,
            },
        }

    def _save_state(self):
        """Write persistent state to state.json and SOUL.md."""
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)

            # Update uptime
            if self._startup_time:
                self._state["uptime_seconds"] += int(time.time() - self._startup_time)

            self._state["last_shutdown"] = datetime.now(timezone.utc).isoformat()

            # Capture last 5 tasks
            recent_tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.updated_at,
                reverse=True,
            )[:5]
            self._state["last_5_tasks"] = [
                {
                    "id": t.id,
                    "description": t.description[:200],
                    "status": t.status,
                    "timestamp": t.updated_at,
                }
                for t in recent_tasks
            ]

            # Capture active monitors
            monitors = []
            if hasattr(self, '_security_heartbeat') and self._security_heartbeat:
                monitors.append("security_heartbeat")
            if self.cognitive_loop:
                monitors.append("cognitive_loop")
            self._state["active_monitors"] = monitors

            # Cognitive loop stats
            if self.cognitive_loop:
                status = self.cognitive_loop.get_status()
                self._state["cognitive_loop"]["cycle_count"] = status.get("cycle_count", 0)

            STATE_FILE_PATH.write_text(json.dumps(self._state, indent=2))

            # Write SOUL.md
            self._write_soul()

            logger.info("[Core] State saved")
        except Exception as e:
            logger.warning("[Core] Failed to save state: %s", e)

    def _write_soul(self):
        """Write SOUL.md — LLM-readable narrative context for continuity."""
        profile = get_profile()
        system_name = profile.system.name or "Assistant"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        state = self._state

        # Build recent context
        task_lines = []
        for t in state.get("last_5_tasks", []):
            task_lines.append(f"- [{t['status']}] {t['description']}")

        hb = state.get("security_heartbeat", {})
        monitors = state.get("active_monitors", [])
        cog = state.get("cognitive_loop", {})
        uptime_hrs = round(state.get("uptime_seconds", 0) / 3600, 1)

        soul = f"""# {system_name} Soul — Last Updated {now}

## Current Focus
Monitoring system security and managing tasks. Total uptime: {uptime_hrs} hours.

## Recent Context
{chr(10).join(task_lines) if task_lines else "- No recent tasks."}

## Security Heartbeat
- Scans completed: {hb.get('scan_count', 0)}
- Last scan: {hb.get('last_scan', 'never')}
- Anomalies found: {hb.get('anomalies_found', 0)}

## Active Watches
{chr(10).join(f'- {m}' for m in monitors) if monitors else '- None active.'}

## Cognitive Loop
- Cycles: {cog.get('cycle_count', 0)}
- Last briefing: {cog.get('last_briefing_type', 'none')} on {cog.get('last_briefing_date', 'N/A')}
"""
        try:
            SOUL_FILE_PATH.write_text(soul)
        except Exception as e:
            logger.warning("[%s] Failed to write SOUL.md: %s", system_name, e)

    def _load_soul(self) -> str:
        """Load SOUL.md for presentation layer context injection."""
        try:
            if SOUL_FILE_PATH.exists():
                return SOUL_FILE_PATH.read_text()
        except Exception as e:
            logger.warning("Failed to load SOUL.md: %s", e)
        return ""
