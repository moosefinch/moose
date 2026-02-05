"""Tests for PatternWatchdog."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from advocacy.models import Evidence, Goal, GoalStatus, Pattern, PatternType
from advocacy.watchdog import PatternWatchdog


def _make_goal(text="Test Goal", priority=0.5, status="active",
               evidence_days_ago=None, created_days_ago=0):
    """Helper to create a goal with optional old evidence."""
    now = datetime.now(timezone.utc)
    created = (now - timedelta(days=created_days_ago)).isoformat()
    goal = Goal(text=text, priority=priority, status=status, created_at=created)
    if evidence_days_ago is not None:
        obs_time = (now - timedelta(days=evidence_days_ago)).isoformat()
        goal.evidence.append(
            Evidence(type="test", description="test evidence", last_observed=obs_time)
        )
    return goal


class TestPatternWatchdog:
    def test_persistence(self, patterns_path):
        w1 = PatternWatchdog(patterns_path)
        p = Pattern(
            type=PatternType.BEHAVIORAL_DRIFT.value,
            description="test pattern",
        )
        w1._patterns[p.id] = p
        w1._save()

        w2 = PatternWatchdog(patterns_path)
        assert len(w2.all_patterns()) == 1
        assert w2.all_patterns()[0].description == "test pattern"

    def test_goal_drift_detected(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        # Goal with old evidence (20 days ago)
        goal = _make_goal("Exercise", evidence_days_ago=20, created_days_ago=20)
        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [goal])
        )
        assert len(patterns) == 1
        assert patterns[0].type == PatternType.BEHAVIORAL_DRIFT.value
        assert "Exercise" in patterns[0].description

    def test_no_drift_for_recent_goals(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        goal = _make_goal("New goal", evidence_days_ago=2, created_days_ago=5)
        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [goal])
        )
        assert len(patterns) == 0

    def test_no_drift_for_new_goal_without_evidence(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        goal = _make_goal("Brand new", created_days_ago=3)
        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [goal])
        )
        assert len(patterns) == 0

    def test_drift_increments_occurrences(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        goal = _make_goal("Stale goal", evidence_days_ago=20, created_days_ago=30)

        asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [goal])
        )
        asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [goal])
        )

        patterns = watchdog.get_active_patterns()
        assert len(patterns) == 1
        assert patterns[0].occurrences == 2

    def test_contradiction_detected(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        observations = [{
            "type": "contradiction",
            "description": "Said save money but bought luxury item",
            "evidence": "Spending contradicts saving goal",
            "related_goals": ["g1"],
        }]
        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze(observations, [])
        )
        assert len(patterns) == 1
        assert patterns[0].type == PatternType.CONTRADICTION.value

    def test_misallocation_detected(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        # High priority goal, stalled (no evidence in 10 days)
        high = _make_goal("Important project", priority=0.9,
                          evidence_days_ago=10, created_days_ago=20)
        # Low priority goal, recently active
        low = _make_goal("Video games", priority=0.2,
                         evidence_days_ago=1, created_days_ago=10)

        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [high, low])
        )
        assert any(p.type == PatternType.MISALLOCATION.value for p in patterns)

    def test_no_misallocation_when_balanced(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        high = _make_goal("Important", priority=0.9,
                          evidence_days_ago=2, created_days_ago=10)
        low = _make_goal("Fun", priority=0.2,
                         evidence_days_ago=1, created_days_ago=10)

        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [high, low])
        )
        assert not any(p.type == PatternType.MISALLOCATION.value for p in patterns)

    def test_blind_spot_detected(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        observations = [{
            "type": "blindspot",
            "category": "time_management",
            "description": "Recurring missed deadlines",
            "evidence": "Missed deadline again",
        }]
        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze(observations, [])
        )
        assert len(patterns) == 1
        assert patterns[0].type == PatternType.BLINDSPOT.value

    def test_cap_enforced(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path, patterns_cap=5)
        # Add 6 dismissed patterns
        for i in range(6):
            p = Pattern(
                type=PatternType.BEHAVIORAL_DRIFT.value,
                description=f"old pattern {i}",
                dismissed=True,
            )
            watchdog._patterns[p.id] = p
        watchdog._enforce_cap()
        assert len(watchdog._patterns) <= 5

    def test_get_patterns_for_goal(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        p1 = Pattern(description="related", related_goals=["g1", "g2"])
        p2 = Pattern(description="unrelated", related_goals=["g3"])
        watchdog._patterns[p1.id] = p1
        watchdog._patterns[p2.id] = p2
        watchdog._save()

        related = watchdog.get_patterns_for_goal("g1")
        assert len(related) == 1
        assert related[0].id == p1.id

    def test_get_active_patterns_excludes_dismissed(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        p1 = Pattern(description="active", dismissed=False, friction_level=2)
        p2 = Pattern(description="dismissed", dismissed=True, friction_level=3)
        watchdog._patterns[p1.id] = p1
        watchdog._patterns[p2.id] = p2

        active = watchdog.get_active_patterns()
        assert len(active) == 1
        assert active[0].id == p1.id

    def test_skips_non_active_goals(self, patterns_path):
        watchdog = PatternWatchdog(patterns_path)
        goal = _make_goal("Completed", status="completed",
                          evidence_days_ago=20, created_days_ago=30)
        patterns = asyncio.get_event_loop().run_until_complete(
            watchdog.analyze([], [goal])
        )
        assert len(patterns) == 0
