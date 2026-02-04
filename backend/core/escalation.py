"""
Escalation flow and presentation layer.
Extracted from agent_core.py for modularity.
"""

import logging
import uuid

from config import (
    MODELS, TOKEN_LIMITS, TEMPERATURE,
    CONTEXT_WINDOW_SIZE, ESCALATION_CONFIG,
)
from agents.prompts import get_presentation_prompt

logger = logging.getLogger(__name__)


class _EscalationMixin:
    """Mixin providing escalation and presentation layer for AgentCore."""

    async def _request_escalation(self, mission_id: str, reason: str,
                                   findings_so_far: str = "") -> dict:
        """Request user approval for escalation. Returns escalation info to frontend.

        The frontend presents the options and the user's choice comes back
        via resolve_escalation().
        """
        escalation_id = str(uuid.uuid4())[:12]
        targets = []
        for key, cfg in ESCALATION_CONFIG["targets"].items():
            targets.append({
                "key": key,
                "label": cfg["label"],
                "description": cfg["description"],
                "memory_cost": cfg.get("memory_cost", 0),
                "available": cfg.get("always_available", True),
            })

        escalation = {
            "id": escalation_id,
            "mission_id": mission_id,
            "reason": reason,
            "findings_so_far": findings_so_far[:2000],
            "targets": targets,
            "status": "pending",
        }
        self._pending_escalations[escalation_id] = escalation

        await self.broadcast({
            "type": "escalation_request",
            "escalation": escalation,
        })

        return escalation

    async def resolve_escalation(self, escalation_id: str, target: str) -> dict:
        """User has chosen an escalation target. Execute it."""
        escalation = self._pending_escalations.get(escalation_id)
        if not escalation:
            return {"error": "Escalation not found"}

        escalation["status"] = "resolved"
        escalation["chosen_target"] = target

        await self.broadcast({
            "type": "escalation_resolved",
            "escalation_id": escalation_id,
            "target": target,
        })

        return escalation

    async def _present(self, user_message: str, raw_content: str,
                       history: list = None) -> str:
        """Optional presentation layer — reformat agent output through personality prompt.

        Uses the presentation prompt from profile. If no presentation model is
        configured or it fails, returns the raw content unchanged.
        """
        primary_model = MODELS.get("primary")
        if not primary_model or not raw_content:
            return raw_content

        presentation_prompt = get_presentation_prompt()
        if not presentation_prompt:
            return raw_content

        prompt = f"""The user asked: "{user_message}"

Here are the findings from the analysis:

{raw_content}

---

Present these findings to the user. Be direct, thorough, and actionable."""

        system = presentation_prompt
        if self._soul_context:
            system = f"{system}\n\n## Persistent Context\n{self._soul_context}"

        msgs = [{"role": "system", "content": system}]
        if history:
            for h in history[-CONTEXT_WINDOW_SIZE:]:
                msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": prompt})

        try:
            async def on_chunk(content_chunk: str):
                await self.broadcast({"type": "stream_chunk", "content": content_chunk})

            return await self.inference.call_llm_stream(
                primary_model, msgs,
                max_tokens=TOKEN_LIMITS.get("primary", 4096),
                temperature=TEMPERATURE.get("primary", 0.7),
                on_chunk=on_chunk,
            )
        except Exception as e:
            logger.warning("Presentation layer failed: %s — returning raw content", e)
            return raw_content
