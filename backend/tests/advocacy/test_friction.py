"""Tests for FrictionGradient — anti-nag rules are NON-NEGOTIABLE."""

from datetime import datetime, timedelta, timezone

import pytest

from advocacy.friction import (
    AMBIENT, GENTLE_FLAG, HARD_FLAG, SILENT, STRUCTURAL_BLOCK,
    FrictionGradient,
)
from advocacy.models import Pattern, PatternType


def _make_pattern(type_=PatternType.BEHAVIORAL_DRIFT.value,
                  occurrences=1, friction_level=0, dismissed=False,
                  cooloff_until=None, description="test pattern"):
    return Pattern(
        type=type_,
        description=description,
        occurrences=occurrences,
        friction_level=friction_level,
        dismissed=dismissed,
        cooloff_until=cooloff_until,
    )


class TestLevelAssignment:
    def test_single_occurrence_is_silent(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(occurrences=1)
        assert fg.assign_level(p) == SILENT

    def test_two_occurrences_is_ambient(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(occurrences=2)
        assert fg.assign_level(p) == AMBIENT

    def test_three_occurrences_is_gentle_flag(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(occurrences=3)
        assert fg.assign_level(p) == GENTLE_FLAG

    def test_five_occurrences_is_hard_flag(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(occurrences=5)
        assert fg.assign_level(p) == HARD_FLAG

    def test_health_pattern_escalates(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(type_=PatternType.HEALTH.value, occurrences=1)
        assert fg.assign_level(p) == GENTLE_FLAG

    def test_health_pattern_three_occurrences(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(type_=PatternType.HEALTH.value, occurrences=3)
        assert fg.assign_level(p) == HARD_FLAG

    def test_contradiction_escalates_faster(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(type_=PatternType.CONTRADICTION.value, occurrences=2)
        level = fg.assign_level(p)
        assert level >= GENTLE_FLAG

    def test_misallocation_two_occurrences(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(type_=PatternType.MISALLOCATION.value, occurrences=2)
        level = fg.assign_level(p)
        assert level >= GENTLE_FLAG

    def test_worsened_during_cooloff_escalates(self, friction_path):
        fg = FrictionGradient(friction_path)
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        p = _make_pattern(occurrences=4, cooloff_until=future)
        level = fg.assign_level(p)
        assert level >= HARD_FLAG

    def test_structural_block_preserved(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=STRUCTURAL_BLOCK)
        assert fg.assign_level(p) == STRUCTURAL_BLOCK


class TestAntiNagRules:
    """These are NON-NEGOTIABLE per spec."""

    def test_silent_patterns_never_surfaced(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(occurrences=1, friction_level=SILENT)
        queued = fg.queue_for_surfacing([p])
        assert len(queued) == 0

    def test_only_one_per_conversation_turn(self, friction_path):
        fg = FrictionGradient(friction_path)
        p1 = _make_pattern(friction_level=GENTLE_FLAG, description="first")
        p2 = _make_pattern(friction_level=GENTLE_FLAG, description="second")
        queued = fg.queue_for_surfacing([p1, p2])
        assert len(queued) == 1

    def test_highest_level_wins(self, friction_path):
        fg = FrictionGradient(friction_path)
        p1 = _make_pattern(friction_level=AMBIENT, description="low")
        p2 = _make_pattern(friction_level=HARD_FLAG, description="high")
        queued = fg.queue_for_surfacing([p1, p2])
        assert len(queued) == 1
        assert queued[0].description == "high"

    def test_cooloff_respected(self, friction_path):
        fg = FrictionGradient(friction_path)
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        p = _make_pattern(friction_level=GENTLE_FLAG, cooloff_until=future)
        queued = fg.queue_for_surfacing([p])
        assert len(queued) == 0

    def test_hard_flag_bypasses_cooloff(self, friction_path):
        fg = FrictionGradient(friction_path)
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        p = _make_pattern(friction_level=HARD_FLAG, cooloff_until=future)
        queued = fg.queue_for_surfacing([p])
        assert len(queued) == 1

    def test_daily_cap_enforced(self, friction_path):
        fg = FrictionGradient(friction_path, max_flags_per_day=2)
        # Simulate 2 already surfaced
        fg._surfaced_today = ["p1", "p2"]
        fg._surfaced_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        p = _make_pattern(friction_level=GENTLE_FLAG)
        queued = fg.queue_for_surfacing([p])
        assert len(queued) == 0

    def test_structural_block_ignores_daily_cap(self, friction_path):
        fg = FrictionGradient(friction_path, max_flags_per_day=1)
        fg._surfaced_today = ["p1"]
        fg._surfaced_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        p = _make_pattern(friction_level=STRUCTURAL_BLOCK)
        queued = fg.queue_for_surfacing([p])
        assert len(queued) == 1

    def test_daily_counter_resets(self, friction_path):
        fg = FrictionGradient(friction_path, max_flags_per_day=1)
        fg._surfaced_today = ["p1"]
        fg._surfaced_date = "2020-01-01"  # Old date

        p = _make_pattern(friction_level=GENTLE_FLAG)
        queued = fg.queue_for_surfacing([p])
        assert len(queued) == 1


class TestDismissal:
    def test_dismiss_gentle_flag_applies_cooloff(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=GENTLE_FLAG)
        fg.dismiss(p)
        assert p.dismissed is True
        assert p.friction_level == SILENT
        assert p.cooloff_until is not None

    def test_dismiss_hard_flag_applies_cooloff(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=HARD_FLAG)
        fg.dismiss(p)
        assert p.dismissed is True
        assert p.cooloff_until is not None

    def test_undismiss_reactivates(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=GENTLE_FLAG)
        fg.dismiss(p)
        fg.undismiss(p)
        assert p.dismissed is False
        assert p.cooloff_until is None


class TestFormatting:
    def test_ambient_format(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=AMBIENT, description="Test pattern")
        fg._queue = [p]
        context = fg.get_advocacy_context()
        assert context is not None
        assert "advocacy-context" in context
        assert "Test pattern" in context

    def test_gentle_flag_format(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=GENTLE_FLAG, description="Worth noting")
        fg._queue = [p]
        context = fg.get_advocacy_context()
        assert "worth noting" in context.lower()

    def test_hard_flag_format(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=HARD_FLAG, description="Important issue")
        fg._queue = [p]
        context = fg.get_advocacy_context()
        assert "flag something" in context.lower()

    def test_structural_block_format(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=STRUCTURAL_BLOCK, description="Danger")
        fg._queue = [p]
        context = fg.get_advocacy_context()
        assert "IMPORTANT" in context
        assert "confirmation" in context.lower()

    def test_empty_queue_returns_none(self, friction_path):
        fg = FrictionGradient(friction_path)
        assert fg.get_advocacy_context() is None

    def test_consuming_queue_clears_it(self, friction_path):
        fg = FrictionGradient(friction_path)
        p = _make_pattern(friction_level=AMBIENT, description="test")
        fg._queue = [p]
        fg.get_advocacy_context()
        assert fg.get_advocacy_context() is None


class TestPersistence:
    def test_state_persists(self, friction_path):
        fg = FrictionGradient(friction_path)
        fg._surfaced_today = ["p1", "p2"]
        fg._surfaced_date = "2025-06-01"
        fg._save()

        fg2 = FrictionGradient(friction_path)
        assert fg2._surfaced_today == ["p1", "p2"]
        assert fg2._surfaced_date == "2025-06-01"

    def test_get_status(self, friction_path):
        fg = FrictionGradient(friction_path)
        status = fg.get_status()
        assert "flags_today" in status
        assert "max_flags_per_day" in status
