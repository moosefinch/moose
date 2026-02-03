"""
AgentRegistry — central registry for all system agents.
"""

from typing import Optional

from agents.base import BaseAgent


class AgentRegistry:
    """Manages registration and lookup of all system agents."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        """Register an agent by its agent_id."""
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def all(self) -> list[BaseAgent]:
        """Return all registered agents."""
        return list(self._agents.values())

    def by_capability(self, capability: str) -> list[BaseAgent]:
        """Find agents that have a specific capability."""
        return [
            a for a in self._agents.values()
            if capability in a.definition.capabilities
        ]

    def ids(self) -> list[str]:
        """Return all registered agent IDs."""
        return list(self._agents.keys())

    def route_task(self, task: dict) -> Optional[BaseAgent]:
        """Find the best agent for a planner task.

        Looks up by model key first (exact match), then falls back to
        capability-based routing.
        """
        model_key = task.get("model", "hermes")

        # Direct model key match
        agent = self._agents.get(model_key)
        if agent:
            return agent

        # Capability fallback — check if the task description hints at capabilities
        if task.get("security_consultation"):
            candidates = self.by_capability("security")
            if candidates:
                return candidates[0]

        # Default to hermes
        return self._agents.get("hermes")
