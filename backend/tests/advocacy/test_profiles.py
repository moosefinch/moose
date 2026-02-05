"""Tests for AdvocateProfile."""

import pytest

from advocacy.models import Pattern, PatternType
from advocacy.profiles import AdvocateProfile
from profile import AdvocacyConfig, AdvocacyUserConfig, AdvocateConfig, DevelopmentalConfig


def _make_config(**overrides):
    defaults = {
        "enabled": True,
        "profile": "solo",
        "user": AdvocacyUserConfig(),
        "goals_cap": 50,
        "patterns_cap": 100,
        "cooloff_days": 14,
        "max_flags_per_day": 3,
        "advocates": [],
        "developmental": DevelopmentalConfig(),
    }
    defaults.update(overrides)
    return AdvocacyConfig(**defaults)


class TestProfileTypes:
    def test_solo_no_escalation(self):
        config = _make_config(profile="solo")
        profile = AdvocateProfile(config)
        assert profile.escalation_enabled is False

    def test_solo_no_escalation_even_with_advocates(self):
        config = _make_config(
            profile="solo",
            advocates=[AdvocateConfig(name="Partner")],
        )
        profile = AdvocateProfile(config)
        assert profile.escalation_enabled is False

    def test_partnered_with_advocate(self):
        config = _make_config(
            profile="partnered",
            advocates=[AdvocateConfig(name="Partner")],
        )
        profile = AdvocateProfile(config)
        assert profile.escalation_enabled is True

    def test_partnered_without_advocate(self):
        config = _make_config(profile="partnered")
        profile = AdvocateProfile(config)
        assert profile.escalation_enabled is False

    def test_guided_profile(self):
        config = _make_config(
            profile="guided",
            advocates=[AdvocateConfig(name="Coach")],
        )
        profile = AdvocateProfile(config)
        assert profile.escalation_enabled is True
        assert profile.get_escalation_threshold() == 2


class TestEscalation:
    def test_should_escalate_high_friction_dismissed(self):
        config = _make_config(
            profile="partnered",
            advocates=[AdvocateConfig(name="Partner")],
        )
        profile = AdvocateProfile(config)
        p = Pattern(friction_level=3, dismissed=True, occurrences=3)
        assert profile.should_escalate(p) is True

    def test_should_not_escalate_low_friction(self):
        config = _make_config(
            profile="partnered",
            advocates=[AdvocateConfig(name="Partner")],
        )
        profile = AdvocateProfile(config)
        p = Pattern(friction_level=1, dismissed=False, occurrences=1)
        assert profile.should_escalate(p) is False

    def test_should_escalate_recurring_high_pattern(self):
        config = _make_config(
            profile="partnered",
            advocates=[AdvocateConfig(name="Partner")],
        )
        profile = AdvocateProfile(config)
        p = Pattern(friction_level=3, dismissed=False, occurrences=5)
        assert profile.should_escalate(p) is True

    def test_custom_threshold(self):
        advocate = AdvocateConfig(
            name="Therapist",
            categories=["health"],
            escalation_threshold=2,
        )
        config = _make_config(profile="custom", advocates=[advocate])
        profile = AdvocateProfile(config)
        assert profile.get_escalation_threshold("health") == 2


class TestAdvocateMatching:
    def test_match_by_category(self):
        a1 = AdvocateConfig(name="Coach", categories=["career", "education"])
        a2 = AdvocateConfig(name="Partner", categories=["health", "financial"])
        config = _make_config(advocates=[a1, a2])
        profile = AdvocateProfile(config)

        assert profile.get_advocate_for("career").name == "Coach"
        assert profile.get_advocate_for("health").name == "Partner"

    def test_fallback_to_first(self):
        a1 = AdvocateConfig(name="Default", categories=["career"])
        config = _make_config(advocates=[a1])
        profile = AdvocateProfile(config)
        assert profile.get_advocate_for("unknown").name == "Default"

    def test_no_advocates_returns_none(self):
        config = _make_config(advocates=[])
        profile = AdvocateProfile(config)
        assert profile.get_advocate_for("career") is None

    def test_advocate_with_empty_categories_matches_all(self):
        a = AdvocateConfig(name="Universal", categories=[])
        config = _make_config(advocates=[a])
        profile = AdvocateProfile(config)
        assert profile.get_advocate_for("anything").name == "Universal"


class TestDevelopmentalMode:
    def test_default_adult(self):
        config = _make_config()
        profile = AdvocateProfile(config)
        assert profile.get_developmental_mode() == "adult"

    def test_explicit_child_mode(self):
        config = _make_config(
            developmental=DevelopmentalConfig(mode="child")
        )
        profile = AdvocateProfile(config)
        assert profile.get_developmental_mode() == "child"

    def test_explicit_adolescent_mode(self):
        config = _make_config(
            developmental=DevelopmentalConfig(mode="adolescent")
        )
        profile = AdvocateProfile(config)
        assert profile.get_developmental_mode() == "adolescent"

    def test_age_inference_child(self):
        config = _make_config(
            user=AdvocacyUserConfig(age=10),
        )
        profile = AdvocateProfile(config)
        assert profile.get_developmental_mode() == "child"

    def test_age_inference_adolescent(self):
        config = _make_config(
            user=AdvocacyUserConfig(age=15),
        )
        profile = AdvocateProfile(config)
        assert profile.get_developmental_mode() == "adolescent"

    def test_age_inference_adult(self):
        config = _make_config(
            user=AdvocacyUserConfig(age=25),
        )
        profile = AdvocateProfile(config)
        assert profile.get_developmental_mode() == "adult"


class TestStatus:
    def test_get_status(self):
        config = _make_config(
            profile="partnered",
            advocates=[AdvocateConfig(name="Partner")],
        )
        profile = AdvocateProfile(config)
        status = profile.get_status()
        assert status["profile"] == "partnered"
        assert status["escalation_enabled"] is True
        assert status["advocate_count"] == 1
