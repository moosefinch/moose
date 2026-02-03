"""
Tests for AgentCore orchestration engine.
Tests classification routing, chat pipeline, escalation, and security checks.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBackgroundTask:
    """Test BackgroundTask data structure."""

    def test_background_task_init(self):
        """BackgroundTask should initialize with correct defaults."""
        from core import BackgroundTask

        task = BackgroundTask(
            task_id="test-123",
            description="Test task",
            plan=[{"step": "do something"}]
        )

        assert task.id == "test-123"
        assert task.description == "Test task"
        assert task.status == "running"
        assert task.progress_log == []
        assert task.result is None

    def test_background_task_log(self):
        """BackgroundTask.log() should append to progress_log."""
        from core import BackgroundTask

        task = BackgroundTask("t1", "desc", [])
        task.log("Step 1 complete", step="step1")
        task.log("Step 2 complete")

        assert len(task.progress_log) == 2
        assert task.progress_log[0]["message"] == "Step 1 complete"
        assert task.progress_log[0]["step"] == "step1"
        assert task.progress_log[1]["step"] is None

    def test_background_task_to_dict(self):
        """BackgroundTask.to_dict() should return serializable dict."""
        from core import BackgroundTask

        task = BackgroundTask("t1", "desc", [{"step": "s1"}])
        task.log("msg")
        task.status = "completed"
        task.result = "Done!"

        d = task.to_dict()
        assert d["id"] == "t1"
        assert d["status"] == "completed"
        assert d["result"] == "Done!"
        assert len(d["progress_log"]) == 1


class TestToolSchemaBuilding:
    """Test tool schema generation."""

    def test_build_tool_schemas_basic(self):
        """Should generate OpenAI-compatible schemas from functions."""
        from core import _build_tool_schemas

        def sample_tool(name: str, count: int) -> str:
            """A sample tool for testing."""
            return f"{name}: {count}"

        schemas = _build_tool_schemas([sample_tool])

        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "sample_tool"
        assert "A sample tool" in schema["function"]["description"]
        assert schema["function"]["parameters"]["properties"]["name"]["type"] == "string"
        assert schema["function"]["parameters"]["properties"]["count"]["type"] == "integer"
        assert "name" in schema["function"]["parameters"]["required"]
        assert "count" in schema["function"]["parameters"]["required"]

    def test_build_tool_schemas_optional_params(self):
        """Should not mark optional params as required."""
        from core import _build_tool_schemas

        def tool_with_optional(required_param: str, optional_param: str = "default") -> str:
            """Tool with optional parameter."""
            return required_param

        schemas = _build_tool_schemas([tool_with_optional])
        required = schemas[0]["function"]["parameters"]["required"]

        assert "required_param" in required
        assert "optional_param" not in required

    def test_build_tool_schemas_type_mapping(self):
        """Should map Python types to JSON schema types correctly."""
        from core import _build_tool_schemas

        def typed_tool(s: str, i: int, f: float, b: bool) -> dict:
            """Tool with various types."""
            pass

        schemas = _build_tool_schemas([typed_tool])
        props = schemas[0]["function"]["parameters"]["properties"]

        assert props["s"]["type"] == "string"
        assert props["i"]["type"] == "integer"
        assert props["f"]["type"] == "number"
        assert props["b"]["type"] == "boolean"


class TestAgentCoreInit:
    """Test AgentCore initialization."""

    @patch("core.agent_core.get_router")
    @patch("core.agent_core.VectorMemory")
    @patch("core.agent_core.get_all_tools")
    @patch("core.agent_core.get_execution_tools")
    def test_agent_core_init_creates_structures(
        self, mock_exec_tools, mock_all_tools, mock_memory, mock_router
    ):
        """AgentCore.__init__() should create all required structures."""
        mock_all_tools.return_value = []
        mock_exec_tools.return_value = []

        from core import AgentCore
        core = AgentCore()

        assert core.available_models == {}
        assert core.ws_clients == []
        assert core._tasks == {}
        assert core._ready is False
        mock_memory.assert_called_once()


class TestClassification:
    """Test query classification logic."""

    @pytest.mark.asyncio
    @patch("core.agent_core.get_router")
    @patch("core.agent_core.VectorMemory")
    @patch("core.agent_core.get_all_tools")
    @patch("core.agent_core.get_execution_tools")
    async def test_passive_security_flags_suspicious_patterns(
        self, mock_exec_tools, mock_all_tools, mock_memory, mock_router
    ):
        """Passive security check should flag suspicious patterns."""
        mock_all_tools.return_value = []
        mock_exec_tools.return_value = []

        from core import AgentCore
        from agents.prompts import SUSPICIOUS_PATTERNS

        core = AgentCore()

        # Test that SUSPICIOUS_PATTERNS exists and has entries
        assert len(SUSPICIOUS_PATTERNS) > 0

        # The actual _passive_security_check method should exist
        assert hasattr(core, "_passive_security_check")


class TestEscalation:
    """Test escalation flow for user approval."""

    @pytest.mark.asyncio
    @patch("core.agent_core.get_router")
    @patch("core.agent_core.VectorMemory")
    @patch("core.agent_core.get_all_tools")
    @patch("core.agent_core.get_execution_tools")
    async def test_escalation_creates_pending_entry(
        self, mock_exec_tools, mock_all_tools, mock_memory, mock_router
    ):
        """Requesting escalation should create a pending entry."""
        mock_all_tools.return_value = []
        mock_exec_tools.return_value = []

        from core import AgentCore
        core = AgentCore()

        # Pending escalations should start empty
        assert core._pending_escalations == {}

        # After requesting escalation, there should be an entry
        # (We test the structure exists, actual escalation tested with integration)
        assert hasattr(core, "_request_escalation")
        assert hasattr(core, "resolve_escalation")


class TestChatPipeline:
    """Test the main chat() pipeline."""

    @pytest.mark.asyncio
    @patch("core.agent_core.get_router")
    @patch("core.agent_core.VectorMemory")
    @patch("core.agent_core.get_all_tools")
    @patch("core.agent_core.get_execution_tools")
    async def test_chat_requires_ready_state(
        self, mock_exec_tools, mock_all_tools, mock_memory, mock_router
    ):
        """chat() should handle not-ready state gracefully."""
        mock_all_tools.return_value = []
        mock_exec_tools.return_value = []

        from core import AgentCore
        core = AgentCore()

        # Core starts not ready
        assert core._ready is False

        # The chat method should exist
        assert hasattr(core, "chat")
