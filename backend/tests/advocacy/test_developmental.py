"""Tests for DevelopmentalCalibration."""

import pytest

from advocacy.developmental import DevelopmentalCalibration
from profile import AdvocacyConfig, AdvocacyUserConfig, DevelopmentalConfig


def _make_config(**overrides):
    defaults = {
        "enabled": True,
        "user": AdvocacyUserConfig(),
        "developmental": DevelopmentalConfig(),
    }
    defaults.update(overrides)
    return AdvocacyConfig(**defaults)


class TestModeDetection:
    def test_default_adult(self):
        config = _make_config()
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "adult"

    def test_explicit_child(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="child"))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "child"

    def test_explicit_adolescent(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="adolescent"))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "adolescent"

    def test_age_inference_child(self):
        config = _make_config(user=AdvocacyUserConfig(age=8))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "child"

    def test_age_inference_adolescent(self):
        config = _make_config(user=AdvocacyUserConfig(age=15))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "adolescent"

    def test_age_inference_adult(self):
        config = _make_config(user=AdvocacyUserConfig(age=30))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "adult"

    def test_age_12_is_child(self):
        config = _make_config(user=AdvocacyUserConfig(age=12))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "child"

    def test_age_13_is_adolescent(self):
        config = _make_config(user=AdvocacyUserConfig(age=13))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "adolescent"

    def test_age_17_is_adolescent(self):
        config = _make_config(user=AdvocacyUserConfig(age=17))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "adolescent"

    def test_age_18_is_adult(self):
        config = _make_config(user=AdvocacyUserConfig(age=18))
        dc = DevelopmentalCalibration(config)
        assert dc.mode == "adult"


class TestDevelopmentalContext:
    def test_child_context(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="child"))
        dc = DevelopmentalCalibration(config)
        ctx = dc.get_developmental_context()
        assert "Child" in ctx
        assert "warm" in ctx.lower()
        assert "patient" in ctx.lower()

    def test_adolescent_context(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="adolescent"))
        dc = DevelopmentalCalibration(config)
        ctx = dc.get_developmental_context()
        assert "Adolescent" in ctx
        assert "respectful" in ctx.lower()

    def test_adult_context(self):
        config = _make_config()
        dc = DevelopmentalCalibration(config)
        ctx = dc.get_developmental_context()
        assert "Adult" in ctx
        assert "peer" in ctx.lower()


class TestParentNotification:
    def test_child_safety_always_notifies(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="child"))
        dc = DevelopmentalCalibration(config)
        assert dc.should_notify_parent(is_safety_concern=True) is True

    def test_adolescent_safety_always_notifies(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="adolescent"))
        dc = DevelopmentalCalibration(config)
        assert dc.should_notify_parent(is_safety_concern=True) is True

    def test_adult_never_notifies_parent(self):
        config = _make_config()
        dc = DevelopmentalCalibration(config)
        assert dc.should_notify_parent(is_safety_concern=True) is False

    def test_child_regular_summaries(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="child"))
        dc = DevelopmentalCalibration(config)
        assert dc.should_notify_parent() is True

    def test_adolescent_no_notify_without_persistence(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="adolescent"))
        dc = DevelopmentalCalibration(config)
        assert dc.should_notify_parent() is False

    def test_adolescent_notifies_on_persistent_pattern(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="adolescent"))
        dc = DevelopmentalCalibration(config)
        assert dc.should_notify_parent(pattern_persistent=True) is True


class TestParentVisibility:
    def test_child_sees_summaries(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="child"))
        dc = DevelopmentalCalibration(config)
        assert dc.get_parent_visibility() == "summaries"

    def test_adolescent_sees_themes(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="adolescent"))
        dc = DevelopmentalCalibration(config)
        assert dc.get_parent_visibility() == "themes"

    def test_adult_sees_none(self):
        config = _make_config()
        dc = DevelopmentalCalibration(config)
        assert dc.get_parent_visibility() == "none"


class TestStatus:
    def test_get_status(self):
        config = _make_config(developmental=DevelopmentalConfig(mode="child"))
        dc = DevelopmentalCalibration(config)
        status = dc.get_status()
        assert status["mode"] == "child"
        assert status["check_in_frequency"] == "proactive"
