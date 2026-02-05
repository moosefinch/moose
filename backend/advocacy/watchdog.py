"""
PatternWatchdog — behavioral observation engine.

Runs in the cognitive loop's _advocate() phase. Detects patterns
like goal drift, decision contradictions, resource misallocation,
health signals, and blind spots. Only creates/updates patterns —
never surfaces them directly (that's FrictionGradient's job).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from advocacy.models import Pattern, PatternType

logger = logging.getLogger(__name__)


class PatternWatchdog:
    """Behavioral pattern detection engine."""

    def __init__(self, path: Path, patterns_cap: int = 100):
        self._path = path
        self._patterns_cap = patterns_cap
        self._patterns: dict[str, Pattern] = {}
        self._load()

    # ── Persistence ──

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for d in data:
                    pattern = Pattern.from_dict(d)
                    self._patterns[pattern.id] = pattern
                logger.info("[Watchdog] Loaded %d patterns", len(self._patterns))
            except Exception as e:
                logger.error("[Watchdog] Load error: %s", e)

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [p.to_dict() for p in self._patterns.values()]
        self._path.write_text(json.dumps(data, indent=2))

    # ── Main Analysis Entry Point ──

    async def analyze(self, observations: list[dict], goals: list,
                      memory: list[dict] = None) -> list[Pattern]:
        """Run all pattern checks. Returns new or updated patterns."""
        new_patterns = []

        drift = self._check_goal_drift(goals)
        new_patterns.extend(drift)

        contradictions = self._check_contradictions(observations, memory or [])
        new_patterns.extend(contradictions)

        misalloc = self._check_misallocation(goals, observations)
        new_patterns.extend(misalloc)

        blind = self._check_blind_spots(observations, memory or [])
        new_patterns.extend(blind)

        # Enforce cap
        self._enforce_cap()
        self._save()

        return new_patterns

    # ── Pattern Detectors ──

    def _check_goal_drift(self, goals: list) -> list[Pattern]:
        """Detect active goals with no evidence for 14+ days."""
        new_patterns = []
        now = datetime.now(timezone.utc)
        drift_threshold = timedelta(days=14)

        for goal in goals:
            if goal.status != "active":
                continue

            # Find latest evidence timestamp
            latest_evidence = None
            if goal.evidence:
                latest_evidence = max(
                    datetime.fromisoformat(e.last_observed)
                    for e in goal.evidence
                )

            if latest_evidence is None:
                # No evidence — check creation date
                created = datetime.fromisoformat(goal.created_at)
                if now - created < drift_threshold:
                    continue
            else:
                if now - latest_evidence < drift_threshold:
                    continue

            # Check if we already have a drift pattern for this goal
            existing = self._find_pattern(
                PatternType.BEHAVIORAL_DRIFT.value,
                related_goal_id=goal.id,
            )
            if existing:
                existing.occurrences += 1
                existing.last_observed = now.isoformat()
                if goal.id not in existing.evidence:
                    existing.evidence.append(
                        f"Goal '{goal.text}' has no recent activity"
                    )
            else:
                pattern = Pattern(
                    type=PatternType.BEHAVIORAL_DRIFT.value,
                    description=f"Goal '{goal.text}' has been neglected",
                    evidence=[f"No evidence recorded for 14+ days"],
                    related_goals=[goal.id],
                )
                self._patterns[pattern.id] = pattern
                new_patterns.append(pattern)

        return new_patterns

    def _check_contradictions(self, observations: list[dict],
                              memory: list[dict]) -> list[Pattern]:
        """Detect contradictions between current actions and stored positions."""
        new_patterns = []
        # Look for contradiction signals in observations
        for obs in observations:
            if obs.get("type") == "contradiction":
                description = obs.get("description", "Decision contradiction detected")
                evidence_text = obs.get("evidence", description)
                related = obs.get("related_goals", [])

                existing = self._find_pattern(
                    PatternType.CONTRADICTION.value,
                    description_contains=description[:50],
                )
                if existing:
                    existing.occurrences += 1
                    existing.last_observed = datetime.now(timezone.utc).isoformat()
                    existing.evidence.append(str(evidence_text))
                else:
                    pattern = Pattern(
                        type=PatternType.CONTRADICTION.value,
                        description=description,
                        evidence=[str(evidence_text)],
                        related_goals=related,
                    )
                    self._patterns[pattern.id] = pattern
                    new_patterns.append(pattern)

        return new_patterns

    def _check_misallocation(self, goals: list,
                             observations: list[dict]) -> list[Pattern]:
        """Detect time going to low-priority goals while high-priority ones stall."""
        new_patterns = []
        now = datetime.now(timezone.utc)

        # Find high-priority stalled goals (priority > 0.7, no evidence in 7 days)
        stalled_high = []
        active_low = []
        for goal in goals:
            if goal.status != "active":
                continue
            if goal.priority > 0.7:
                latest = None
                if goal.evidence:
                    latest = max(
                        datetime.fromisoformat(e.last_observed)
                        for e in goal.evidence
                    )
                if latest is None or (now - latest) > timedelta(days=7):
                    stalled_high.append(goal)
            elif goal.priority < 0.4:
                if goal.evidence:
                    latest = max(
                        datetime.fromisoformat(e.last_observed)
                        for e in goal.evidence
                    )
                    if latest and (now - latest) < timedelta(days=3):
                        active_low.append(goal)

        if stalled_high and active_low:
            high_names = ", ".join(g.text[:40] for g in stalled_high[:3])
            low_names = ", ".join(g.text[:40] for g in active_low[:3])

            existing = self._find_pattern(PatternType.MISALLOCATION.value)
            if existing:
                existing.occurrences += 1
                existing.last_observed = now.isoformat()
                existing.evidence.append(
                    f"High-priority stalled: {high_names}; Active low-priority: {low_names}"
                )
                existing.related_goals = [g.id for g in stalled_high + active_low]
            else:
                pattern = Pattern(
                    type=PatternType.MISALLOCATION.value,
                    description=(
                        f"High-priority goals stalling while low-priority goals get attention"
                    ),
                    evidence=[
                        f"Stalled high-priority: {high_names}",
                        f"Active low-priority: {low_names}",
                    ],
                    related_goals=[g.id for g in stalled_high + active_low],
                )
                self._patterns[pattern.id] = pattern
                new_patterns.append(pattern)

        return new_patterns

    def _check_blind_spots(self, observations: list[dict],
                           memory: list[dict]) -> list[Pattern]:
        """Detect recurring mistake patterns (same class recurs 3+ times)."""
        new_patterns = []

        # Look for error/mistake observations
        mistakes = [
            o for o in observations
            if o.get("type") in ("error", "mistake", "blindspot")
        ]

        for mistake in mistakes:
            category = mistake.get("category", "unknown")
            description = mistake.get("description", "Recurring mistake pattern")

            existing = self._find_pattern(
                PatternType.BLINDSPOT.value,
                description_contains=category,
            )
            if existing:
                existing.occurrences += 1
                existing.last_observed = datetime.now(timezone.utc).isoformat()
                existing.evidence.append(str(mistake.get("evidence", description)))
            else:
                pattern = Pattern(
                    type=PatternType.BLINDSPOT.value,
                    description=description,
                    evidence=[str(mistake.get("evidence", description))],
                    occurrences=1,
                )
                self._patterns[pattern.id] = pattern
                new_patterns.append(pattern)

        return new_patterns

    # ── Query API ──

    def get_pattern(self, pattern_id: str) -> Optional[Pattern]:
        return self._patterns.get(pattern_id)

    def get_active_patterns(self) -> list[Pattern]:
        """Return non-dismissed patterns sorted by friction level (highest first)."""
        active = [
            p for p in self._patterns.values()
            if not p.dismissed
        ]
        active.sort(key=lambda p: p.friction_level, reverse=True)
        return active

    def get_patterns_for_goal(self, goal_id: str) -> list[Pattern]:
        return [
            p for p in self._patterns.values()
            if goal_id in p.related_goals
        ]

    def all_patterns(self) -> list[Pattern]:
        return list(self._patterns.values())

    # ── Internal Helpers ──

    def _find_pattern(self, pattern_type: str,
                      related_goal_id: Optional[str] = None,
                      description_contains: Optional[str] = None) -> Optional[Pattern]:
        """Find an existing active pattern matching criteria."""
        for p in self._patterns.values():
            if p.type != pattern_type:
                continue
            if p.dismissed:
                continue
            if related_goal_id and related_goal_id not in p.related_goals:
                continue
            if description_contains and description_contains.lower() not in p.description.lower():
                continue
            return p
        return None

    def _enforce_cap(self):
        """Remove oldest dismissed patterns when over cap."""
        if len(self._patterns) <= self._patterns_cap:
            return
        # Remove oldest dismissed first
        dismissed = sorted(
            [p for p in self._patterns.values() if p.dismissed],
            key=lambda p: p.last_observed,
        )
        while len(self._patterns) > self._patterns_cap and dismissed:
            old = dismissed.pop(0)
            del self._patterns[old.id]
