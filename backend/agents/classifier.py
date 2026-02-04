"""
ClassifierAgent — Ultra-lightweight query classifier.

Qwen3-0.6B (~0.5GB). Always loaded. Classifies queries as TRIVIAL/SIMPLE/COMPLEX
in 10 tokens or less. No tools, no persona.
"""

from typing import Optional

from agents.base import BaseAgent, AgentDefinition, AgentState, ModelSize, register_agent_class
from agents.prompts import CLASSIFIER_PROMPT
from config import TOKEN_LIMITS, TEMPERATURE
from orchestration.messages import AgentMessage, MessageType

import logging

logger = logging.getLogger(__name__)


@register_agent_class
class ClassifierAgent(BaseAgent):
    AGENT_ID = "classifier"

    def __init__(self, agent_core):
        definition = AgentDefinition(
            agent_id="classifier",
            model_key="classifier",
            model_size=ModelSize.SMALL,
            can_use_tools=False,
            capabilities=["classification", "routing"],
            max_tokens=TOKEN_LIMITS.get("classifier", 10),
            temperature=TEMPERATURE.get("classifier", 0.1),
        )
        super().__init__(definition, agent_core)

    async def classify(self, query: str) -> str:
        """Classify a query into TRIVIAL, SIMPLE, or COMPLEX. Returns the tier string."""
        try:
            prompt = CLASSIFIER_PROMPT.format(query=query[:500])
            result = await self.call_llm([{"role": "user", "content": prompt}])
            response = result["choices"][0]["message"].get("content", "").strip()
            # Strip Qwen3 thinking tags if present
            import re
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip().upper()
            for tier in ("TRIVIAL", "SIMPLE", "COMPLEX"):
                if tier in response:
                    return tier
            return "COMPLEX"
        except Exception as e:
            logger.error("Classification error: %s", e)
            return "COMPLEX"

    async def run(self, message: AgentMessage, bus, workspace) -> Optional[AgentMessage]:
        """Classify a query via message bus (rarely used — classify() is called directly)."""
        self.state = AgentState.RUNNING
        try:
            tier = await self.classify(message.content)
            self.state = AgentState.IDLE
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=tier,
                payload={"tier": tier},
                parent_msg_id=message.id,
            )
        except Exception as e:
            self.state = AgentState.ERROR
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=f"Classifier error: {e}",
                payload={"error": True},
                parent_msg_id=message.id,
            )
