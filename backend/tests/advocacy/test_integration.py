"""
Integration tests for the full advocacy subsystem.

End-to-end: goal creation → pattern detection → friction assignment →
response integration → escalation flow.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from advocacy import AdvocacySystem
from advocacy.friction import AMBIENT, GENTLE_FLAG, HARD_FLAG, SILENT
from advocacy.models import Evidence, Goal, Pattern, PatternType
from advocacy.onboarding import OnboardingStage
from profile import (
    AdvocacyConfig, AdvocacyUserConfig, AdvocateConfig, DevelopmentalConfig,
)


def _make_system(tmp_path, profile="solo", advocates=None,
                 user=None, developmental=None, enabled=True):
    config = AdvocacyConfig(
        enabled=enabled,
        profile=profile,
        user=user or AdvocacyUserConfig(),
        goals_cap=50,
        patterns_cap=100,
        cooloff_days=14,
        max_flags_per_day=3,
        advocates=advocates or [],
        developmental=developmental or DevelopmentalConfig(),
    )
    return AdvocacySystem(config, tmp_path / "advocacy")


class TestSystemInitialization:
    def test_all_subsystems_initialized(self, tmp_path):
        system = _make_system(tmp_path)
        assert system.goals is not None
        assert system.watchdog is not None
        assert system.friction is not None
        assert system.advocate_profile is not None
        assert system.network is not None
        assert system.developmental is not None
        assert system.onboarding is not None

    def test_enabled_flag(self, tmp_path):
        system = _make_system(tmp_path, enabled=True)
        assert system.enabled is True

        system2 = _make_system(tmp_path, enabled=False)
        assert system2.enabled is False

    def test_status_report(self, tmp_path):
        system = _make_system(tmp_path)
        status = system.get_status()
        assert status["enabled"] is True
        assert "active_goals" in status
        assert "active_patterns" in status
        assert "friction" in status
        assert "developmental" in status
        assert "onboarding" in status


class TestGoalToPatternFlow:
    """Goal creation → neglect → drift pattern detection."""

    def test_neglected_goal_creates_drift_pattern(self, tmp_path):
        system = _make_system(tmp_path)

        # Add a goal
        goal = system.goals.add_goal("Exercise regularly", category="health", priority=0.8)

        # Simulate time passage — make the goal old
        old_time = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        goal.created_at = old_time
        goal.evidence.append(
            Evidence(type="stated", description="User mentioned", last_observed=old_time)
        )
        system.goals._save()

        # Run advocacy cycle
        asyncio.get_event_loop().run_until_complete(
            system.run_advocacy_cycle([])
        )

        # Should have a drift pattern
        patterns = system.watchdog.get_active_patterns()
        assert len(patterns) >= 1
        drift_patterns = [p for p in patterns if p.type == PatternType.BEHAVIORAL_DRIFT.value]
        assert len(drift_patterns) == 1
        assert goal.id in drift_patterns[0].related_goals

    def test_active_goal_no_drift(self, tmp_path):
        system = _make_system(tmp_path)
        goal = system.goals.add_goal("Coding", priority=0.7)
        system.goals.record_evidence(
            goal.id,
            Evidence(type="action", description="Wrote code today"),
        )

        asyncio.get_event_loop().run_until_complete(
            system.run_advocacy_cycle([])
        )

        drift_patterns = [
            p for p in system.watchdog.get_active_patterns()
            if p.type == PatternType.BEHAVIORAL_DRIFT.value
        ]
        assert len(drift_patterns) == 0


class TestFrictionSurfacing:
    """Pattern → friction assignment → context surfacing."""

    def test_pattern_gets_friction_level(self, tmp_path):
        system = _make_system(tmp_path)

        # Create a pattern with enough occurrences for gentle flag
        pattern = Pattern(
            type=PatternType.BEHAVIORAL_DRIFT.value,
            description="Goal neglected",
            occurrences=3,
        )
        system.watchdog._patterns[pattern.id] = pattern
        system.watchdog._save()

        level = system.friction.assign_level(pattern)
        assert level == GENTLE_FLAG

    def test_surfacing_respects_anti_nag(self, tmp_path):
        system = _make_system(tmp_path)

        # Two patterns — only one should surface per turn
        p1 = Pattern(
            type=PatternType.BEHAVIORAL_DRIFT.value,
            description="First",
            occurrences=3,
            friction_level=GENTLE_FLAG,
        )
        p2 = Pattern(
            type=PatternType.CONTRADICTION.value,
            description="Second",
            occurrences=3,
            friction_level=GENTLE_FLAG,
        )
        queued = system.friction.queue_for_surfacing([p1, p2])
        assert len(queued) == 1  # Only ONE per turn

    def test_context_formatting(self, tmp_path):
        system = _make_system(tmp_path)

        pattern = Pattern(
            type=PatternType.BEHAVIORAL_DRIFT.value,
            description="You haven't worked on your fitness goal in weeks",
            occurrences=4,
            friction_level=GENTLE_FLAG,
        )
        system.friction._queue = [pattern]
        context = system.friction.get_advocacy_context()
        assert context is not None
        assert "fitness goal" in context


class TestEscalationFlow:
    """Dismissed pattern → worsens → escalation to advocate."""

    def test_dismissed_pattern_escalates_when_worsened(self, tmp_path):
        advocate = AdvocateConfig(
            name="Partner",
            relationship="partner",
            channel="email",
            escalation_threshold=3,
        )
        system = _make_system(tmp_path, profile="partnered", advocates=[advocate])

        # Create a pattern that's been dismissed but worsened
        pattern = Pattern(
            type=PatternType.HEALTH.value,
            description="Not sleeping enough",
            occurrences=5,
            friction_level=HARD_FLAG,
            dismissed=True,
        )
        system.watchdog._patterns[pattern.id] = pattern

        # Run escalation
        sent = asyncio.get_event_loop().run_until_complete(
            system.network.check_and_escalate([pattern])
        )
        assert len(sent) == 1
        assert sent[0].advocate.name == "Partner"
        assert pattern.escalated is True

    def test_solo_profile_never_escalates(self, tmp_path):
        system = _make_system(tmp_path, profile="solo")
        pattern = Pattern(
            friction_level=HARD_FLAG,
            dismissed=True,
            occurrences=10,
        )
        sent = asyncio.get_event_loop().run_until_complete(
            system.network.check_and_escalate([pattern])
        )
        assert len(sent) == 0


class TestDevelopmentalIntegration:
    """Developmental mode affects behavior."""

    def test_child_mode_detected(self, tmp_path):
        system = _make_system(
            tmp_path,
            user=AdvocacyUserConfig(age=10),
        )
        assert system.developmental.mode == "child"

    def test_child_safety_notifies_parent(self, tmp_path):
        system = _make_system(
            tmp_path,
            user=AdvocacyUserConfig(age=10),
        )
        assert system.developmental.should_notify_parent(is_safety_concern=True) is True

    def test_adult_mode_no_parent_notification(self, tmp_path):
        system = _make_system(tmp_path)
        assert system.developmental.should_notify_parent(is_safety_concern=True) is False


class TestOnboardingIntegration:
    """Onboarding feeds into goal graph."""

    def test_onboarding_collects_goals(self, tmp_path):
        system = _make_system(tmp_path)

        # Run through onboarding
        system.onboarding.start()
        system.onboarding.process_response("yes")  # intro
        system.onboarding.process_response("Alex")  # about
        system.onboarding.process_response("Get fit\nLearn piano")  # goals
        system.onboarding.process_response("no")  # advocates
        system.onboarding.process_response("no")  # family

        # Check collected data
        data = system.onboarding.get_collected_data()
        assert len(data["goals"]) == 2
        assert "Get fit" in data["goals"]

        # Seed goals into graph from onboarding data
        for goal_text in data["goals"]:
            system.goals.add_goal(goal_text)

        assert len(system.goals.get_active_goals()) == 2


class TestFullCycle:
    """End-to-end: message → goal inference → pattern detection →
    friction assignment → response integration."""

    def test_full_advocacy_cycle(self, tmp_path):
        system = _make_system(tmp_path)

        # 1. Add some goals
        g1 = system.goals.add_goal("Exercise", category="health", priority=0.9)
        g2 = system.goals.add_goal("Read more", category="education", priority=0.5)

        # 2. Make g1 neglected (old evidence)
        old_time = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        g1.evidence.append(
            Evidence(type="stated", description="set goal", last_observed=old_time)
        )
        g1.created_at = old_time
        system.goals._save()

        # 3. Add recent evidence to g2
        system.goals.record_evidence(
            g2.id,
            Evidence(type="action", description="Read a chapter"),
        )

        # 4. Run advocacy cycle
        asyncio.get_event_loop().run_until_complete(
            system.run_advocacy_cycle([])
        )

        # 5. Check that drift pattern was detected for g1
        patterns = system.watchdog.get_active_patterns()
        drift = [p for p in patterns if PatternType.BEHAVIORAL_DRIFT.value == p.type]
        assert len(drift) >= 1
        assert g1.id in drift[0].related_goals

        # 6. Check that friction was assigned
        assert drift[0].friction_level >= SILENT

    def test_disabled_system_does_nothing(self, tmp_path):
        system = _make_system(tmp_path, enabled=False)
        result = asyncio.get_event_loop().run_until_complete(
            system.run_advocacy_cycle([])
        )
        assert result is None
        assert len(system.watchdog.get_active_patterns()) == 0
