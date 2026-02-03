"""
HermesAgent — Deep reasoning engine, tool-caller. Always loaded.

Hermes 4 70B Q8 GGUF (~75GB). Central inference engine via llama.cpp
continuous batching. Always loaded — no swapping needed.

No planning, no synthesis — reasoner plans, voice speaks.
Hermes executes complex tasks with tools and security consultation.
"""

import asyncio
import json
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

from agents.base import BaseAgent, AgentDefinition, AgentState, ModelSize, register_agent_class
from agents.prompts import (
    EXECUTOR_PROMPT_HERMES,
    HERMES_SECURITY_EXECUTOR_PROMPT, HERMES_DECISION_PROMPT,
)
from config import (
    MODELS, TOKEN_LIMITS, TEMPERATURE, CONTEXT_WINDOW_SIZE,
    MAX_TOOL_ROUNDS, MAX_SECURITY_CONSULTATIONS,
)
from orchestration.messages import AgentMessage, MessageType


@register_agent_class
class HermesAgent(BaseAgent):
    AGENT_ID = "hermes"

    def __init__(self, agent_core):
        definition = AgentDefinition(
            agent_id="hermes",
            model_key="hermes",
            model_size=ModelSize.SMALL,   # Always loaded — central inference engine
            can_use_tools=True,
            capabilities=[
                "deep_reasoning", "execution", "tool_calling",
                "security_escalation", "complex_analysis",
            ],
            max_tokens=TOKEN_LIMITS.get("hermes", 4096),
            temperature=TEMPERATURE.get("hermes", 0.7),
        )
        super().__init__(definition, agent_core)

    async def run(self, message: AgentMessage, bus, workspace) -> Optional[AgentMessage]:
        """Dispatch by message payload action."""
        self.state = AgentState.RUNNING
        action = message.payload.get("action", "execution")

        try:
            if action == "execution":
                return await self._handle_execution(message, bus, workspace)
            elif action == "security_consultation":
                return await self._handle_security_task(message, bus, workspace)
            elif action == "direct":
                return await self._handle_direct(message, bus, workspace)
            else:
                return await self._handle_execution(message, bus, workspace)
        except Exception as e:
            self.state = AgentState.ERROR
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=f"Hermes error: {e}",
                payload={"error": True},
                parent_msg_id=message.id,
            )
        finally:
            if self.state == AgentState.RUNNING:
                self.state = AgentState.IDLE

    # ── Execution (tool-calling loop) ──

    async def _handle_execution(self, message: AgentMessage, bus, workspace) -> AgentMessage:
        """Execute a task with tool calling, post findings to workspace."""
        task_desc = message.content
        mission_id = message.mission_id
        task_id = message.payload.get("task_id", message.id)
        tool_plan = message.payload.get("tool_plan")

        system_prompt = EXECUTOR_PROMPT_HERMES

        # Build context from workspace
        prior_entries = self.read_workspace(workspace, mission_id)
        context = ""
        if prior_entries:
            context_parts = [f"[{e.agent_id}] {e.title}:\n{e.content[:1000]}" for e in prior_entries]
            context = "\n\nPrior findings:\n" + "\n---\n".join(context_parts)

        user_content = f"{task_desc}{context}"
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
        seen_calls = set()

        for _round in range(MAX_TOOL_ROUNDS):
            result = await self.call_llm(messages, tools=exec_schemas)
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

                    await self._core.broadcast({
                        "type": "agent_event",
                        "event": "tool_call",
                        "agent": self.agent_id,
                        "mission_id": mission_id,
                        "tool": fn_name,
                        "args": fn_args,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(tool_result),
                    })
            else:
                response_text = msg.get("content", "") or ""
                break
        else:
            response_text = "[Hit tool-call limit]"

        self.post_to_workspace(
            workspace, mission_id, "finding",
            f"Hermes execution: {task_desc[:80]}",
            response_text,
            tags=["hermes", "execution"],
        )

        return AgentMessage.create(
            msg_type=MessageType.RESULT,
            sender=self.agent_id,
            recipient=message.sender,
            mission_id=mission_id,
            content=response_text,
            payload={"task_id": task_id, "tool_calls": tool_calls_log},
            parent_msg_id=message.id,
        )

    # ── Security Task (Hermes + Security Agent inline advisory loop) ──

    async def _handle_security_task(self, message: AgentMessage, bus, workspace) -> AgentMessage:
        """Security task: Hermes does recon, consults security agent inline.

        Security agent is always resident — no GPU swap needed. We call it
        directly via _core._call_llm instead of routing through the bus.
        """
        task_desc = message.content
        mission_id = message.mission_id
        task_id = message.payload.get("task_id", message.id)
        tool_plan = message.payload.get("tool_plan")

        system_prompt = HERMES_SECURITY_EXECUTOR_PROMPT

        user_content = task_desc
        if tool_plan and isinstance(tool_plan, list):
            plan_steps = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(tool_plan))
            user_content += f"\n\n[Planner suggested tool calls]:\n{plan_steps}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        all_tool_calls = []
        consultation_log = []
        final_report = ""
        exec_schemas = self.get_tool_schemas()
        seen_calls = set()

        for consultation_round in range(MAX_SECURITY_CONSULTATIONS):
            logger.info("Security round %d/%d", consultation_round + 1, MAX_SECURITY_CONSULTATIONS)

            # Phase A: Hermes tool-calling loop
            hermes_text = ""
            for _round in range(MAX_TOOL_ROUNDS):
                try:
                    result = await self.call_llm(messages, tools=exec_schemas)
                except Exception as e:
                    hermes_text = f"Error during tool loop: {e}"
                    break

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
                        all_tool_calls.append({"tool": fn_name, "args": fn_args, "result": str(tool_result)[:500]})
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(tool_result)})
                else:
                    hermes_text = msg.get("content", "") or ""
                    break
            else:
                hermes_text = "[Hit tool-call limit during security task]"

            # Phase B: Parse decision
            if "DECISION:" not in hermes_text:
                messages.append({"role": "assistant", "content": hermes_text})
                messages.append({"role": "user", "content": HERMES_DECISION_PROMPT})
                try:
                    result = await self.call_llm(messages)
                    hermes_text = result["choices"][0]["message"].get("content", "")
                except Exception:
                    hermes_text = "DECISION: COMPLETE\nFINAL_REPORT:\nTask incomplete due to error."

            if "DECISION: COMPLETE" in hermes_text:
                if "FINAL_REPORT:" in hermes_text:
                    final_report = hermes_text.split("FINAL_REPORT:", 1)[1].strip()
                else:
                    final_report = hermes_text

                self.post_to_workspace(
                    workspace, mission_id, "finding",
                    f"Security assessment: {task_desc[:60]}",
                    final_report,
                    tags=["hermes", "security", "complete"],
                )
                break

            elif "DECISION: CONSULT" in hermes_text:
                question = hermes_text.split("QUESTION:", 1)[1].strip() if "QUESTION:" in hermes_text else hermes_text

                self.post_to_workspace(
                    workspace, mission_id, "tool_output",
                    f"Recon data (round {consultation_round + 1})",
                    question[:2000],
                    tags=["hermes", "recon"],
                )

                # Inline security agent consultation — no bus, no yield
                logger.info("Consulting security agent inline (round %d)", consultation_round + 1)
                try:
                    security_result = await self._core._call_llm(
                        MODELS["security"],
                        [{"role": "user", "content": question}],
                        max_tokens=TOKEN_LIMITS.get("security", 4096),
                        temperature=TEMPERATURE.get("security", 0.3),
                    )
                    security_advice = security_result["choices"][0]["message"].get("content", "")
                except Exception as e:
                    security_advice = f"Security consultation failed: {e}"

                consultation_log.append({
                    "round": consultation_round + 1,
                    "question": question[:500],
                    "advice": security_advice[:500],
                })

                self.post_to_workspace(
                    workspace, mission_id, "analysis",
                    f"Security consultation (round {consultation_round + 1})",
                    security_advice,
                    tags=["security", "consultation"],
                )

                messages.append({"role": "assistant", "content": hermes_text})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Security analysis:\n\n{security_advice}\n\n"
                        "Based on this analysis, continue your investigation. "
                        "Use tools to execute any recommended actions, then decide: CONSULT, CONTINUE, or COMPLETE."
                    ),
                })

            elif "DECISION: CONTINUE" in hermes_text:
                messages.append({"role": "assistant", "content": hermes_text})
                messages.append({
                    "role": "user",
                    "content": "Continue your investigation. Use tools as needed, then decide: CONSULT, CONTINUE, or COMPLETE.",
                })
            else:
                messages.append({"role": "assistant", "content": hermes_text})
                messages.append({
                    "role": "user",
                    "content": "Continue your investigation. Use tools as needed, then decide: CONSULT, CONTINUE, or COMPLETE.",
                })
        else:
            messages.append({
                "role": "user",
                "content": "Consultation limit reached. Provide your FINAL_REPORT now.",
            })
            try:
                result = await self.call_llm(messages)
                final_report = result["choices"][0]["message"].get("content", "")
                if "FINAL_REPORT:" in final_report:
                    final_report = final_report.split("FINAL_REPORT:", 1)[1].strip()
            except Exception as e:
                final_report = f"Error getting final report: {e}"

        return AgentMessage.create(
            msg_type=MessageType.RESULT,
            sender=self.agent_id,
            recipient=message.sender,
            mission_id=mission_id,
            content=final_report,
            payload={
                "task_id": task_id,
                "model": "hermes+security",
                "tool_calls": all_tool_calls,
                "consultations": consultation_log,
            },
            parent_msg_id=message.id,
        )

    # ── Direct ──

    async def _handle_direct(self, message: AgentMessage, bus, workspace) -> AgentMessage:
        """Direct execution — no delegation."""
        mission_id = message.mission_id
        history = message.payload.get("history")
        use_tools = message.payload.get("use_tools", True)

        msgs = [{"role": "system", "content": EXECUTOR_PROMPT_HERMES}]
        if history:
            for h in history[-CONTEXT_WINDOW_SIZE:]:
                msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": message.content})

        tool_calls_log = []
        response_text = ""
        tool_schemas = self.get_tool_schemas() if use_tools else None
        seen_calls = set()

        for _round in range(MAX_TOOL_ROUNDS):
            result = await self.call_llm(msgs, tools=tool_schemas)
            choice = result["choices"][0]
            msg = choice["message"]
            finish = choice.get("finish_reason", "")

            if finish == "tool_calls" and msg.get("tool_calls"):
                msgs.append(msg)
                for tc in msg["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError as e:
                        msgs.append({"role": "tool", "tool_call_id": tc["id"],
                            "content": f"JSON parse error: {e}. Raw: {tc['function']['arguments'][:200]}"})
                        continue

                    call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
                    if call_sig in seen_calls:
                        msgs.append({"role": "tool", "tool_call_id": tc["id"],
                            "content": f"Skipped: duplicate call to {fn_name} with same arguments."})
                        continue
                    seen_calls.add(call_sig)

                    tool_result = await self.execute_tool(fn_name, fn_args)
                    tool_calls_log.append({"tool": fn_name, "args": fn_args, "result": str(tool_result)[:500]})
                    msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": str(tool_result)})
            else:
                response_text = msg.get("content", "") or ""
                break
        else:
            response_text = "[Hit tool-call limit]"

        return AgentMessage.create(
            msg_type=MessageType.RESULT,
            sender=self.agent_id,
            recipient=message.sender,
            mission_id=mission_id,
            content=response_text,
            payload={"tool_calls": tool_calls_log, "action": "direct"},
            parent_msg_id=message.id,
        )
