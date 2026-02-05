"""
AdvocacySystem — coordinator for the advocacy subsystem.

Wires together GoalGraph, PatternWatchdog, FrictionGradient,
AdvocateProfile, TrustedAdvocateNetwork, DevelopmentalCalibration,
and FamilyOnboarding.

Initialized from agent_core.py if profile.advocacy.enabled.
"""

import logging
from pathlib import Path
from typing import Optional

from profile import AdvocacyConfig

logger = logging.getLogger(__name__)


class AdvocacySystem:
    """Top-level coordinator for the advocacy subsystem."""

    def __init__(self, config: AdvocacyConfig, state_dir: Path,
                 channel_manager=None, bus=None):
        self._config = config
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Goal Graph
        from advocacy.goals import GoalGraph
        self.goals = GoalGraph(
            path=state_dir / "goals.json",
            goals_cap=config.goals_cap,
        )

        # Phase 2: Pattern Watchdog
        from advocacy.watchdog import PatternWatchdog
        self.watchdog = PatternWatchdog(
            path=state_dir / "patterns.json",
            patterns_cap=config.patterns_cap,
        )

        # Phase 3: Friction Gradient
        from advocacy.friction import FrictionGradient
        self.friction = FrictionGradient(
            path=state_dir / "friction.json",
            cooloff_days=config.cooloff_days,
            max_flags_per_day=config.max_flags_per_day,
        )

        # Phase 4: Advocate Profile
        from advocacy.profiles import AdvocateProfile
        self.advocate_profile = AdvocateProfile(config)

        # Phase 5: Trusted Advocate Network
        from advocacy.network import TrustedAdvocateNetwork
        self.network = TrustedAdvocateNetwork(
            profile=self.advocate_profile,
            channel_manager=channel_manager,
            bus=bus,
        )

        # Phase 6: Developmental Calibration
        from advocacy.developmental import DevelopmentalCalibration
        self.developmental = DevelopmentalCalibration(config)

        # Phase 7: Family Onboarding
        from advocacy.onboarding import FamilyOnboarding
        self.onboarding = FamilyOnboarding(
            path=state_dir / "onboarding.json",
        )

        logger.info(
            "[Advocacy] System initialized (profile=%s, mode=%s, goals_cap=%d, "
            "patterns_cap=%d, advocates=%d)",
            config.profile,
            self.developmental.mode,
            config.goals_cap,
            config.patterns_cap,
            len(config.advocates),
        )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    async def run_advocacy_cycle(self, observations: list[dict],
                                  memory: list[dict] = None) -> Optional[str]:
        """Run a full advocacy cycle: detect patterns, assign friction,
        queue for surfacing, check escalation.

        Returns advocacy context string if anything should be surfaced,
        or None.
        """
        if not self.enabled:
            return None

        # 1. Get active goals
        goals = self.goals.get_active_goals()

        # 2. Run watchdog — detect new/updated patterns
        new_patterns = await self.watchdog.analyze(observations, goals, memory)

        # 3. Assign friction levels to all active patterns
        active_patterns = self.watchdog.get_active_patterns()
        for pattern in active_patterns:
            self.friction.assign_level(pattern)

        # 4. Queue patterns for surfacing (respects anti-nag rules)
        queued = self.friction.queue_for_surfacing(active_patterns)

        # 5. Check escalation for qualifying patterns
        if self.network:
            await self.network.check_and_escalate(active_patterns)

        # 6. Save updated watchdog state
        self.watchdog._save()

        return None  # Context retrieved via friction.get_advocacy_context()

    def get_status(self) -> dict:
        """Return full advocacy subsystem status."""
        status = {
            "enabled": self._config.enabled,
            "profile": self._config.profile,
            "active_goals": len(self.goals.get_active_goals()),
            "unconfirmed_goals": len(self.goals.get_unconfirmed_goals()),
            "active_patterns": len(self.watchdog.get_active_patterns()),
        }

        if self.friction:
            status["friction"] = self.friction.get_status()
        if self.advocate_profile:
            status["advocate_profile"] = self.advocate_profile.get_status()
        if self.network:
            status["network"] = self.network.get_status()
        if self.developmental:
            status["developmental"] = self.developmental.get_status()
        if self.onboarding:
            status["onboarding"] = self.onboarding.get_status()

        return status
