"""
Core package — Multi-agent orchestration engine.

This package provides the AgentCore class and supporting modules.

Structure:
    agent_core.py      — Main AgentCore class (~800 lines, down from 1425)
    background_tasks.py — BackgroundTask data class
    state.py           — Persistent state and SOUL.md management
    classification.py  — Query classification and trivial response handling
    escalation.py      — Escalation flow and presentation layer
    chat_pipeline.py   — Main chat() pipeline

Usage:
    from core import AgentCore
    from core import BackgroundTask
    from core import _build_tool_schemas
"""

# Re-export from agent_core for backward compatibility
from core.agent_core import (
    AgentCore,
    BackgroundTask,
    _build_tool_schemas,
)

__all__ = [
    "AgentCore",
    "BackgroundTask",
    "_build_tool_schemas",
]
