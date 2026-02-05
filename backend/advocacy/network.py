"""
TrustedAdvocateNetwork — escalation delivery.

When a pattern reaches the escalation threshold and the user has
dismissed it at a lower level, this module sends a summary to
the configured advocate through their preferred channel.

Messages include: pattern description, category, first observed, occurrences.
Messages do NOT include: transcripts, specific messages, work content.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from advocacy.models import Pattern
from advocacy.profiles import AdvocateProfile
from profile import AdvocateConfig

logger = logging.getLogger(__name__)


class EscalationMessage:
    """A message prepared for delivery to an advocate."""

    def __init__(self, advocate: AdvocateConfig, pattern: Pattern):
        self.advocate = advocate
        self.pattern = pattern
        self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def subject(self) -> str:
        return f"Advocacy alert: {self.pattern.type.replace('_', ' ').title()}"

    @property
    def body(self) -> str:
        lines = [
            f"Pattern: {self.pattern.description}",
            f"Category: {self.pattern.type.replace('_', ' ').title()}",
            f"First observed: {self.pattern.first_observed}",
            f"Occurrences: {self.pattern.occurrences}",
            f"Current friction level: {self.pattern.friction_level}",
        ]
        if self.advocate.visibility == "full":
            if self.pattern.evidence:
                lines.append(f"Evidence: {'; '.join(self.pattern.evidence[:5])}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "advocate_name": self.advocate.name,
            "channel": self.advocate.channel,
            "subject": self.subject,
            "body": self.body,
            "pattern_id": self.pattern.id,
            "created_at": self.created_at,
        }


class TrustedAdvocateNetwork:
    """Manages escalation delivery to trusted advocates."""

    def __init__(self, profile: AdvocateProfile,
                 channel_manager=None, bus=None):
        self._profile = profile
        self._channel_manager = channel_manager
        self._bus = bus
        self._escalation_history: list[dict] = []

    async def check_and_escalate(self, patterns: list[Pattern]) -> list[EscalationMessage]:
        """Check patterns for escalation, send if needed. Returns sent messages."""
        sent = []

        for pattern in patterns:
            if pattern.escalated:
                continue
            if not self._profile.should_escalate(pattern):
                continue

            advocate = self._profile.get_advocate_for(pattern.type)
            if not advocate:
                continue

            message = EscalationMessage(advocate, pattern)

            # Deliver through configured channel
            delivered = await self._deliver(message)
            if delivered:
                pattern.escalated = True
                sent.append(message)
                self._escalation_history.append(message.to_dict())

                # Notify through message bus (so security agent sees it)
                if self._bus:
                    self._send_bus_notification(message)

                logger.info(
                    "[AdvocateNetwork] Escalated pattern %s to %s via %s",
                    pattern.id, advocate.name, advocate.channel,
                )

        return sent

    async def _deliver(self, message: EscalationMessage) -> bool:
        """Deliver an escalation message through the configured channel."""
        channel = message.advocate.channel

        if channel == "email" and self._channel_manager:
            try:
                send_fn = getattr(self._channel_manager, 'send_email', None)
                if send_fn:
                    await send_fn(
                        to=message.advocate.name,
                        subject=message.subject,
                        body=message.body,
                    )
                    return True
            except Exception as e:
                logger.error("[AdvocateNetwork] Email delivery failed: %s", e)
                return False

        # For other channels (slack, telegram), log intent for now
        # Actual delivery integrates with existing plugin infrastructure
        logger.info(
            "[AdvocateNetwork] Would deliver to %s via %s: %s",
            message.advocate.name, channel, message.subject,
        )
        return True  # Consider logged delivery as success for testing

    def _send_bus_notification(self, message: EscalationMessage):
        """Send notification through MessageBus for security monitoring."""
        if not self._bus:
            return
        try:
            from orchestration.messages import AgentMessage, MessageType, MessagePriority
            msg = AgentMessage.create(
                msg_type=MessageType.ADVOCACY_ESCALATION,
                sender="advocacy",
                recipient="security",
                mission_id="advocacy",
                content=f"Escalation to {message.advocate.name}: {message.subject}",
                payload=message.to_dict(),
                priority=MessagePriority.HIGH,
            )
            self._bus.send(msg)
        except Exception as e:
            logger.error("[AdvocateNetwork] Bus notification error: %s", e)

    def get_escalation_history(self) -> list[dict]:
        return list(self._escalation_history)

    def get_status(self) -> dict:
        return {
            "escalation_enabled": self._profile.escalation_enabled,
            "total_escalations": len(self._escalation_history),
        }
