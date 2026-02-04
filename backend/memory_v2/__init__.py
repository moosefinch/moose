"""
Moose Memory V2 — Self-aware, self-populating personal memory system.

This module provides:
- SystemAwareness: Hardware detection and resource monitoring
- UserModel: Self-populating user understanding
- EpisodicMemory: Vector-based semantic memory with adaptive importance
- ContextBuilder: Tiered context assembly for prompts
- MemoryV2: Main interface that coordinates all components
"""

from .system_awareness import SystemAwareness
from .user_model import UserModel
from .episodic import EpisodicMemory
from .context import ContextBuilder
from .core import MemoryV2

__all__ = [
    "SystemAwareness",
    "UserModel",
    "EpisodicMemory",
    "ContextBuilder",
    "MemoryV2",
]
