"""
AdvocateProfile — advocacy configuration management.

Determines escalation thresholds, developmental mode, and
which advocate should be contacted for which category.
"""

import logging
from typing import Optional

from profile import AdvocacyConfig, AdvocateConfig

logger = logging.getLogger(__name__)


# Profile presets
PROFILE_PRESETS = {
    "solo": {
        "description": "No external escalation. User manages everything.",
        "escalation_enabled": False,
        "default_threshold": 4,  # Only structural blocks matter
    },
    "partnered": {
        "description": "Trusted person notified at Level 3+.",
        "escalation_enabled": True,
        "default_threshold": 3,
    },
    "guided": {
        "description": "Tighter loop, more visibility. For users who want structure.",
        "escalation_enabled": True,
        "default_threshold": 2,
    },
    "custom": {
        "description": "Per-category thresholds.",
        "escalation_enabled": True,
        "default_threshold": 3,
    },
}


class AdvocateProfile:
    """Manages advocate configuration and escalation rules."""

    def __init__(self, config: AdvocacyConfig):
        self._config = config
        self._preset = PROFILE_PRESETS.get(config.profile, PROFILE_PRESETS["solo"])

    @property
    def profile_type(self) -> str:
        return self._config.profile

    @property
    def escalation_enabled(self) -> bool:
        return self._preset["escalation_enabled"] and bool(self._config.advocates)

    def should_escalate(self, pattern) -> bool:
        """Whether a pattern should be escalated to the advocate network."""
        if not self.escalation_enabled:
            return False

        # Get the threshold for this pattern's categories
        threshold = self.get_escalation_threshold(pattern.type)

        # Pattern must meet threshold AND have been dismissed at lower level
        if pattern.friction_level >= threshold:
            if pattern.dismissed or pattern.occurrences >= 3:
                return True

        return False

    def get_advocate_for(self, category: str) -> Optional[AdvocateConfig]:
        """Get the configured advocate for a category."""
        for advocate in self._config.advocates:
            if not advocate.categories or category in advocate.categories:
                return advocate
        # Fallback: first advocate handles everything
        if self._config.advocates:
            return self._config.advocates[0]
        return None

    def get_escalation_threshold(self, category: str = "") -> int:
        """Minimum friction level for escalation.
        Custom profile uses per-advocate thresholds; others use preset default."""
        if self._config.profile == "custom":
            advocate = self.get_advocate_for(category)
            if advocate:
                return advocate.escalation_threshold
        return self._preset["default_threshold"]

    def get_developmental_mode(self) -> str:
        """Determine developmental mode: explicit config > age inference > default adult."""
        # Explicit override
        if self._config.developmental.mode != "adult":
            return self._config.developmental.mode

        # Age inference
        age = self._config.user.age
        if age is not None:
            if age <= 12:
                return "child"
            elif age <= 17:
                return "adolescent"

        return "adult"

    def get_advocates(self) -> list[AdvocateConfig]:
        """Return all configured advocates."""
        return list(self._config.advocates)

    def get_status(self) -> dict:
        return {
            "profile": self._config.profile,
            "escalation_enabled": self.escalation_enabled,
            "developmental_mode": self.get_developmental_mode(),
            "advocate_count": len(self._config.advocates),
        }
