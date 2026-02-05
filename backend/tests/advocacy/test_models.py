"""Tests for advocacy data models."""

from advocacy.models import (
    Evidence,
    Goal,
    GoalCategory,
    GoalStatus,
    Pattern,
    PatternType,
)


class TestEvidence:
    def test_create_evidence(self):
        e = Evidence(type="observation", description="User mentioned fitness goal")
        assert e.type == "observation"
        assert e.description == "User mentioned fitness goal"
        assert e.last_observed  # auto-populated

    def test_roundtrip(self):
        e = Evidence(type="action", description="test", last_observed="2025-01-01T00:00:00Z")
        d = e.to_dict()
        e2 = Evidence.from_dict(d)
        assert e2.type == e.type
        assert e2.description == e.description
        assert e2.last_observed == e.last_observed


class TestGoal:
    def test_create_goal(self):
        g = Goal(text="Get fit", category=GoalCategory.HEALTH.value)
        assert g.text == "Get fit"
        assert g.category == "health"
        assert g.status == GoalStatus.ACTIVE.value
        assert g.priority == 0.5
        assert g.confirmed is True
        assert g.inferred is False
        assert g.id  # auto-generated

    def test_roundtrip(self):
        g = Goal(
            text="Learn piano",
            category=GoalCategory.CREATIVE.value,
            priority=0.8,
            tensions=["abc", "def"],
            evidence=[Evidence(type="stated", description="User said so")],
        )
        d = g.to_dict()
        g2 = Goal.from_dict(d)
        assert g2.id == g.id
        assert g2.text == g.text
        assert g2.category == g.category
        assert g2.priority == g.priority
        assert g2.tensions == ["abc", "def"]
        assert len(g2.evidence) == 1
        assert g2.evidence[0].type == "stated"

    def test_inferred_goal(self):
        g = Goal(text="Seems interested in cooking", inferred=True, confirmed=False)
        assert g.inferred is True
        assert g.confirmed is False

    def test_default_values(self):
        g = Goal()
        assert g.text == ""
        assert g.category == GoalCategory.OTHER.value
        assert g.parent_id is None
        assert g.tensions == []
        assert g.evidence == []


class TestPattern:
    def test_create_pattern(self):
        p = Pattern(
            type=PatternType.BEHAVIORAL_DRIFT.value,
            description="Goal neglected for 3 weeks",
        )
        assert p.type == "behavioral_drift"
        assert p.occurrences == 1
        assert p.friction_level == 0
        assert p.dismissed is False
        assert p.escalated is False

    def test_roundtrip(self):
        p = Pattern(
            type=PatternType.CONTRADICTION.value,
            description="Said they want to save money but spending increased",
            evidence=["Spending up 30%", "Stated saving goal last week"],
            occurrences=3,
            friction_level=2,
            related_goals=["goal-1"],
        )
        d = p.to_dict()
        p2 = Pattern.from_dict(d)
        assert p2.id == p.id
        assert p2.type == p.type
        assert p2.description == p.description
        assert p2.evidence == p.evidence
        assert p2.occurrences == 3
        assert p2.friction_level == 2
        assert p2.related_goals == ["goal-1"]

    def test_dismissed_state(self):
        p = Pattern(dismissed=True, dismissed_at="2025-01-01T00:00:00Z",
                    cooloff_until="2025-01-15T00:00:00Z")
        assert p.dismissed is True
        assert p.cooloff_until == "2025-01-15T00:00:00Z"

    def test_all_pattern_types(self):
        for pt in PatternType:
            p = Pattern(type=pt.value)
            assert p.type == pt.value
