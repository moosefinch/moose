"""
DevelopmentalCalibration — age-appropriate advocacy behavior.

Three modes:
  - Child (6-12): Warm, patient, proactive check-ins. Parent sees summaries.
    Child told when shared. Safety → immediate parent notification.
  - Adolescent (13-17): Respectful, direct. Growing independence. Parent sees
    themes not specifics. Support directly first, escalate if persistent.
  - Adult: Full range. Peer-to-peer. Advocate network optional.
"""

import logging
from typing import Optional

from profile import AdvocacyConfig

logger = logging.getLogger(__name__)

# Developmental mode context injected into presentation prompts
_MODE_CONTEXTS = {
    "child": {
        "tone": "warm, patient, encouraging",
        "approach": (
            "Use simple, clear language. Be proactive with check-ins. "
            "Celebrate small wins. Never be condescending — children are perceptive. "
            "When sharing with parents, always tell the child what you're sharing and why. "
            "Privacy is the default. Only break privacy for immediate safety concerns."
        ),
        "escalation": (
            "Safety concerns trigger immediate parent notification. "
            "Regular summaries (themes, not specifics) shared with parent. "
            "Child is always told when information is shared."
        ),
        "check_in_frequency": "proactive",
        "parent_visibility": "summaries",
    },
    "adolescent": {
        "tone": "respectful, direct, peer-like",
        "approach": (
            "Treat them as a growing adult. Be direct but not preachy. "
            "Respect their growing independence. Support them directly first. "
            "Only escalate to parents if a pattern persists or safety is at risk. "
            "Privacy is the default — only break for immediate safety."
        ),
        "escalation": (
            "Try to support directly first. Escalate to parent only if "
            "pattern persists after direct support or safety is at risk. "
            "Parent sees themes, not specific conversations."
        ),
        "check_in_frequency": "moderate",
        "parent_visibility": "themes",
    },
    "adult": {
        "tone": "peer-to-peer, direct, honest",
        "approach": (
            "Full advocacy range. Direct, honest communication. "
            "Advocate network is optional and user-controlled. "
            "Respect autonomy completely."
        ),
        "escalation": (
            "Escalate only through configured advocate network. "
            "User controls all escalation settings."
        ),
        "check_in_frequency": "user-driven",
        "parent_visibility": "none",
    },
}


class DevelopmentalCalibration:
    """Age-appropriate advocacy behavior calibration."""

    def __init__(self, config: AdvocacyConfig):
        self._config = config
        self._mode = self._determine_mode()

    @property
    def mode(self) -> str:
        return self._mode

    def _determine_mode(self) -> str:
        """Explicit override > age inference > default adult."""
        # Explicit mode override
        if self._config.developmental.mode in ("child", "adolescent"):
            return self._config.developmental.mode

        # Age inference
        age = self._config.user.age
        if age is not None:
            if age <= 12:
                return "child"
            elif age <= 17:
                return "adolescent"

        return "adult"

    def get_developmental_context(self) -> str:
        """Return prompt context string for the presentation layer."""
        ctx = _MODE_CONTEXTS.get(self._mode, _MODE_CONTEXTS["adult"])
        lines = [
            f"## Developmental Mode: {self._mode.title()}",
            f"",
            f"**Tone:** {ctx['tone']}",
            f"",
            f"**Approach:** {ctx['approach']}",
            f"",
            f"**Escalation rules:** {ctx['escalation']}",
        ]
        return "\n".join(lines)

    def get_mode_config(self) -> dict:
        """Return the full mode configuration dict."""
        return dict(_MODE_CONTEXTS.get(self._mode, _MODE_CONTEXTS["adult"]))

    def should_notify_parent(self, is_safety_concern: bool = False,
                             pattern_persistent: bool = False) -> bool:
        """Whether to notify parent/guardian based on mode and situation."""
        if self._mode == "adult":
            return False
        if is_safety_concern:
            return True  # Always for safety, regardless of mode
        if self._mode == "child":
            return True  # Parents get regular summaries for children
        if self._mode == "adolescent" and pattern_persistent:
            return True  # Escalate persistent patterns for adolescents
        return False

    def get_parent_visibility(self) -> str:
        """What level of detail parents should see."""
        ctx = _MODE_CONTEXTS.get(self._mode, _MODE_CONTEXTS["adult"])
        return ctx["parent_visibility"]

    def get_status(self) -> dict:
        return {
            "mode": self._mode,
            "check_in_frequency": _MODE_CONTEXTS.get(
                self._mode, _MODE_CONTEXTS["adult"]
            )["check_in_frequency"],
        }
