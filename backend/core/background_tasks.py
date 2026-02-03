"""
Background Tasks — Long-running autonomous task management.
Extracted from core.py for modularity.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional


class BackgroundTask:
    """Represents an autonomous long-running task."""

    def __init__(self, task_id: str, description: str, plan: list[dict]):
        self.id = task_id
        self.description = description
        self.plan = plan
        self.status = "running"  # running, completed, failed, cancelled
        self.progress_log: list[dict] = []
        self.result: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self._task: Optional[asyncio.Task] = None

    def log(self, message: str, step: Optional[str] = None):
        """Log progress for this task."""
        self.progress_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "message": message,
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Convert task to serializable dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "plan": self.plan,
            "progress_log": self.progress_log,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
