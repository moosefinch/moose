"""
ContentAgent — content creation specialist.
Routes inference to central engine with filtered content tools.
"""

import json
from typing import Optional

from agents.base import BaseAgent, AgentDefinition, AgentState, ModelSize, register_agent_class
from plugins.crm.prompts import CONTENT_SYSTEM_PROMPT
from config import TOKEN_LIMITS, MAX_TOOL_ROUNDS
from orchestration.messages import AgentMessage, MessageType


@register_agent_class
class ContentAgent(BaseAgent):
    AGENT_ID = "content"

    def __init__(self, agent_core):
        definition = AgentDefinition(
            agent_id="content",
            model_key="hermes",          # Routes to Hermes 70B central engine
            model_size=ModelSize.SMALL,
            can_use_tools=True,
            capabilities=[
                "blog_writing", "social_media", "landing_pages",
                "content_strategy", "copywriting",
            ],
            max_tokens=TOKEN_LIMITS.get("hermes", 4096),
            temperature=0.7,
        )
        super().__init__(definition, agent_core)

    async def run(self, message: AgentMessage, bus, workspace) -> Optional[AgentMessage]:
        """Execute a content creation task with tool-calling loop."""
        self.state = AgentState.RUNNING

        try:
            mission_id = message.mission_id
            task_desc = message.content
            task_id = message.payload.get("task_id", message.id)
            tool_plan = message.payload.get("tool_plan")

            system_prompt = CONTENT_SYSTEM_PROMPT

            user_content = task_desc
            if tool_plan and isinstance(tool_plan, list):
                plan_steps = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(tool_plan))
                user_content += f"\n\n[Planner suggested tool calls]:\n{plan_steps}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            tool_calls_log = []
            response_text = ""
            exec_schemas = self.get_tool_schemas()
            tools_needed = message.payload.get("tools_needed", True)
            seen_calls = set()

            for _round in range(MAX_TOOL_ROUNDS):
                result = await self.call_llm(
                    messages,
                    tools=exec_schemas if tools_needed else None,
                )
                choice = result["choices"][0]
                msg = choice["message"]
                finish = choice.get("finish_reason", "")

                if finish == "tool_calls" and msg.get("tool_calls"):
                    messages.append(msg)
                    for tc in msg["tool_calls"]:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError as e:
                            messages.append({"role": "tool", "tool_call_id": tc["id"],
                                "content": f"JSON parse error: {e}. Raw: {tc['function']['arguments'][:200]}"})
                            continue

                        call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
                        if call_sig in seen_calls:
                            messages.append({"role": "tool", "tool_call_id": tc["id"],
                                "content": f"Skipped: duplicate call to {fn_name} with same arguments."})
                            continue
                        seen_calls.add(call_sig)

                        tool_result = await self.execute_tool(fn_name, fn_args)
                        tool_calls_log.append({"tool": fn_name, "args": fn_args, "result": str(tool_result)[:500]})
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(tool_result)})
                else:
                    response_text = msg.get("content", "") or ""
                    break
            else:
                response_text = "[Hit tool-call limit]"

            self.post_to_workspace(
                workspace, mission_id, "finding",
                f"Content: {task_desc[:60]}",
                response_text,
                tags=["content", "marketing", "execution"],
            )

            self.state = AgentState.IDLE
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=mission_id,
                content=response_text,
                payload={"task_id": task_id, "tool_calls": tool_calls_log, "model": "hermes"},
                parent_msg_id=message.id,
            )

        except Exception as e:
            self.state = AgentState.ERROR
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=f"Content error: {e}",
                payload={"error": True, "task_id": message.payload.get("task_id", "")},
                parent_msg_id=message.id,
            )
