"""
ClaudeAgent — External Claude Code CLI for complex code tasks.

Cannot use tools (external). ModelSize.EXTERNAL.
"""

from typing import Optional

from agents.base import BaseAgent, AgentDefinition, AgentState, ModelSize, register_agent_class
from orchestration.messages import AgentMessage, MessageType
from tools import ask_claude


@register_agent_class
class ClaudeAgent(BaseAgent):
    AGENT_ID = "claude"

    def __init__(self, agent_core):
        definition = AgentDefinition(
            agent_id="claude",
            model_key="claude",
            model_size=ModelSize.EXTERNAL,
            can_use_tools=False,
            capabilities=["code", "refactoring", "debugging", "terminal"],
            max_tokens=4096,
            temperature=0.7,
        )
        super().__init__(definition, agent_core)

    async def run(self, message: AgentMessage, bus, workspace) -> Optional[AgentMessage]:
        """Call Claude Code CLI via tools.ask_claude, post results to workspace."""
        self.state = AgentState.RUNNING

        try:
            mission_id = message.mission_id
            task_id = message.payload.get("task_id", message.id)

            result = await ask_claude(message.content)

            # Post results to workspace
            self.post_to_workspace(
                workspace, mission_id, "finding",
                f"Claude: {message.content[:60]}",
                result,
                tags=["claude", "code"],
            )

            self.state = AgentState.IDLE
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=mission_id,
                content=result,
                payload={"task_id": task_id},
                parent_msg_id=message.id,
            )

        except Exception as e:
            self.state = AgentState.ERROR
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=f"Claude error: {e}",
                payload={"error": True},
                parent_msg_id=message.id,
            )
