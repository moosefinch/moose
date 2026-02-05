"""
Advocacy data models — Goal, Pattern, FrictionEvent, Evidence.

Shared dataclasses used across the advocacy subsystem.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid


class GoalCategory(str, Enum):
    CAREER = "career"
    HEALTH = "health"
    RELATIONSHIPS = "relationships"
    FINANCIAL = "financial"
    PERSONAL_GROWTH = "personal_growth"
    CREATIVE = "creative"
    EDUCATION = "education"
    COMMUNITY = "community"
    SPIRITUAL = "spiritual"
    OTHER = "other"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class PatternType(str, Enum):
    BEHAVIORAL_DRIFT = "behavioral_drift"
    CONTRADICTION = "contradiction"
    MISALLOCATION = "misallocation"
    HEALTH = "health"
    BLINDSPOT = "blindspot"


@dataclass
class Evidence:
    type: str
    description: str
    last_observed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "description": self.description,
            "last_observed": self.last_observed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        return cls(
            type=d["type"],
            description=d["description"],
            last_observed=d.get(
                "last_observed", datetime.now(timezone.utc).isoformat()
            ),
        )


@dataclass
class Goal:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    text: str = ""
    category: str = GoalCategory.OTHER.value
    priority: float = 0.5  # 0-1
    parent_id: Optional[str] = None
    tensions: list[str] = field(default_factory=list)  # conflicting goal IDs
    status: str = GoalStatus.ACTIVE.value
    evidence: list[Evidence] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    inferred: bool = False
    confirmed: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "category": self.category,
            "priority": self.priority,
            "parent_id": self.parent_id,
            "tensions": self.tensions,
            "status": self.status,
            "evidence": [e.to_dict() for e in self.evidence],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "inferred": self.inferred,
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Goal":
        return cls(
            id=d["id"],
            text=d["text"],
            category=d.get("category", GoalCategory.OTHER.value),
            priority=d.get("priority", 0.5),
            parent_id=d.get("parent_id"),
            tensions=d.get("tensions", []),
            status=d.get("status", GoalStatus.ACTIVE.value),
            evidence=[Evidence.from_dict(e) for e in d.get("evidence", [])],
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=d.get("updated_at", datetime.now(timezone.utc).isoformat()),
            inferred=d.get("inferred", False),
            confirmed=d.get("confirmed", True),
        )


@dataclass
class Pattern:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    type: str = PatternType.BEHAVIORAL_DRIFT.value
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    first_observed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_observed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    occurrences: int = 1
    friction_level: int = 0  # 0-4
    last_surfaced: Optional[str] = None
    dismissed: bool = False
    dismissed_at: Optional[str] = None
    cooloff_until: Optional[str] = None
    escalated: bool = False
    related_goals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "evidence": self.evidence,
            "first_observed": self.first_observed,
            "last_observed": self.last_observed,
            "occurrences": self.occurrences,
            "friction_level": self.friction_level,
            "last_surfaced": self.last_surfaced,
            "dismissed": self.dismissed,
            "dismissed_at": self.dismissed_at,
            "cooloff_until": self.cooloff_until,
            "escalated": self.escalated,
            "related_goals": self.related_goals,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Pattern":
        return cls(
            id=d["id"],
            type=d.get("type", PatternType.BEHAVIORAL_DRIFT.value),
            description=d.get("description", ""),
            evidence=d.get("evidence", []),
            first_observed=d.get(
                "first_observed", datetime.now(timezone.utc).isoformat()
            ),
            last_observed=d.get(
                "last_observed", datetime.now(timezone.utc).isoformat()
            ),
            occurrences=d.get("occurrences", 1),
            friction_level=d.get("friction_level", 0),
            last_surfaced=d.get("last_surfaced"),
            dismissed=d.get("dismissed", False),
            dismissed_at=d.get("dismissed_at"),
            cooloff_until=d.get("cooloff_until"),
            escalated=d.get("escalated", False),
            related_goals=d.get("related_goals", []),
        )
