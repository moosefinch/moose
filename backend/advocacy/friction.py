"""
FrictionGradient — intervention control for the advocacy subsystem.

Assigns friction levels (0-4) to patterns and controls when/how
they're surfaced in conversation. Enforces anti-nag rules.

Levels:
  0 — Silent: Pattern noticed, signal weak. Stored, nothing said.
  1 — Ambient: Clear but not urgent. Weave context into normal responses.
  2 — Gentle flag: Clear and actionable. Raise ONCE. 14-day cooloff if dismissed.
  3 — Hard flag: Safety/high-stakes. Say it clearly whether user wants to hear it.
  4 — Structural block: Irreversible harm. Require explicit confirmation.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from advocacy.models import Pattern, PatternType

logger = logging.getLogger(__name__)

# Friction level constants
SILENT = 0
AMBIENT = 1
GENTLE_FLAG = 2
HARD_FLAG = 3
STRUCTURAL_BLOCK = 4


class FrictionGradient:
    """Controls when and how patterns are surfaced to the user."""

    def __init__(self, path: Path, cooloff_days: int = 14,
                 max_flags_per_day: int = 3):
        self._path = path
        self._cooloff_days = cooloff_days
        self._max_flags_per_day = max_flags_per_day
        self._surfaced_today: list[str] = []  # pattern IDs surfaced today
        self._surfaced_date: Optional[str] = None
        self._queue: list[Pattern] = []  # patterns queued for next response
        self._state: dict = {}
        self._load()

    # ── Persistence ──

    def _load(self):
        if self._path.exists():
            try:
                self._state = json.loads(self._path.read_text())
                self._surfaced_today = self._state.get("surfaced_today", [])
                self._surfaced_date = self._state.get("surfaced_date")
            except Exception as e:
                logger.error("[Friction] Load error: %s", e)

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state["surfaced_today"] = self._surfaced_today
        self._state["surfaced_date"] = self._surfaced_date
        self._path.write_text(json.dumps(self._state, indent=2))

    # ── Level Assignment ──

    def assign_level(self, pattern: Pattern) -> int:
        """Determine friction level from pattern characteristics."""
        # Safety patterns always get higher levels
        if pattern.type == PatternType.HEALTH.value:
            if pattern.occurrences >= 3:
                return HARD_FLAG
            return GENTLE_FLAG

        # Structural block for patterns explicitly marked
        if pattern.friction_level == STRUCTURAL_BLOCK:
            return STRUCTURAL_BLOCK

        # Base level from occurrences and type
        if pattern.occurrences >= 5:
            level = HARD_FLAG
        elif pattern.occurrences >= 3:
            level = GENTLE_FLAG
        elif pattern.occurrences >= 2:
            level = AMBIENT
        else:
            level = SILENT

        # Contradictions escalate faster
        if pattern.type == PatternType.CONTRADICTION.value and level < GENTLE_FLAG:
            level = min(level + 1, GENTLE_FLAG)

        # Misallocation with high-priority goals escalates
        if pattern.type == PatternType.MISALLOCATION.value and pattern.occurrences >= 2:
            level = max(level, GENTLE_FLAG)

        # Worsened during cooloff → escalate to HARD_FLAG
        if pattern.cooloff_until:
            cooloff_end = datetime.fromisoformat(pattern.cooloff_until)
            now = datetime.now(timezone.utc)
            if now < cooloff_end and pattern.occurrences > 3:
                level = max(level, HARD_FLAG)

        pattern.friction_level = level
        return level

    # ── Surfacing Queue ──

    def queue_for_surfacing(self, patterns: list[Pattern]) -> list[Pattern]:
        """Queue Level 1+ patterns for next interaction. Returns queued patterns.
        Respects anti-nag rules and daily caps."""
        self._reset_daily_counter()
        queued = []

        for pattern in patterns:
            level = pattern.friction_level
            if level < AMBIENT:
                continue

            # Anti-nag: check cooloff
            if self._in_cooloff(pattern):
                # Exception: worsened during cooloff can come back at HARD_FLAG
                if level >= HARD_FLAG:
                    pass  # Allow through
                else:
                    continue

            # Anti-nag: check daily cap (Level 4 exempted)
            if level < STRUCTURAL_BLOCK and self._daily_cap_reached():
                continue

            queued.append(pattern)

        # Anti-nag: only ONE advocacy observation per conversation turn
        # Sort by level (highest first), take the most important one
        queued.sort(key=lambda p: p.friction_level, reverse=True)
        if queued:
            self._queue = [queued[0]]
        else:
            self._queue = []

        return self._queue

    def get_advocacy_context(self, conversation_topic: str = "",
                             response_content: str = "") -> Optional[str]:
        """Return context string for the next response, or None.
        Consumes the queue."""
        if not self._queue:
            return None

        pattern = self._queue[0]
        level = pattern.friction_level

        # Record surfacing
        self._record_surfacing(pattern)
        self._queue = []

        if level == AMBIENT:
            return self._format_ambient(pattern)
        elif level == GENTLE_FLAG:
            return self._format_gentle_flag(pattern)
        elif level == HARD_FLAG:
            return self._format_hard_flag(pattern)
        elif level == STRUCTURAL_BLOCK:
            return self._format_structural_block(pattern)

        return None

    # ── Dismissal ──

    def dismiss(self, pattern: Pattern) -> None:
        """Handle user dismissal of a pattern. Applies cooloff."""
        now = datetime.now(timezone.utc)
        pattern.dismissed = True
        pattern.dismissed_at = now.isoformat()

        if pattern.friction_level <= GENTLE_FLAG:
            # Dismissed Level 2 → Level 0 for cooloff duration
            pattern.friction_level = SILENT
            pattern.cooloff_until = (
                now + timedelta(days=self._cooloff_days)
            ).isoformat()
        elif pattern.friction_level == HARD_FLAG:
            # Dismissed Level 3 → dropped entirely unless new evidence
            pattern.cooloff_until = (
                now + timedelta(days=self._cooloff_days)
            ).isoformat()
        # Level 4 is the ONLY exception to respecting dismissal
        # It stays active regardless

        self._save()

    def undismiss(self, pattern: Pattern) -> None:
        """Re-activate a dismissed pattern (e.g., new evidence found)."""
        pattern.dismissed = False
        pattern.dismissed_at = None
        pattern.cooloff_until = None
        self._save()

    # ── Anti-Nag Internals ──

    def _in_cooloff(self, pattern: Pattern) -> bool:
        """Check if pattern is in cooloff period."""
        if not pattern.cooloff_until:
            return False
        cooloff_end = datetime.fromisoformat(pattern.cooloff_until)
        return datetime.now(timezone.utc) < cooloff_end

    def _daily_cap_reached(self) -> bool:
        """Check if we've hit the daily flag limit."""
        self._reset_daily_counter()
        return len(self._surfaced_today) >= self._max_flags_per_day

    def _reset_daily_counter(self):
        """Reset the daily counter if it's a new day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._surfaced_date != today:
            self._surfaced_today = []
            self._surfaced_date = today

    def _record_surfacing(self, pattern: Pattern):
        """Record that a pattern was surfaced."""
        self._reset_daily_counter()
        pattern.last_surfaced = datetime.now(timezone.utc).isoformat()
        self._surfaced_today.append(pattern.id)
        self._save()

    # ── Formatting ──

    def _format_ambient(self, pattern: Pattern) -> str:
        """Level 1: context to weave into response naturally."""
        return f"[advocacy-context] {pattern.description}"

    def _format_gentle_flag(self, pattern: Pattern) -> str:
        """Level 2: clear, conversational flag."""
        return (
            f"\n\n---\n"
            f"Something worth noting: {pattern.description}\n"
            f"(Observed {pattern.occurrences} time(s). "
            f"You can dismiss this if it's not relevant.)"
        )

    def _format_hard_flag(self, pattern: Pattern) -> str:
        """Level 3: direct, clear statement."""
        return (
            f"\n\n---\n"
            f"**I need to flag something:** {pattern.description}\n\n"
            f"This has come up {pattern.occurrences} time(s). "
            f"I'm raising this because it seems important enough to address directly."
        )

    def _format_structural_block(self, pattern: Pattern) -> str:
        """Level 4: warning requiring explicit confirmation."""
        return (
            f"\n\n---\n"
            f"**IMPORTANT — Please read before proceeding:**\n\n"
            f"{pattern.description}\n\n"
            f"This requires your explicit confirmation to continue. "
            f"I cannot proceed without your acknowledgment."
        )

    # ── Status ──

    def get_status(self) -> dict:
        return {
            "flags_today": len(self._surfaced_today),
            "max_flags_per_day": self._max_flags_per_day,
            "queued": len(self._queue),
            "cooloff_days": self._cooloff_days,
        }
