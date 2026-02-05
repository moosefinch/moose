"""Tests for GoalGraph."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from advocacy.goals import GoalGraph
from advocacy.models import Evidence, GoalCategory, GoalStatus


class TestGoalGraph:
    def test_add_goal(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.add_goal("Get fit", category="health", priority=0.8)
        assert goal.text == "Get fit"
        assert goal.category == "health"
        assert goal.priority == 0.8
        assert goal.confirmed is True
        assert goal.inferred is False

    def test_persistence(self, goals_path):
        g1 = GoalGraph(goals_path)
        g1.add_goal("Learn Python", category="education")

        g2 = GoalGraph(goals_path)
        goals = g2.get_active_goals()
        assert len(goals) == 1
        assert goals[0].text == "Learn Python"

    def test_infer_goal(self, goals_path):
        graph = GoalGraph(goals_path)
        evidence = Evidence(type="observation", description="Mentioned jogging")
        goal = graph.infer_goal("Stay active", category="health", evidence=evidence)
        assert goal.inferred is True
        assert goal.confirmed is False
        assert goal.priority == 0.3
        assert len(goal.evidence) == 1

    def test_confirm_goal(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.infer_goal("Read more", category="education")
        assert graph.confirm_goal(goal.id) is True
        confirmed = graph.get_goal(goal.id)
        assert confirmed.confirmed is True

    def test_reject_goal(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.infer_goal("Skydive", category="other")
        assert graph.reject_goal(goal.id) is True
        rejected = graph.get_goal(goal.id)
        assert rejected.status == GoalStatus.ABANDONED.value

    def test_confirm_non_inferred_fails(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.add_goal("Direct goal")
        assert graph.confirm_goal(goal.id) is False

    def test_update_priority(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.add_goal("Test", priority=0.5)
        assert graph.update_priority(goal.id, 0.9) is True
        assert graph.get_goal(goal.id).priority == 0.9

    def test_priority_clamped(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.add_goal("Test")
        graph.update_priority(goal.id, 1.5)
        assert graph.get_goal(goal.id).priority == 1.0
        graph.update_priority(goal.id, -0.5)
        assert graph.get_goal(goal.id).priority == 0.0

    def test_update_status(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.add_goal("Test")
        assert graph.update_status(goal.id, "completed") is True
        assert graph.get_goal(goal.id).status == "completed"

    def test_update_status_invalid(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.add_goal("Test")
        assert graph.update_status(goal.id, "invalid_status") is False

    def test_add_tension(self, goals_path):
        graph = GoalGraph(goals_path)
        g1 = graph.add_goal("Save money", category="financial")
        g2 = graph.add_goal("Travel the world", category="personal_growth")
        assert graph.add_tension(g1.id, g2.id) is True

        tensions = graph.get_tensions_for(g1.id)
        assert len(tensions) == 1
        assert tensions[0].id == g2.id

        # Bidirectional
        tensions2 = graph.get_tensions_for(g2.id)
        assert len(tensions2) == 1
        assert tensions2[0].id == g1.id

    def test_tension_nonexistent_goal(self, goals_path):
        graph = GoalGraph(goals_path)
        g1 = graph.add_goal("Test")
        assert graph.add_tension(g1.id, "nonexistent") is False

    def test_get_active_goals_sorted(self, goals_path):
        graph = GoalGraph(goals_path)
        graph.add_goal("Low", priority=0.2)
        graph.add_goal("High", priority=0.9)
        graph.add_goal("Mid", priority=0.5)

        active = graph.get_active_goals()
        assert len(active) == 3
        assert active[0].text == "High"
        assert active[1].text == "Mid"
        assert active[2].text == "Low"

    def test_get_unconfirmed_goals(self, goals_path):
        graph = GoalGraph(goals_path)
        graph.add_goal("Confirmed")
        graph.infer_goal("Maybe this")
        graph.infer_goal("Maybe that")

        unconfirmed = graph.get_unconfirmed_goals()
        assert len(unconfirmed) == 2

    def test_record_evidence(self, goals_path):
        graph = GoalGraph(goals_path)
        goal = graph.add_goal("Exercise")
        evidence = Evidence(type="action", description="Went for a run")
        assert graph.record_evidence(goal.id, evidence) is True
        updated = graph.get_goal(goal.id)
        assert len(updated.evidence) == 1
        assert updated.evidence[0].description == "Went for a run"

    def test_neglected_goals(self, goals_path):
        graph = GoalGraph(goals_path)
        # Create a goal with old evidence
        goal = graph.add_goal("Old goal")
        old_time = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        goal.evidence.append(
            Evidence(type="test", description="old", last_observed=old_time)
        )
        goal.created_at = old_time
        graph._save()

        # Create a fresh goal with recent evidence
        fresh = graph.add_goal("Fresh goal")
        graph.record_evidence(
            fresh.id,
            Evidence(type="test", description="recent"),
        )

        neglected = graph.neglected_goals(days=7)
        assert len(neglected) == 1
        assert neglected[0].id == goal.id

    def test_neglected_goal_no_evidence(self, goals_path):
        graph = GoalGraph(goals_path)
        old_time = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        goal = graph.add_goal("No evidence goal")
        goal.created_at = old_time
        graph._save()

        neglected = graph.neglected_goals(days=7)
        assert len(neglected) == 1

    def test_goal_cap(self, goals_path):
        graph = GoalGraph(goals_path, goals_cap=3)
        graph.add_goal("One")
        graph.add_goal("Two")
        graph.add_goal("Three")
        with pytest.raises(ValueError, match="cap"):
            graph.add_goal("Four")

    def test_cap_allows_after_completing(self, goals_path):
        graph = GoalGraph(goals_path, goals_cap=2)
        g1 = graph.add_goal("One")
        graph.add_goal("Two")
        graph.update_status(g1.id, "completed")
        # Should work now — only 1 active
        graph.add_goal("Three")
        assert len(graph.get_active_goals()) == 2

    def test_get_children(self, goals_path):
        graph = GoalGraph(goals_path)
        parent = graph.add_goal("Parent goal")
        c1 = graph.add_goal("Child 1", parent_id=parent.id)
        c2 = graph.add_goal("Child 2", parent_id=parent.id)
        graph.add_goal("Unrelated")

        children = graph.get_children(parent.id)
        assert len(children) == 2
        ids = {c.id for c in children}
        assert c1.id in ids
        assert c2.id in ids

    def test_all_goals(self, goals_path):
        graph = GoalGraph(goals_path)
        g1 = graph.add_goal("Active")
        g2 = graph.add_goal("Completed")
        graph.update_status(g2.id, "completed")
        assert len(graph.all_goals()) == 2

    def test_get_nonexistent_goal(self, goals_path):
        graph = GoalGraph(goals_path)
        assert graph.get_goal("nope") is None

    def test_record_evidence_nonexistent(self, goals_path):
        graph = GoalGraph(goals_path)
        assert graph.record_evidence("nope", Evidence(type="t", description="d")) is False
