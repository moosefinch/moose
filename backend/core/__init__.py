"""
Core package — Multi-agent orchestration engine.

This package provides the AgentCore class and supporting modules.
The package structure allows for future modularization while maintaining
backward compatibility with existing imports.

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
