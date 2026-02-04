"""
Query classification and trivial response handling.
Extracted from agent_core.py for modularity.
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Optional

from config import (
    MODELS, MODEL_LABELS,
    CLASSIFIER_MAX_TOKENS, CLASSIFIER_TEMPERATURE,
    TRIVIAL_RESPONSE_MAX_TOKENS, TRIVIAL_RESPONSE_TEMPERATURE,
)
from agents.prompts import (
    SUSPICIOUS_PATTERNS, CLASSIFIER_PROMPT,
    build_trivial_prompt,
)

logger = logging.getLogger(__name__)


class _ClassificationMixin:
    """Mixin providing query classification, trivial handling, and passive security."""

    async def _classify_query(self, message: str) -> str:
        """Use classifier agent (Qwen3-0.6B) to classify: TRIVIAL, SIMPLE, or COMPLEX."""
        classifier = self.registry.get("classifier") if self.registry else None
        if not classifier:
            # Fallback if classifier agent not available
            if not self.available_models.get("classifier"):
                return "COMPLEX"
            try:
                prompt = CLASSIFIER_PROMPT.replace("{query}", message[:500])
                result = await self._call_llm(
                    MODELS["classifier"],
                    [{"role": "user", "content": prompt}],
                    max_tokens=CLASSIFIER_MAX_TOKENS,
                    temperature=CLASSIFIER_TEMPERATURE,
                )
                response = result["choices"][0]["message"].get("content", "").strip().upper()
                for tier in ("TRIVIAL", "SIMPLE", "COMPLEX"):
                    if tier in response:
                        return tier
                return "COMPLEX"
            except Exception as e:
                logger.error("Classifier error: %s", e)
                return "COMPLEX"

        try:
            tier = await classifier.classify(message)
            return tier
        except Exception as e:
            logger.error("Classifier error: %s", e)
            return "COMPLEX"

    async def _handle_trivial(self, message: str, history: list = None) -> dict:
        """Handle TRIVIAL queries with always-loaded conversational model.

        Uses the conversational model (8B, always loaded) for personality-rich
        instant replies. Falls back to primary if conversational unavailable.
        No model spin-up required — conversational is always resident.
        """
        t0 = time.time()
        current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

        # Use conversational model (always loaded, 8B) — fast + personality.
        # Falls back to primary if conversational isn't configured.
        trivial_model = MODELS.get("conversational") or MODELS.get("primary")
        model_key = "conversational" if MODELS.get("conversational") else "primary"
        if not trivial_model:
            return {
                "content": "No model configured.",
                "model": "none", "model_key": "none", "error": True,
            }

        system_prompt = build_trivial_prompt(current_time)

        # Inject Memory V2 context if available
        if self.memory_v2:
            try:
                memory_context = await self.memory_v2.build_context(
                    message, session_id=self._current_session_id
                )
                if memory_context.get("context"):
                    system_prompt = f"{system_prompt}\n\n## User Context\n{memory_context['context']}"
            except Exception:
                pass

        if self._soul_context:
            system_prompt = f"{system_prompt}\n\n## Persistent Context\n{self._soul_context}"

        msgs = [{"role": "system", "content": system_prompt}]
        if history:
            msgs.extend(history[-4:])
        msgs.append({"role": "user", "content": message})

        try:
            async def on_chunk(content_chunk: str):
                await self.broadcast({"type": "stream_chunk", "content": content_chunk})

            content = await self.inference.call_llm_stream(
                trivial_model, msgs,
                max_tokens=TRIVIAL_RESPONSE_MAX_TOKENS,
                temperature=TRIVIAL_RESPONSE_TEMPERATURE,
                on_chunk=on_chunk,
            )
        except Exception as e:
            content = f"Error: {e}"

        elapsed = time.time() - t0

        # Process through Memory V2 (async, don't block response)
        if content and not content.startswith("Error"):
            asyncio.create_task(self._process_memory_v2(message, content))

        return {
            "content": content,
            "model": model_key,
            "model_key": model_key,
            "model_label": MODEL_LABELS.get(model_key, model_key.title()),
            "elapsed_seconds": round(elapsed, 2),
            "tool_calls": [],
            "plan": None,
            "tier": "TRIVIAL",
            "error": bool(content.startswith("Error")),
        }

    def _passive_security_check(self, text: str) -> Optional[str]:
        """Lightweight pattern-based screening for prompt injection and suspicious input.
        Returns a warning string if suspicious, None if clean."""
        text_lower = text.lower()
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, text_lower):
                return f"Passive security flag: matched pattern '{pattern}' in input"
        return None
