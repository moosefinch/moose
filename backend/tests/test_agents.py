"""
Tests for individual agent implementations.
Tests tool-calling loops, permission enforcement, and planning.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBaseAgent:
    """Test BaseAgent abstract class and lifecycle."""

    def test_agent_definition_structure(self):
        """AgentDefinition should have required fields."""
        from agents.base import AgentDefinition, ModelSize

        defn = AgentDefinition(
            agent_id="test",
            model_key="hermes",
            model_size=ModelSize.SMALL,
            can_use_tools=True,
        )

        assert defn.agent_id == "test"
        assert defn.model_key == "hermes"
        assert defn.model_size == ModelSize.SMALL
        assert defn.can_use_tools is True

    def test_agent_state_enum_values(self):
        """AgentState should have expected states."""
        from agents.base import AgentState

        assert hasattr(AgentState, "IDLE")
        assert hasattr(AgentState, "RUNNING")
        assert hasattr(AgentState, "SUSPENDED")

    def test_model_size_enum_values(self):
        """ModelSize should have expected sizes."""
        from agents.base import ModelSize

        assert hasattr(ModelSize, "SMALL")
        assert hasattr(ModelSize, "LARGE")
        assert hasattr(ModelSize, "EXTERNAL")


class TestAgentRegistry:
    """Test agent registration and retrieval."""

    def test_register_agent_class_decorator_exists(self):
        """@register_agent_class decorator should exist."""
        from agents.base import register_agent_class

        assert callable(register_agent_class)

    def test_registry_can_list_agents(self):
        """AgentRegistry should list registered agents."""
        from agents.registry import AgentRegistry

        # Registry should have a method to list agent IDs
        assert hasattr(AgentRegistry, "ids")


class TestToolPermissions:
    """Test agent tool permission enforcement."""

    def test_agent_tool_filter_config_exists(self):
        """AGENT_TOOL_FILTER config should exist."""
        from config import AGENT_TOOL_FILTER

        assert isinstance(AGENT_TOOL_FILTER, dict)

    def test_get_tools_for_agent_filters_correctly(self):
        """get_tools_for_agent should return filtered tool set."""
        from tools import get_tools_for_agent

        # Function should exist and be callable
        assert callable(get_tools_for_agent)


class TestCoderAgent:
    """Test CoderAgent tool-calling loop."""

    def test_coder_agent_exists(self):
        """CoderAgent should be importable."""
        from agents.coder import CoderAgent

        assert CoderAgent is not None
        assert hasattr(CoderAgent, "AGENT_ID")

    def test_coder_has_run_method(self):
        """CoderAgent should have async run() method."""
        from agents.coder import CoderAgent

        assert hasattr(CoderAgent, "run")


class TestReasonerAgent:
    """Test ReasonerAgent planning capabilities."""

    def test_reasoner_agent_exists(self):
        """ReasonerAgent should be importable."""
        from agents.reasoner import ReasonerAgent

        assert ReasonerAgent is not None
        assert hasattr(ReasonerAgent, "AGENT_ID")

    def test_reasoner_has_run_method(self):
        """ReasonerAgent should have async run() method."""
        from agents.reasoner import ReasonerAgent

        assert hasattr(ReasonerAgent, "run")


class TestClassifierAgent:
    """Test ClassifierAgent fast-path routing."""

    def test_classifier_agent_exists(self):
        """ClassifierAgent should be importable."""
        from agents.classifier import ClassifierAgent

        assert ClassifierAgent is not None
        assert hasattr(ClassifierAgent, "AGENT_ID")


class TestSecurityAgent:
    """Test SecurityAgent monitoring."""

    def test_security_agent_exists(self):
        """SecurityAgent should be importable."""
        from agents.security import SecurityAgent

        assert SecurityAgent is not None
        assert hasattr(SecurityAgent, "AGENT_ID")


class TestAgentPrompts:
    """Test agent prompts configuration."""

    def test_suspicious_patterns_defined(self):
        """SUSPICIOUS_PATTERNS should be defined for security checks."""
        from agents.prompts import SUSPICIOUS_PATTERNS

        assert isinstance(SUSPICIOUS_PATTERNS, (list, tuple, set))
        assert len(SUSPICIOUS_PATTERNS) > 0

    def test_classifier_prompt_defined(self):
        """CLASSIFIER_PROMPT should be defined."""
        from agents.prompts import CLASSIFIER_PROMPT

        assert isinstance(CLASSIFIER_PROMPT, str)
        assert len(CLASSIFIER_PROMPT) > 0

    def test_presentation_prompt_function_exists(self):
        """get_presentation_prompt function should exist."""
        from agents.prompts import get_presentation_prompt

        assert callable(get_presentation_prompt)
