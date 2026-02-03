"""
Rust GPU Scheduler - Drop-in replacement using Rust backend.

This module provides a Python wrapper around the Rust Scheduler implementation
for backwards compatibility with existing code.
"""

from typing import Any, Callable, Optional

try:
    from moose_core import Scheduler as RustScheduler, MessageBus as RustMessageBus
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    RustScheduler = None
    RustMessageBus = None


class MessageBus:
    """
    Drop-in replacement for the Python MessageBus using Rust backend.

    Features:
    - SQLite-backed persistence with WAL mode
    - Priority-based message ordering
    - Prompt injection detection
    - Monitor hooks for security
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the MessageBus.

        Args:
            db_path: Path to SQLite database file
        """
        if not RUST_AVAILABLE:
            raise ImportError(
                "moose_core Rust extension not available. "
                "Build with: cd backend/rust_core && maturin develop --release"
            )

        self._inner = RustMessageBus(db_path)

    def send(self, msg: dict) -> str:
        """
        Send a message.

        Args:
            msg: Message dictionary with keys:
                - msg_type: Message type
                - sender: Sender agent ID
                - recipient: Recipient agent ID
                - mission_id: Mission ID
                - content: Message content
                - parent_msg_id: Optional parent message ID
                - priority: Message priority (0-3)
                - payload: Additional payload

        Returns:
            Message ID
        """
        return self._inner.send(msg)

    def pop_next(self, agent_id: str) -> Optional[dict]:
        """
        Pop the next highest-priority message for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Message dict or None if no pending messages
        """
        return self._inner.pop_next(agent_id)

    def get_pending(self, agent_id: str) -> list[dict]:
        """
        Get pending messages for an agent without removing them.

        Args:
            agent_id: Agent ID

        Returns:
            List of pending messages
        """
        return list(self._inner.get_pending(agent_id))

    def has_pending(self, agent_id: str) -> bool:
        """
        Check if an agent has pending messages.

        Args:
            agent_id: Agent ID

        Returns:
            True if agent has pending messages
        """
        return self._inner.has_pending(agent_id)

    def agents_with_pending_messages(self) -> list[str]:
        """
        Get list of agents with pending messages.

        Returns:
            List of agent IDs
        """
        return self._inner.agents_with_pending_messages()

    def get_mission_messages(self, mission_id: str) -> list[dict]:
        """
        Get all messages for a mission.

        Args:
            mission_id: Mission ID

        Returns:
            List of messages
        """
        return list(self._inner.get_mission_messages(mission_id))

    def mark_processed(self, msg_id: str) -> bool:
        """
        Mark a message as processed.

        Args:
            msg_id: Message ID

        Returns:
            True if marked, False if not found
        """
        return self._inner.mark_processed(msg_id)

    def register_monitor_hook(self, hook: Callable[[dict], None]) -> None:
        """
        Register a monitor hook (called on every send).

        Args:
            hook: Callable that receives message dict
        """
        self._inner.register_monitor_hook(hook)

    def get_message(self, msg_id: str) -> Optional[dict]:
        """
        Get a message by ID.

        Args:
            msg_id: Message ID

        Returns:
            Message dict or None if not found
        """
        return self._inner.get_message(msg_id)

    def clear(self) -> None:
        """Clear all messages."""
        self._inner.clear()

    def count(self) -> int:
        """Get total message count."""
        return self._inner.count()

    def pending_count(self) -> int:
        """Get pending message count."""
        return self._inner.pending_count()


class Scheduler:
    """
    Drop-in replacement for the Python GPUScheduler using Rust backend.

    Features:
    - Event-driven dispatch (replaces polling)
    - Lock-free mission state with DashMap
    - Dependency-level task grouping
    - Integration with MessageBus
    """

    def __init__(self, poll_interval_ms: int = 50):
        """
        Initialize the Scheduler.

        Args:
            poll_interval_ms: Poll interval in milliseconds
        """
        if not RUST_AVAILABLE:
            raise ImportError(
                "moose_core Rust extension not available. "
                "Build with: cd backend/rust_core && maturin develop --release"
            )

        self._inner = RustScheduler(poll_interval_ms)

    def set_message_bus(self, bus: MessageBus) -> None:
        """
        Set the message bus.

        Args:
            bus: MessageBus instance
        """
        self._inner.set_message_bus(bus._inner)

    def set_security_monitor(self, monitor: Any) -> None:
        """
        Set the security monitor agent.

        Args:
            monitor: Security monitor agent
        """
        self._inner.set_security_monitor(monitor)

    def submit_mission(
        self,
        mission_id: str,
        tasks: list[dict],
        synthesize: bool = True,
        user_message: str = "",
        history: Optional[list[dict]] = None,
    ) -> None:
        """
        Submit a new mission.

        Args:
            mission_id: Unique mission ID
            tasks: List of task dictionaries with keys:
                - id: Task ID
                - agent_id: Agent to execute task
                - model_key: Model to use
                - task: Task description
                - depends_on: List of task IDs this depends on
            synthesize: Whether to synthesize results
            user_message: Original user message
            history: Conversation history
        """
        self._inner.submit_mission(
            mission_id,
            tasks,
            synthesize,
            user_message,
            history,
        )

    async def await_mission(
        self,
        mission_id: str,
        timeout: float = 600.0,
    ) -> dict:
        """
        Await mission completion.

        Args:
            mission_id: Mission ID
            timeout: Timeout in seconds

        Returns:
            Mission result dictionary
        """
        return await self._inner.await_mission(mission_id, timeout)

    def get_mission(self, mission_id: str) -> Optional[dict]:
        """
        Get mission by ID.

        Args:
            mission_id: Mission ID

        Returns:
            Mission dict or None if not found
        """
        return self._inner.get_mission(mission_id)

    def complete_task(
        self,
        mission_id: str,
        task_id: str,
        result: Optional[str] = None,
        tool_calls: Optional[list[str]] = None,
    ) -> bool:
        """
        Complete a task within a mission.

        Args:
            mission_id: Mission ID
            task_id: Task ID
            result: Task result
            tool_calls: List of tool call JSON strings

        Returns:
            True if task was completed
        """
        return self._inner.complete_task(mission_id, task_id, result, tool_calls)

    def fail_task(
        self,
        mission_id: str,
        task_id: str,
        error: str,
    ) -> bool:
        """
        Fail a task within a mission.

        Args:
            mission_id: Mission ID
            task_id: Task ID
            error: Error message

        Returns:
            True if task was failed
        """
        return self._inner.fail_task(mission_id, task_id, error)

    def get_ready_tasks(self, mission_id: str) -> list[dict]:
        """
        Get tasks ready to execute (current level, not started).

        Args:
            mission_id: Mission ID

        Returns:
            List of ready tasks
        """
        return list(self._inner.get_ready_tasks(mission_id))

    def start_task(self, mission_id: str, task_id: str) -> bool:
        """
        Mark a task as started.

        Args:
            mission_id: Mission ID
            task_id: Task ID

        Returns:
            True if task was started
        """
        return self._inner.start_task(mission_id, task_id)

    async def start_loop(self, agent_runner: Callable) -> None:
        """
        Start the scheduler loop.

        Args:
            agent_runner: Callable to run agents
        """
        await self._inner.start_loop(agent_runner)

    def stop_loop(self) -> None:
        """Stop the scheduler loop."""
        self._inner.stop_loop()

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._inner.is_running()

    def list_missions(self) -> list[str]:
        """Get all mission IDs."""
        return self._inner.list_missions()

    def mission_count(self) -> int:
        """Get mission count."""
        return self._inner.mission_count()

    def clear_completed(self) -> int:
        """
        Clear completed missions.

        Returns:
            Number of missions cleared
        """
        return self._inner.clear_completed()

    def cancel_mission(self, mission_id: str) -> bool:
        """
        Cancel a mission.

        Args:
            mission_id: Mission ID

        Returns:
            True if mission was cancelled
        """
        return self._inner.cancel_mission(mission_id)

    def get_inflight(self, model_key: str) -> int:
        """
        Get inflight count for a model.

        Args:
            model_key: Model key

        Returns:
            Number of inflight requests
        """
        return self._inner.get_inflight(model_key)

    def inc_inflight(self, model_key: str) -> None:
        """Increment inflight count for a model."""
        self._inner.inc_inflight(model_key)

    def dec_inflight(self, model_key: str) -> None:
        """Decrement inflight count for a model."""
        self._inner.dec_inflight(model_key)


# Alias for backwards compatibility
GPUScheduler = Scheduler


# Export for backwards compatibility
__all__ = ["Scheduler", "GPUScheduler", "MessageBus", "RUST_AVAILABLE"]
