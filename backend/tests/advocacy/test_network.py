"""Tests for TrustedAdvocateNetwork."""

import asyncio
from unittest.mock import MagicMock

import pytest

from advocacy.models import Pattern, PatternType
from advocacy.network import EscalationMessage, TrustedAdvocateNetwork
from advocacy.profiles import AdvocateProfile
from profile import AdvocacyConfig, AdvocacyUserConfig, AdvocateConfig, DevelopmentalConfig


def _make_profile(profile_type="partnered", advocates=None):
    if advocates is None:
        advocates = [AdvocateConfig(
            name="Partner",
            relationship="partner",
            channel="email",
            categories=["health", "financial"],
            escalation_threshold=3,
        )]
    config = AdvocacyConfig(
        enabled=True,
        profile=profile_type,
        user=AdvocacyUserConfig(),
        advocates=advocates,
    )
    return AdvocateProfile(config)


class TestEscalationMessage:
    def test_message_creation(self):
        advocate = AdvocateConfig(name="Partner", channel="email")
        pattern = Pattern(
            type=PatternType.BEHAVIORAL_DRIFT.value,
            description="Goal neglected",
            occurrences=5,
        )
        msg = EscalationMessage(advocate, pattern)
        assert "Behavioral Drift" in msg.subject
        assert "Goal neglected" in msg.body
        assert "5" in msg.body

    def test_full_visibility_includes_evidence(self):
        advocate = AdvocateConfig(name="Therapist", visibility="full")
        pattern = Pattern(
            description="Test",
            evidence=["evidence 1", "evidence 2"],
        )
        msg = EscalationMessage(advocate, pattern)
        assert "evidence 1" in msg.body

    def test_themes_visibility_excludes_evidence(self):
        advocate = AdvocateConfig(name="Partner", visibility="themes")
        pattern = Pattern(
            description="Test",
            evidence=["evidence 1", "evidence 2"],
        )
        msg = EscalationMessage(advocate, pattern)
        assert "evidence 1" not in msg.body

    def test_to_dict(self):
        advocate = AdvocateConfig(name="Coach", channel="slack")
        pattern = Pattern(description="Pattern")
        msg = EscalationMessage(advocate, pattern)
        d = msg.to_dict()
        assert d["advocate_name"] == "Coach"
        assert d["channel"] == "slack"
        assert "pattern_id" in d


class TestTrustedAdvocateNetwork:
    def test_escalate_qualifying_pattern(self):
        profile = _make_profile()
        network = TrustedAdvocateNetwork(profile)
        pattern = Pattern(
            type=PatternType.HEALTH.value,
            description="Health concern",
            friction_level=3,
            dismissed=True,
            occurrences=4,
        )
        sent = asyncio.get_event_loop().run_until_complete(
            network.check_and_escalate([pattern])
        )
        assert len(sent) == 1
        assert pattern.escalated is True

    def test_skip_already_escalated(self):
        profile = _make_profile()
        network = TrustedAdvocateNetwork(profile)
        pattern = Pattern(
            friction_level=3,
            dismissed=True,
            escalated=True,
            occurrences=4,
        )
        sent = asyncio.get_event_loop().run_until_complete(
            network.check_and_escalate([pattern])
        )
        assert len(sent) == 0

    def test_skip_low_friction(self):
        profile = _make_profile()
        network = TrustedAdvocateNetwork(profile)
        pattern = Pattern(
            friction_level=1,
            dismissed=False,
            occurrences=1,
        )
        sent = asyncio.get_event_loop().run_until_complete(
            network.check_and_escalate([pattern])
        )
        assert len(sent) == 0

    def test_solo_profile_no_escalation(self):
        profile = _make_profile(profile_type="solo")
        network = TrustedAdvocateNetwork(profile)
        pattern = Pattern(
            friction_level=4,
            dismissed=True,
            occurrences=10,
        )
        sent = asyncio.get_event_loop().run_until_complete(
            network.check_and_escalate([pattern])
        )
        assert len(sent) == 0

    def test_bus_notification_sent(self):
        profile = _make_profile()
        bus = MagicMock()
        network = TrustedAdvocateNetwork(profile, bus=bus)
        pattern = Pattern(
            type=PatternType.HEALTH.value,
            description="Health alert",
            friction_level=3,
            dismissed=True,
            occurrences=4,
        )
        asyncio.get_event_loop().run_until_complete(
            network.check_and_escalate([pattern])
        )
        bus.send.assert_called_once()

    def test_escalation_history_tracked(self):
        profile = _make_profile()
        network = TrustedAdvocateNetwork(profile)
        pattern = Pattern(
            friction_level=3,
            dismissed=True,
            occurrences=3,
        )
        asyncio.get_event_loop().run_until_complete(
            network.check_and_escalate([pattern])
        )
        history = network.get_escalation_history()
        assert len(history) == 1
        assert history[0]["advocate_name"] == "Partner"

    def test_get_status(self):
        profile = _make_profile()
        network = TrustedAdvocateNetwork(profile)
        status = network.get_status()
        assert status["escalation_enabled"] is True
        assert status["total_escalations"] == 0
