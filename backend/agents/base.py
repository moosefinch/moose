"""
Base agent abstraction for Moose multi-agent architecture.

Provides AgentState, ModelSize, AgentDefinition, and BaseAgent — the foundation
that all specialist agents inherit from.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


class AgentState(Enum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    ERROR = "error"


class ModelSize(Enum):
    LARGE = "large"
    SMALL = "small"
    EXTERNAL = "external"
    NONE = "none"


@dataclass
class AgentDefinition:
    agent_id: str
    model_key: str
    model_size: ModelSize
    can_use_tools: bool
    capabilities: list[str] = field(default_factory=list)
    max_tokens: int = 2048
    temperature: float = 0.7


class BaseAgent(ABC):
    """Base class for all Moose agents.

    Provides model lifecycle management, message handling, workspace access,
    and LLM/tool delegation through the AgentCore reference.

    ## Agent Protocol

    Every agent subclass must:
    1. Define an AGENT_ID class attribute (str) — unique identifier.
    2. Implement __init__(self, agent_core) that builds an AgentDefinition
       and calls super().__init__(definition, agent_core).
    3. Implement async run(self, message, bus, workspace) -> Optional[AgentMessage].
       Returns RESULT when done, PROGRESS if waiting on another agent.
    4. Decorate the class with @register_agent_class to enable auto-registration.
    """

    # Class-level registry: agent_id -> agent class
    _registry: dict[str, type] = {}

    @classmethod
    def create_all(cls, agent_core) -> dict[str, "BaseAgent"]:
        """Instantiate all registered agent classes, keyed by agent_id."""
        return {aid: acls(agent_core) for aid, acls in cls._registry.items()}

    def __init__(self, definition: AgentDefinition, agent_core):
        self.definition = definition
        self.agent_id = definition.agent_id
        self.model_key = definition.model_key
        self.model_size = definition.model_size
        self.can_use_tools = definition.can_use_tools
        self.state = AgentState.IDLE
        self._core = agent_core
        self._pending_messages: list = []
        self._suspended_state: Optional[dict] = None

    # ── Model Lifecycle ──

    async def activate(self) -> bool:
        """No-op — all models are always loaded."""
        self.state = AgentState.IDLE
        return True

    async def deactivate(self) -> bool:
        """No-op — all models are always loaded."""
        self.state = AgentState.IDLE
        return True

    def suspend(self) -> dict:
        """Serialize agent state for GPU swap. Returns state dict."""
        self._suspended_state = {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "pending_messages": list(self._pending_messages),
            "suspended_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state = AgentState.SUSPENDED
        return self._suspended_state

    def resume(self, saved_state: dict = None):
        """Restore agent state after GPU swap."""
        state = saved_state or self._suspended_state
        if state:
            self._pending_messages = state.get("pending_messages", [])
        self.state = AgentState.IDLE
        self._suspended_state = None

    # ── Message Handling ──

    def receive(self, message):
        """Add a message to this agent's pending queue."""
        self._pending_messages.append(message)

    def has_pending(self) -> bool:
        return len(self._pending_messages) > 0

    def pop_message(self):
        """Pop the next pending message (FIFO)."""
        if self._pending_messages:
            return self._pending_messages.pop(0)
        return None

    # ── Abstract Run ──

    @abstractmethod
    async def run(self, message, bus, workspace) -> Optional[Any]:
        """Process a message. Subclasses implement task-specific logic.

        Args:
            message: AgentMessage to process
            bus: MessageBus for inter-agent communication
            workspace: SharedWorkspace for posting/reading findings

        Returns:
            Optional response message, or None if work is complete.
        """
        ...

    # ── LLM Delegation ──

    # ── Tool Schema Access ──

    def get_tool_schemas(self) -> list[dict]:
        """Get filtered tool schemas for this agent via AgentCore cache."""
        return self._core.get_agent_tool_schemas(self.agent_id)

    async def call_llm(self, messages: list[dict], tools: list[dict] = None,
                       tool_choice: str = None, model_key_override: str = None) -> dict:
        """Delegate an LLM call to AgentCore._call_llm with this agent's model.

        Args:
            model_key_override: Use a different model key for this call (e.g. for planning).
        """
        from config import MODELS
        key = model_key_override or self.model_key
        model_id = MODELS.get(key)
        if not model_id:
            raise ValueError(f"Unknown model key: {key}")

        return await self._core._call_llm(
            model_id, messages,
            tools=tools,
            max_tokens=self.definition.max_tokens,
            temperature=self.definition.temperature,
            tool_choice=tool_choice,
        )

    async def call_llm_stream(self, messages: list[dict],
                              on_chunk: Callable[[str], Any] = None) -> str:
        """Streaming LLM call. on_chunk(content: str) called per token.

        Returns the full accumulated response text.
        """
        from config import MODELS
        model_id = MODELS.get(self.model_key)
        if not model_id:
            raise ValueError(f"Unknown model key: {self.model_key}")

        return await self._core.inference.call_llm_stream(
            model_id, messages,
            max_tokens=self.definition.max_tokens,
            temperature=self.definition.temperature,
            on_chunk=on_chunk,
        )

    # ── Tool Execution ──

    async def execute_tool(self, name: str, args: dict) -> str:
        """Execute a tool via core._execute_tool. Only if can_use_tools.

        Enforces AGENT_TOOL_FILTER at runtime — agents can only call tools
        in their allowed set, regardless of what the LLM requests.
        """
        if not self.can_use_tools:
            return f"Error: agent {self.agent_id} cannot use tools"
        from config import AGENT_TOOL_FILTER
        allowed = AGENT_TOOL_FILTER.get(self.agent_id)
        # allowed=None means all tools permitted; [] means none; list means only those
        if allowed is not None and name not in allowed:
            return f"Error: agent {self.agent_id} is not permitted to use tool '{name}'"
        return await self._core._execute_tool(name, args)

    # ── Workspace Access ──

    def post_to_workspace(self, workspace, mission_id: str, entry_type: str,
                          title: str, content: str, tags: list[str] = None,
                          references: list[str] = None):
        """Post an entry to the shared workspace."""
        from orchestration.workspace import WorkspaceEntry
        entry = WorkspaceEntry(
            id=str(uuid.uuid4())[:12],
            mission_id=mission_id,
            agent_id=self.agent_id,
            entry_type=entry_type,
            title=title,
            content=content,
            tags=tags or [],
            references=references or [],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        workspace.add(entry)
        return entry

    def read_workspace(self, workspace, mission_id: str, agent_id: str = None,
                       entry_type: str = None) -> list:
        """Read entries from the shared workspace."""
        return workspace.query(mission_id, agent_id=agent_id, entry_type=entry_type)

    # ── Channel Access ──

    def post_to_channel(self, channel_name: str, content: str, payload: dict = None):
        """Post a message to a named channel. Enforces permissions via ChannelManager."""
        if not hasattr(self._core, 'channel_manager') or not self._core.channel_manager:
            return None
        return self._core.channel_manager.post(channel_name, self.agent_id, content, payload)

    def read_channel(self, channel_name: str, since: str = None, limit: int = 50) -> list:
        """Read messages from a named channel. Enforces permissions via ChannelManager."""
        if not hasattr(self._core, 'channel_manager') or not self._core.channel_manager:
            return []
        return self._core.channel_manager.read(channel_name, self.agent_id, since=since, limit=limit)


def register_agent_class(cls):
    """Decorator to register an agent class for auto-registration.

    Usage:
        @register_agent_class
        class MyAgent(BaseAgent):
            AGENT_ID = "my_agent"
            ...
    """
    agent_id = getattr(cls, "AGENT_ID", None)
    if not agent_id:
        raise ValueError(f"Agent class {cls.__name__} must define AGENT_ID class attribute")
    BaseAgent._registry[agent_id] = cls
    return cls
