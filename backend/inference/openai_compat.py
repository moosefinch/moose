"""
OpenAI-compatible inference backend adapter.

Covers any server that implements the OpenAI API contract:
  - LM Studio (with dynamic model load/unload extensions)
  - vLLM
  - text-generation-webui (with --api flag)
  - Any other /v1/chat/completions + /v1/models server

This is the refactored version of the original backend/inference.py.
"""

import json
import logging
from typing import Optional

import httpx

from inference.base import InferenceBackend

logger = logging.getLogger(__name__)


class OpenAICompatBackend(InferenceBackend):
    """Backend adapter for OpenAI-compatible inference servers."""

    def __init__(self, base_url: str = "http://localhost:1234",
                 default_timeout: float = 300):
        super().__init__(base_url, default_timeout)

    # ── Model Discovery ──

    async def discover_models(self) -> dict[str, dict]:
        """Query the backend for available models.

        Tries LM Studio /api/v1/models first (has loaded_instances for
        accurate load-state detection), then /v1/models (OpenAI compat,
        lists all downloaded — cannot distinguish loaded vs downloaded).
        """
        # Prefer LM Studio native API — has loaded_instances field
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/v1/models")
                resp.raise_for_status()
                models = {}
                for m in resp.json().get("models", []):
                    mid = m.get("key", m.get("id", ""))
                    models[mid] = m
                    loaded = len(m.get("loaded_instances", [])) > 0
                    self._model_states[mid] = "loaded" if loaded else "downloaded"
                    caps = m.get("capabilities", {})
                    self._model_capabilities[mid] = (
                        list(caps.keys()) if isinstance(caps, dict) else caps
                    ) or ["chat"]
                return models
        except Exception:
            pass

        # Fallback: OpenAI /v1/models — marks all as "downloaded" since
        # this endpoint cannot distinguish loaded from merely available.
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/v1/models")
                resp.raise_for_status()
                data = resp.json()
                models = {}
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    models[mid] = m
                    self._model_states[mid] = "downloaded"
                    self._model_capabilities[mid] = m.get("capabilities", ["chat"])
                return models
        except Exception as e:
            raise ConnectionError(
                f"Cannot reach inference backend at {self.base_url}: {e}"
            )

    # ── Chat Completion ──

    async def call_llm(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tool_choice: str = None,
        timeout: float = None,
        draft_model: str = None,
    ) -> dict:
        """Non-streaming chat completion via /v1/chat/completions."""
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if draft_model:
            payload["draft_model"] = draft_model
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        async with httpx.AsyncClient(
            timeout=timeout or self.default_timeout
        ) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def call_llm_stream(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        on_chunk=None,
    ) -> str:
        """Streaming chat completion via /v1/chat/completions with SSE.

        Parses the server-sent events stream, accumulates content, and
        optionally invokes on_chunk for each content delta.
        """
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        full_text = ""
        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/v1/chat/completions", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                            if on_chunk:
                                await on_chunk(content)
                    except json.JSONDecodeError:
                        continue
        return full_text

    # ── Model Lifecycle ──

    async def load_model(self, model_id: str, ttl: int = None, **kwargs) -> bool:
        """Load a model into the backend.

        1. Checks internal cache for already-loaded state.
        2. Queries LM Studio /api/v1/models for actual loaded_instances.
        3. Triggers load via /api/v1/models/load if not yet loaded.

        Returns True if the model is loaded and ready.
        """
        async with self._model_lock:
            # Already tracked as loaded
            if self._model_states.get(model_id) == "loaded":
                return True

            # Check actual load state via LM Studio native API
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{self.base_url}/api/v1/models")
                    resp.raise_for_status()
                    for m in resp.json().get("models", []):
                        mid = m.get("key", m.get("id", ""))
                        if mid == model_id and len(m.get("loaded_instances", [])) > 0:
                            self._model_states[model_id] = "loaded"
                            return True
            except Exception:
                pass

            # Not loaded — trigger load via LM Studio dynamic load API
            try:
                payload = {"model": model_id}
                if ttl is not None:
                    payload["ttl"] = ttl
                logger.info("Loading model %s into LM Studio...", model_id)
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{self.base_url}/api/v1/models/load", json=payload
                    )
                    if resp.status_code < 400:
                        self._model_states[model_id] = "loaded"
                        logger.info(
                            "Loaded %s%s",
                            model_id,
                            f" (TTL={ttl}s)" if ttl else "",
                        )
                        return True
            except Exception:
                pass

            logger.warning("Model %s not available on %s", model_id, self.base_url)
            return False

    async def unload_model(self, model_id: str) -> bool:
        """Unload a model. LM Studio manages its own memory; this tracks state.

        For LM Studio with auto-evict disabled, unload is advisory.
        For vLLM/TGI, there is typically no unload endpoint.
        """
        # Try LM Studio unload endpoint
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/models/unload",
                    json={"model": model_id},
                )
                if resp.status_code < 400:
                    logger.info("Unloaded %s from %s", model_id, self.base_url)
        except Exception:
            pass  # Not all servers support this

        self._model_states[model_id] = "unloaded"
        return True

    # ── Embedding ──

    async def embed(
        self,
        model_id: str,
        texts: list[str],
        timeout: float = None,
    ) -> list[list[float]]:
        """Generate embeddings via /v1/embeddings.

        Handles both single-input and batch-input responses.
        """
        payload = {
            "model": model_id,
            "input": texts,
        }
        async with httpx.AsyncClient(
            timeout=timeout or self.default_timeout
        ) as client:
            resp = await client.post(
                f"{self.base_url}/v1/embeddings",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract embedding vectors, sorted by index
        embeddings_data = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in embeddings_data]
