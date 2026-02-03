"""
Agent System — import all agents to trigger auto-registration.

Each agent decorated with @register_agent_class registers itself in
BaseAgent._registry on import. Importing this package ensures all
agents are available for BaseAgent.create_all().
"""

import logging

logger = logging.getLogger(__name__)

from agents.hermes import HermesAgent  # noqa: F401
from agents.security import SecurityAgent  # noqa: F401
from agents.classifier import ClassifierAgent  # noqa: F401
from agents.reasoner import ReasonerAgent  # noqa: F401
from agents.claude import ClaudeAgent  # noqa: F401
from agents.coder import CoderAgent  # noqa: F401
from agents.math_agent import MathAgent  # noqa: F401

# CRM plugin agents — imported conditionally
try:
    from profile import get_profile
    if get_profile().plugins.crm.enabled:
        from agents.outreach import OutreachAgent  # noqa: F401
        from agents.content import ContentAgent  # noqa: F401
except Exception:
    logger.debug("CRM plugin agents not available")
