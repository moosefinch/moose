"""
OutreachEngine — persistent background workflow engine.
Checks campaigns every 5 minutes, drives outreach work.
All state in SQLite — survives restarts.
"""

import asyncio
import json
import logging
import time
from typing import Optional

from db import db_connection_row
from tools_outreach import get_next_actions

logger = logging.getLogger(__name__)

# Action types that can auto-trigger background tasks
_AUTO_TASK_ACTION_TYPES = {"follow_up", "research"}
_MAX_AUTO_TASKS_PER_CYCLE = 2


class OutreachEngine:
    def __init__(self, check_interval: float = 300.0):
        self.check_interval = check_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._ws_broadcast = None
        self._task_creator = None
        self.max_auto_tasks_per_cycle = _MAX_AUTO_TASKS_PER_CYCLE

    def set_ws_broadcast(self, callback):
        self._ws_broadcast = callback

    def set_task_creator(self, callback):
        """Set the callback for creating autonomous background tasks.
        Expected signature: async def task_creator(description: str) -> Any"""
        self._task_creator = callback

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[OutreachEngine] Started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[OutreachEngine] Stopped")

    async def _run_loop(self):
        while self.running:
            try:
                await self._check_campaigns()
            except Exception as e:
                logger.error("[OutreachEngine] Error: %s", e)
            await asyncio.sleep(self.check_interval)

    async def _check_campaigns(self):
        with db_connection_row() as conn:
            campaigns = conn.execute("SELECT id, name FROM campaigns WHERE status = 'active'").fetchall()
        auto_tasks_created = 0
        for cam in campaigns:
            result = json.loads(get_next_actions(cam["id"]))
            actions = result.get("actions", [])
            if actions and self._ws_broadcast:
                await self._ws_broadcast({
                    "type": "outreach_notification",
                    "campaign_id": cam["id"],
                    "campaign_name": cam["name"],
                    "pending_actions": len(actions),
                    "top_action": actions[0] if actions else None,
                })
            # Auto-trigger tasks for high-priority actions (follow_up, research only)
            if self._task_creator and actions:
                high_priority = [a for a in actions
                                 if a.get("priority") == "high"
                                 and a.get("type") in _AUTO_TASK_ACTION_TYPES]
                for action in high_priority:
                    if auto_tasks_created >= self.max_auto_tasks_per_cycle:
                        break
                    try:
                        desc = f"[Auto] {action['description']} (campaign: {cam['name']})"
                        await self._task_creator(desc)
                        auto_tasks_created += 1
                        logger.info("[OutreachEngine] Auto-created task: %s", desc)
                    except Exception as e:
                        logger.error("[OutreachEngine] Failed to auto-create task: %s", e)

    async def handle_inbound_lead(self, lead_data: dict):
        """Handle a new inbound lead — broadcast notification and create briefing."""
        name = lead_data.get("name", "Unknown")
        company = lead_data.get("company", "Unknown")
        email = lead_data.get("email", "")
        message = lead_data.get("message", "")
        source = lead_data.get("source", "website")

        notification = {
            "type": "lead_received",
            "lead": {
                "name": name,
                "company": company,
                "email": email,
                "source": source,
                "message": message[:200],
            },
        }
        if self._ws_broadcast:
            await self._ws_broadcast(notification)

        # Create a briefing for the lead
        briefing_content = f"**New inbound lead** from {source}:\n- **Name:** {name}\n- **Company:** {company}\n- **Email:** {email}"
        if message:
            briefing_content += f"\n- **Message:** {message[:300]}"

        if self._ws_broadcast:
            import uuid
            from datetime import datetime, timezone
            briefing = {
                "id": str(uuid.uuid4())[:12],
                "task_id": None,
                "content": briefing_content,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "read": False,
            }
            await self._ws_broadcast({"type": "briefing", "data": briefing})

    async def resume_campaign_work(self, campaign_id: str) -> dict:
        result = json.loads(get_next_actions(campaign_id))
        actions = result.get("actions", [])
        if not actions:
            return {"message": "No pending actions"}
        return {"message": f"Found {len(actions)} actions", "actions": actions}


_engine: Optional[OutreachEngine] = None

def get_outreach_engine() -> OutreachEngine:
    global _engine
    if _engine is None:
        _engine = OutreachEngine()
    return _engine
