"""
MathAgent — Math, logic, data analysis specialist.

Cannot use tools. Routes inference to Hermes 70B. Pure reasoning.
"""

from typing import Optional

from agents.base import BaseAgent, AgentDefinition, AgentState, ModelSize, register_agent_class
from agents.prompts import MATH_SYSTEM_PROMPT
from config import TOKEN_LIMITS, TEMPERATURE
from orchestration.messages import AgentMessage, MessageType


@register_agent_class
class MathAgent(BaseAgent):
    AGENT_ID = "math"

    def __init__(self, agent_core):
        definition = AgentDefinition(
            agent_id="math",
            model_key="hermes",          # Routes to Hermes 70B central engine
            model_size=ModelSize.SMALL,
            can_use_tools=False,
            capabilities=["math", "logic", "data_analysis", "statistics"],
            max_tokens=TOKEN_LIMITS.get("hermes", 4096),
            temperature=0.2,
        )
        super().__init__(definition, agent_core)

    async def run(self, message: AgentMessage, bus, workspace) -> Optional[AgentMessage]:
        """Execute a math/logic task — pure reasoning, no tools."""
        self.state = AgentState.RUNNING

        try:
            mission_id = message.mission_id
            task_desc = message.content
            task_id = message.payload.get("task_id", message.id)

            system_prompt = MATH_SYSTEM_PROMPT

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_desc},
            ]

            result = await self.call_llm(messages)
            response_text = result["choices"][0]["message"].get("content", "") or ""

            self.post_to_workspace(
                workspace, mission_id, "finding",
                f"Math: {task_desc[:60]}",
                response_text,
                tags=["math", "reasoning", "execution"],
            )

            self.state = AgentState.IDLE
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=mission_id,
                content=response_text,
                payload={"task_id": task_id, "tool_calls": [], "model": "math"},
                parent_msg_id=message.id,
            )

        except Exception as e:
            self.state = AgentState.ERROR
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=f"Math error: {e}",
                payload={"error": True},
                parent_msg_id=message.id,
            )
