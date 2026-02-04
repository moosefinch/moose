"""
Main chat pipeline — routes queries through classifier and agent fleet.
Extracted from agent_core.py for modularity.
"""

import asyncio
import logging
import time
import uuid

from config import MODELS, MODEL_LABELS
from orchestration.messages import AgentMessage, MessageType
from profile import get_profile

logger = logging.getLogger(__name__)


class _ChatPipelineMixin:
    """Mixin providing the main chat() entry point for AgentCore."""

    async def chat(self, message: str, history: list = None,
                   use_tools: bool = True, stream: bool = False) -> dict:
        """Main entry point — routes through classifier then agent fleet.

        Flow:
          1. Passive security check
          2. Classify (TRIVIAL/SIMPLE/COMPLEX)
          3. TRIVIAL → presentation layer responds directly (0 coordination)
          4. SIMPLE → reasoner plans single task, agent executes
          5. COMPLEX → reasoner plans multi-task, agents execute, results synthesized
          6. Escalation → reasoner flags needs_escalation, user approves target
        """
        if not self.scheduler or not self.registry:
            raise RuntimeError("Agent system not initialized. Cannot process requests.")

        t0 = time.time()

        # Passive security check
        security_flag = self._passive_security_check(message)
        if security_flag:
            logger.warning("Security: %s", security_flag)

        # Fast-path classification
        tier = await self._classify_query(message)
        logger.info("Classification: %s", tier)
        await self.broadcast({"type": "execution_status", "stage": "classified", "tier": tier})

        # TRIVIAL tier — presentation layer handles directly
        if tier == "TRIVIAL":
            return await self._handle_trivial(message, history)

        # SIMPLE/COMPLEX — reasoner plans, agents execute
        reasoner = self.registry.get("reasoner")
        if not reasoner:
            return {
                "content": "System offline: reasoner agent not available.",
                "model": "none", "model_key": "none", "error": True,
            }

        # Phase 1: Plan via reasoner agent
        plan = await reasoner.plan(message, history)
        logger.info("Plan: %s (complexity=%s, tier=%s, %d tasks)",
                    plan['plan_summary'], plan['complexity'], plan['response_tier'], len(plan['tasks']))

        await self.broadcast({
            "type": "execution_status", "stage": "planned",
            "plan_summary": plan["plan_summary"],
            "task_count": len(plan["tasks"]),
        })

        # Check escalation
        if plan.get("needs_escalation"):
            logger.info("Escalation requested — notifying user")
            escalation = await self._request_escalation(
                mission_id=str(uuid.uuid4())[:12],
                reason=plan.get("plan_summary", "Task exceeds fleet capability"),
                findings_so_far="",
            )
            return {
                "content": f"This task may exceed the fleet's capability. {plan.get('plan_summary', '')}",
                "model": "reasoner",
                "model_key": "reasoner",
                "model_label": MODEL_LABELS.get("reasoner", "Reasoner"),
                "elapsed_seconds": round(time.time() - t0, 2),
                "tool_calls": [],
                "plan": {"summary": plan["plan_summary"], "complexity": plan["complexity"]},
                "tier": tier,
                "escalation": escalation,
                "error": False,
            }

        # Immediate tier: single task, no synthesis needed
        if (plan["response_tier"] == "immediate"
                and len(plan["tasks"]) == 1
                and not plan["synthesize"]):
            task = plan["tasks"][0]
            model_key = task.get("model", "coder")
            agent_id = model_key
            agent = self.registry.get(agent_id)

            if not agent:
                return {
                    "content": f"Agent '{agent_id}' not available.",
                    "model": "none", "model_key": "none", "error": True,
                }

            # Ensure the agent's model is loaded before dispatch
            if self.model_manager:
                loaded = await self.model_manager.ensure_loaded(agent.model_key)
                if not loaded:
                    return {
                        "content": f"Model '{agent.model_key}' could not be loaded.",
                        "model": "none", "model_key": "none", "error": True,
                    }

            mission_id = str(uuid.uuid4())[:12]
            task_msg = AgentMessage.create(
                msg_type=MessageType.TASK,
                sender="system",
                recipient=agent_id,
                mission_id=mission_id,
                content=task.get("task", message),
                payload={
                    "action": "execution" if agent.can_use_tools else "direct",
                    "history": history,
                    "use_tools": use_tools and agent.can_use_tools,
                    "task_id": task.get("id", "t1"),
                    "tools_needed": task.get("tools_needed", False),
                    "tool_plan": task.get("tool_plan"),
                },
            )

            try:
                response = await agent.run(task_msg, self.bus, self.workspace)
            finally:
                # Release model reference after agent completes
                if self.model_manager:
                    await self.model_manager.release(agent.model_key)

            raw_content = response.content if response else "No response"
            tool_calls = response.payload.get("tool_calls", []) if response else []

            # Skip presentation layer for immediate tasks — agent output is the response.
            # Presentation adds another full 70b round-trip which doubles latency.
            content = raw_content

            elapsed = time.time() - t0

            if self.memory._api_base and content and not content.startswith("Error"):
                try:
                    await self.memory.store(f"User: {message}\nAssistant: {content[:500]}", tags=f"chat,{model_key}")
                except Exception:
                    pass

            # Process through Memory V2 (async, don't block response)
            if content and not content.startswith("Error"):
                asyncio.create_task(self._process_memory_v2(message, content))

            await self.broadcast({
                "type": "mission_update", "mission_id": mission_id,
                "status": "completed", "active_agent": agent_id,
            })

            return {
                "content": content,
                "model": model_key,
                "model_key": model_key,
                "model_label": MODEL_LABELS.get(model_key, model_key),
                "elapsed_seconds": round(elapsed, 2),
                "tool_calls": tool_calls,
                "plan": None,
                "tier": tier,
                "error": bool(content.startswith("Error") if content else False),
            }

        # Enhanced/Deep tier: Submit mission to scheduler
        # Ensure specialist models are available before dispatching
        for task in plan["tasks"]:
            model_key = task.get("model", "coder")
            if model_key not in ("hermes", "claude"):
                await self._ensure_model_available(model_key)

        mission_id = str(uuid.uuid4())[:12]
        logger.info("Submitting mission %s (%d tasks)", mission_id, len(plan['tasks']))

        await self.broadcast({
            "type": "mission_update", "mission_id": mission_id,
            "status": "running", "plan": plan["plan_summary"],
        })

        self.scheduler.submit_mission(
            mission_id, plan["tasks"],
            synthesize=plan["synthesize"],
            user_message=message,
            history=history,
        )
        self.scheduler.start_loop()

        # Await completion (300s timeout for chat queries)
        mission = await self.scheduler.await_mission(mission_id, timeout=300)

        # Build response
        profile = get_profile()
        system_name = profile.system.name or "Assistant"
        if mission.get("error"):
            elapsed = time.time() - t0
            return {
                "content": f"Mission error: {mission.get('error')}",
                "model": "orchestrated", "model_key": "orchestrated",
                "model_label": system_name, "elapsed_seconds": round(elapsed, 2),
                "tool_calls": [], "plan": None, "error": True,
            }

        # Get synthesis result or first task result
        if mission.get("synthesis_result"):
            raw_text = mission["synthesis_result"]
            model_label = f"{system_name} (multi-agent)"
            response_text = await self._present(message, raw_text, history)
        elif mission.get("results"):
            results = list(mission["results"].values())
            if len(results) == 1:
                raw_text = results[0].get("result", "")
                model_key = results[0].get("model", "coder")
                model_label = MODEL_LABELS.get(model_key, model_key)
                response_text = await self._present(message, raw_text, history)
            else:
                raw_text = "\n\n---\n\n".join(r.get("result", "") for r in results)
                model_chain = [r.get("model", "?") for r in results]
                model_label = " -> ".join(dict.fromkeys(model_chain))
                response_text = await self._present(message, raw_text, history)
        else:
            response_text = "No tasks executed."
            model_label = system_name

        # Collect all tool calls
        all_tool_calls = []
        for r in mission.get("results", {}).values():
            all_tool_calls.extend(r.get("tool_calls", []))

        elapsed = time.time() - t0

        # Store in memory (V1)
        if self.memory._api_base and response_text and not response_text.startswith("Error"):
            try:
                models_used = ",".join(set(r.get("model", "") for r in mission.get("results", {}).values()))
                await self.memory.store(
                    f"User: {message}\nAssistant: {response_text[:500]}",
                    tags=f"chat,{models_used}",
                )
            except Exception:
                pass

        # Process through Memory V2 (async, don't block response)
        if response_text and not response_text.startswith("Error"):
            asyncio.create_task(self._process_memory_v2(message, response_text))

        return {
            "content": response_text,
            "model": "orchestrated",
            "model_key": "orchestrated",
            "model_label": model_label,
            "elapsed_seconds": round(elapsed, 2),
            "tool_calls": all_tool_calls,
            "plan": {
                "summary": plan["plan_summary"],
                "complexity": plan["complexity"],
                "response_tier": plan["response_tier"],
                "tasks": [{"id": t.get("id"), "model": t.get("model"), "task": t.get("task", "")[:200], "depends_on": t.get("depends_on", [])} for t in plan["tasks"]],
                "synthesized": plan["synthesize"],
            },
            "tier": tier,
            "error": False,
        }
