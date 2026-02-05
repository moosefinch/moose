"""
GoalGraph — persistent goal hierarchy with JSON storage.

Manages the user's goal tree: adding, inferring, confirming,
prioritizing, recording evidence, detecting tensions and neglect.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from advocacy.models import Evidence, Goal, GoalStatus

logger = logging.getLogger(__name__)


class GoalGraph:
    """Persistent, capped goal hierarchy stored as JSON."""

    def __init__(self, path: Path, goals_cap: int = 50):
        self._path = path
        self._goals_cap = goals_cap
        self._goals: dict[str, Goal] = {}
        self._load()

    # ── Persistence ──

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for d in data:
                    goal = Goal.from_dict(d)
                    self._goals[goal.id] = goal
                logger.info("[GoalGraph] Loaded %d goals", len(self._goals))
            except Exception as e:
                logger.error("[GoalGraph] Load error: %s", e)

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [g.to_dict() for g in self._goals.values()]
        self._path.write_text(json.dumps(data, indent=2))

    # ── Public API ──

    def add_goal(
        self,
        text: str,
        category: str = "other",
        priority: float = 0.5,
        parent_id: Optional[str] = None,
    ) -> Goal:
        """Create a confirmed goal. Returns the new Goal."""
        if self._active_count() >= self._goals_cap:
            raise ValueError(
                f"Active goal cap ({self._goals_cap}) reached. "
                "Complete or abandon existing goals first."
            )
        goal = Goal(
            text=text,
            category=category,
            priority=max(0.0, min(1.0, priority)),
            parent_id=parent_id,
            inferred=False,
            confirmed=True,
        )
        self._goals[goal.id] = goal
        self._save()
        return goal

    def infer_goal(
        self,
        text: str,
        category: str = "other",
        evidence: Optional[Evidence] = None,
    ) -> Goal:
        """Create an unconfirmed, inferred goal."""
        if self._active_count() >= self._goals_cap:
            raise ValueError(
                f"Active goal cap ({self._goals_cap}) reached."
            )
        goal = Goal(
            text=text,
            category=category,
            priority=0.3,  # inferred goals start lower
            inferred=True,
            confirmed=False,
        )
        if evidence:
            goal.evidence.append(evidence)
        self._goals[goal.id] = goal
        self._save()
        return goal

    def confirm_goal(self, goal_id: str) -> bool:
        """Confirm an inferred goal."""
        goal = self._goals.get(goal_id)
        if not goal or not goal.inferred:
            return False
        goal.confirmed = True
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def reject_goal(self, goal_id: str) -> bool:
        """Reject an inferred goal — marks it abandoned."""
        goal = self._goals.get(goal_id)
        if not goal or not goal.inferred:
            return False
        goal.status = GoalStatus.ABANDONED.value
        goal.confirmed = False
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def update_priority(self, goal_id: str, priority: float) -> bool:
        """Update a goal's priority (0-1)."""
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        goal.priority = max(0.0, min(1.0, priority))
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def update_status(self, goal_id: str, status: str) -> bool:
        """Update a goal's status."""
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        if status not in (s.value for s in GoalStatus):
            return False
        goal.status = status
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def add_tension(self, id_a: str, id_b: str) -> bool:
        """Record a tension between two goals."""
        goal_a = self._goals.get(id_a)
        goal_b = self._goals.get(id_b)
        if not goal_a or not goal_b:
            return False
        if id_b not in goal_a.tensions:
            goal_a.tensions.append(id_b)
        if id_a not in goal_b.tensions:
            goal_b.tensions.append(id_a)
        goal_a.updated_at = datetime.now(timezone.utc).isoformat()
        goal_b.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a single goal by ID."""
        return self._goals.get(goal_id)

    def get_active_goals(self) -> list[Goal]:
        """Return active goals sorted by priority (highest first)."""
        active = [
            g for g in self._goals.values()
            if g.status == GoalStatus.ACTIVE.value
        ]
        active.sort(key=lambda g: g.priority, reverse=True)
        return active

    def get_unconfirmed_goals(self) -> list[Goal]:
        """Return inferred goals pending confirmation."""
        return [
            g for g in self._goals.values()
            if g.inferred and not g.confirmed
            and g.status == GoalStatus.ACTIVE.value
        ]

    def get_tensions_for(self, goal_id: str) -> list[Goal]:
        """Return conflicting goals for a given goal."""
        goal = self._goals.get(goal_id)
        if not goal:
            return []
        return [
            self._goals[tid]
            for tid in goal.tensions
            if tid in self._goals
        ]

    def record_evidence(self, goal_id: str, evidence: Evidence) -> bool:
        """Add evidence to a goal, updates last_observed."""
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        goal.evidence.append(evidence)
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def neglected_goals(self, days: int = 7) -> list[Goal]:
        """Active goals with no evidence in the last N days."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()
        result = []
        for goal in self.get_active_goals():
            if not goal.evidence:
                # No evidence at all — check if created before cutoff
                if goal.created_at < cutoff:
                    result.append(goal)
            else:
                latest = max(e.last_observed for e in goal.evidence)
                if latest < cutoff:
                    result.append(goal)
        return result

    def get_children(self, parent_id: str) -> list[Goal]:
        """Return child goals of a parent."""
        return [
            g for g in self._goals.values()
            if g.parent_id == parent_id
        ]

    def all_goals(self) -> list[Goal]:
        """Return all goals regardless of status."""
        return list(self._goals.values())

    # ── Internal ──

    def _active_count(self) -> int:
        return sum(
            1 for g in self._goals.values()
            if g.status == GoalStatus.ACTIVE.value
        )
