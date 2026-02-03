"""
ReasonerAgent — Mission planner and escalation detector.

Routes inference to Hermes 4 70B central engine. Always loaded. Text-only.
Plans missions, detects when tasks exceed the fleet's capability and
triggers escalation. No persona — pure task decomposition and routing.
"""

import json
from typing import Optional

from agents.base import BaseAgent, AgentDefinition, AgentState, ModelSize, register_agent_class
from agents.prompts import PLANNER_PROMPT
from config import TOKEN_LIMITS, TEMPERATURE, CONTEXT_WINDOW_SIZE, ESCALATION_CONFIG, PLANNER_MODEL
from orchestration.messages import AgentMessage, MessageType

import logging

logger = logging.getLogger(__name__)


@register_agent_class
class ReasonerAgent(BaseAgent):
    """Mission planner — decomposes user requests into task graphs.

    Routes to Hermes 4 70B central engine. Text-only (no vision — voice handles images).
    Also detects when a task needs escalation (user or Claude).
    """
    AGENT_ID = "reasoner"

    def __init__(self, agent_core):
        definition = AgentDefinition(
            agent_id="reasoner",
            model_key="hermes",          # Routes to Hermes 70B central engine
            model_size=ModelSize.SMALL,
            can_use_tools=True,
            capabilities=["planning", "reasoning", "analysis", "tool_calling", "escalation_detection"],
            max_tokens=TOKEN_LIMITS.get("hermes", 4096),
            temperature=TEMPERATURE.get("planner", 0.3),
        )
        super().__init__(definition, agent_core)

    async def plan(self, user_message: str, history: list = None) -> dict:
        """Decompose a user request into a task graph.

        Returns a plan dict with complexity, response_tier, tasks, synthesize, plan_summary.
        """
        tool_desc = self._core._build_tool_descriptions()
        planner_system = PLANNER_PROMPT.replace("{tool_descriptions}", tool_desc)

        history_summary = ""
        if history:
            recent = history[-CONTEXT_WINDOW_SIZE:]
            history_summary = "\n\nRecent conversation:\n" + "\n".join(
                f"{h['role']}: {h['content'][:200]}" for h in recent
            )

        user_prompt = f"User request: {user_message}{history_summary}"

        try:
            result = await self.call_llm(
                [
                    {"role": "system", "content": planner_system},
                    {"role": "user", "content": user_prompt},
                ],
                model_key_override=PLANNER_MODEL,
            )
            raw = result["choices"][0]["message"].get("content", "").strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            plan = json.loads(raw)

            if "tasks" not in plan or not isinstance(plan["tasks"], list):
                raise ValueError("Plan missing 'tasks' array")

            for i, t in enumerate(plan["tasks"]):
                if "id" not in t:
                    t["id"] = f"t{i+1}"
                if "depends_on" not in t:
                    t["depends_on"] = []

            return {
                "complexity": plan.get("complexity", "medium"),
                "response_tier": plan.get("response_tier", "enhanced"),
                "tasks": plan["tasks"],
                "synthesize": plan.get("synthesize", True),
                "plan_summary": plan.get("plan_summary", ""),
                "needs_escalation": plan.get("needs_escalation", False),
            }
        except Exception as e:
            logger.error("Planning failed: %s", e)
            # Fallback: single task to the most appropriate agent
            return {
                "complexity": "simple",
                "response_tier": "immediate",
                "tasks": [{"id": "t1", "model": "coder", "task": user_message, "tools_needed": True, "depends_on": []}],
                "synthesize": False,
                "plan_summary": f"Planning failed ({e}) — direct fallback",
                "needs_escalation": False,
            }

    async def run(self, message: AgentMessage, bus, workspace) -> Optional[AgentMessage]:
        """Handle planning requests via message bus."""
        self.state = AgentState.RUNNING

        try:
            action = message.payload.get("action", "planning")

            if action == "planning":
                plan = await self.plan(
                    message.content,
                    history=message.payload.get("history"),
                )
                self.state = AgentState.IDLE
                return AgentMessage.create(
                    msg_type=MessageType.RESULT,
                    sender=self.agent_id,
                    recipient=message.sender,
                    mission_id=message.mission_id,
                    content=json.dumps(plan),
                    payload={"plan": plan},
                    parent_msg_id=message.id,
                )
            else:
                # General reasoning task
                result = await self.call_llm([
                    {"role": "user", "content": message.content},
                ])
                text = result["choices"][0]["message"].get("content", "")

                self.post_to_workspace(
                    workspace, message.mission_id, "analysis",
                    f"Reasoner: {message.content[:60]}",
                    text,
                    tags=["reasoner", "analysis"],
                )

                self.state = AgentState.IDLE
                return AgentMessage.create(
                    msg_type=MessageType.RESULT,
                    sender=self.agent_id,
                    recipient=message.sender,
                    mission_id=message.mission_id,
                    content=text,
                    payload={"task_id": message.payload.get("task_id", message.id)},
                    parent_msg_id=message.id,
                )

        except Exception as e:
            self.state = AgentState.ERROR
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=f"Reasoner error: {e}",
                payload={"error": True},
                parent_msg_id=message.id,
            )
