"""
SolutionResearcher — given a capability gap, research and return a solution.

Uses the orchestrator model for LLM reasoning when needed, and queries
inference backends to inventory available models.
"""

import json
import logging

from config import MODELS, TOKEN_LIMITS, TEMPERATURE

logger = logging.getLogger(__name__)

RESEARCH_PROMPT = """\
You are analyzing a capability gap in an AI system.

Gap: {gap_description}
Evidence: {gap_evidence}
Available models: {model_inventory}
System resources: {resource_info}

Recommend a solution. Respond with JSON only (no markdown fences):
{{"solution_type": "download_model|load_model|swap_model|evict_model", "model_id": "...", "model_key": "...", "reasoning": "...", "config_changes": {{}}}}
"""


class SolutionResearcher:
    """Research solutions for capability gaps."""

    async def research_solution(self, gap: dict, core) -> dict:
        """Given a capability gap, research and return a solution dict."""
        gap_type = gap.get("gap_type", "unknown")

        if gap_type == "missing_model":
            return await self._research_missing_model(gap, core)
        elif gap_type == "model_load_failed":
            return await self._research_load_failure(gap, core)
        elif gap_type == "repeated_failures":
            return await self._research_failures(gap, core)
        else:
            return await self._research_generic(gap, core)

    async def _get_model_inventory(self, core) -> dict:
        """Query backends for available models."""
        try:
            return await core.inference.discover_models()
        except Exception as e:
            logger.warning("[Researcher] discover_models error: %s", e)
            return {}

    async def _call_orchestrator(self, prompt: str, core) -> dict:
        """Call the orchestrator model and parse JSON response."""
        model_id = MODELS.get("orchestrator")
        if not model_id:
            logger.warning("[Researcher] No orchestrator model configured")
            return {}

        try:
            result = await core._call_llm(
                model_id,
                [{"role": "user", "content": prompt}],
                max_tokens=TOKEN_LIMITS.get("orchestrator", 1024),
                temperature=TEMPERATURE.get("orchestrator", 0.3),
            )
            content = result["choices"][0]["message"].get("content", "")
            # Strip markdown fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()
            return json.loads(content)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("[Researcher] Orchestrator response parse error: %s", e)
            return {}
        except Exception as e:
            logger.warning("[Researcher] Orchestrator call error: %s", e)
            return {}

    async def _research_missing_model(self, gap: dict, core) -> dict:
        """Research a solution for a model that's configured but not downloaded."""
        model_key = gap.get("model_key", "")
        model_id = gap.get("model_id", MODELS.get(model_key, ""))

        if not model_id:
            return {"solution_type": "none", "reasoning": f"No model ID for key '{model_key}'"}

        # Check if the model is available from any backend
        inventory = await self._get_model_inventory(core)

        if model_id in inventory:
            # Model exists but isn't loaded — just load it
            return {
                "solution_type": "load_model",
                "model_key": model_key,
                "model_id": model_id,
                "reasoning": f"Model {model_id} is available but not loaded. Loading it.",
                "config_changes": {},
            }

        # Model not available — needs download
        return {
            "solution_type": "download_model",
            "model_key": model_key,
            "model_id": model_id,
            "reasoning": f"Model {model_id} is not available on any backend. Downloading required.",
            "config_changes": {},
        }

    async def _research_load_failure(self, gap: dict, core) -> dict:
        """Research a solution when a model fails to load (VRAM, missing file, etc.)."""
        model_key = gap.get("model_key", "")
        model_id = gap.get("model_id", MODELS.get(model_key, ""))
        inventory = await self._get_model_inventory(core)

        # Get resource info
        resource_info = "unknown"
        if core.model_manager:
            try:
                mem_gb = await core.model_manager._get_available_memory_gb()
                if mem_gb is not None:
                    resource_info = f"{mem_gb:.1f}GB available"
            except Exception:
                pass

        # Use orchestrator to diagnose
        prompt = RESEARCH_PROMPT.format(
            gap_description=gap.get("description", f"Model '{model_key}' ({model_id}) failed to load"),
            gap_evidence=json.dumps(gap.get("evidence", {})),
            model_inventory=json.dumps(list(inventory.keys())[:30]),
            resource_info=resource_info,
        )

        solution = await self._call_orchestrator(prompt, core)
        if solution:
            return solution

        # Fallback: suggest evicting on-demand models and retrying
        return {
            "solution_type": "evict_model",
            "model_key": model_key,
            "model_id": model_id,
            "reasoning": f"Model {model_key} failed to load. Suggest evicting on-demand models to free resources, then retrying.",
            "config_changes": {},
        }

    async def _research_failures(self, gap: dict, core) -> dict:
        """Research repeated task failures — use orchestrator for analysis."""
        inventory = await self._get_model_inventory(core)

        resource_info = "unknown"
        if core.model_manager:
            try:
                mem_gb = await core.model_manager._get_available_memory_gb()
                if mem_gb is not None:
                    resource_info = f"{mem_gb:.1f}GB available"
            except Exception:
                pass

        prompt = RESEARCH_PROMPT.format(
            gap_description=gap.get("description", "Repeated task failures detected"),
            gap_evidence=json.dumps(gap.get("evidence", {})),
            model_inventory=json.dumps(list(inventory.keys())[:30]),
            resource_info=resource_info,
        )

        solution = await self._call_orchestrator(prompt, core)
        return solution or {
            "solution_type": "none",
            "reasoning": "Could not determine a solution for repeated failures.",
        }

    async def _research_generic(self, gap: dict, core) -> dict:
        """Generic gap research — delegate to orchestrator."""
        inventory = await self._get_model_inventory(core)

        prompt = RESEARCH_PROMPT.format(
            gap_description=gap.get("description", "Unknown capability gap"),
            gap_evidence=json.dumps(gap.get("evidence", {})),
            model_inventory=json.dumps(list(inventory.keys())[:30]),
            resource_info="unknown",
        )

        solution = await self._call_orchestrator(prompt, core)
        return solution or {
            "solution_type": "none",
            "reasoning": "Could not determine a solution.",
        }
