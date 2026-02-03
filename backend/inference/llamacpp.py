"""
llama.cpp server inference backend adapter.

Wraps the llama.cpp HTTP server which has two API generations:
  - Legacy: /completion endpoint with its own JSON schema
  - Modern: /v1/chat/completions (OpenAI-compatible, available in newer builds)

This adapter auto-detects which API is available and uses the appropriate one.
It also handles /v1/models, /health, and /embedding endpoints.
"""

import json
import logging
import time
from typing import Optional

import httpx

from inference.base import InferenceBackend

logger = logging.getLogger(__name__)


def _messages_to_prompt(messages: list[dict], model_id: str = "") -> str:
    """Convert OpenAI-format messages to a single prompt string for the
    legacy /completion endpoint.

    Uses ChatML format which is the most widely supported template for
    llama.cpp models.
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Flatten multi-part content
            text_parts = [
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            ]
            content = "\n".join(text_parts)
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    # Prompt the model to generate an assistant response
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


def _legacy_response_to_openai(resp_data: dict, model_id: str) -> dict:
    """Convert llama.cpp /completion response to OpenAI-compatible format."""
    content = resp_data.get("content", "")
    # Strip any trailing ChatML close tag the model may have generated
    if "<|im_end|>" in content:
        content = content.split("<|im_end|>")[0]

    tokens_predicted = resp_data.get("tokens_predicted", 0)
    tokens_evaluated = resp_data.get("tokens_evaluated", 0)
    stop_reason = resp_data.get("stop_type", "stop")
    finish = "stop" if stop_reason in ("stop", "eos") else "length"

    return {
        "id": f"llamacpp-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content.strip(),
                },
                "finish_reason": finish,
            }
        ],
        "usage": {
            "prompt_tokens": tokens_evaluated,
            "completion_tokens": tokens_predicted,
            "total_tokens": tokens_evaluated + tokens_predicted,
        },
    }


class LlamaCppBackend(InferenceBackend):
    """Backend adapter for llama.cpp HTTP server.

    Auto-detects whether the server supports the modern /v1/chat/completions
    endpoint or only the legacy /completion endpoint.
    """

    def __init__(self, base_url: str = "http://localhost:8080",
                 default_timeout: float = 300):
        super().__init__(base_url, default_timeout)
        self._has_openai_compat: Optional[bool] = None
        self._server_model: Optional[str] = None  # The single model loaded

    async def _detect_api_version(self) -> bool:
        """Detect if the server supports /v1/chat/completions.

        Returns True if OpenAI-compatible endpoints are available.
        Caches the result for subsequent calls.
        """
        if self._has_openai_compat is not None:
            return self._has_openai_compat

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/v1/models")
                if resp.status_code < 400:
                    self._has_openai_compat = True
                    # Cache the loaded model name
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        self._server_model = models[0].get("id", "unknown")
                    return True
        except Exception:
            pass

        # Check if legacy /health endpoint responds
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health")
                if resp.status_code < 400:
                    self._has_openai_compat = False
                    return False
        except Exception:
            pass

        self._has_openai_compat = False
        return False

    # ── Model Discovery ──

    async def discover_models(self) -> dict[str, dict]:
        """Discover the model loaded in the llama.cpp server.

        llama.cpp typically serves a single model. We detect it via /v1/models
        (modern) or /props (legacy) or /health.
        """
        has_v1 = await self._detect_api_version()

        if has_v1:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{self.base_url}/v1/models")
                    resp.raise_for_status()
                    data = resp.json()
                    models = {}
                    for m in data.get("data", []):
                        mid = m.get("id", "unknown")
                        models[mid] = m
                        self._model_states[mid] = "loaded"
                        self._model_capabilities[mid] = ["chat"]
                        self._server_model = mid
                    return models
            except Exception:
                pass

        # Legacy: try /props for model metadata
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/props")
                if resp.status_code < 400:
                    data = resp.json()
                    mid = data.get("default_generation_settings", {}).get(
                        "model", "llamacpp-model"
                    )
                    self._server_model = mid
                    self._model_states[mid] = "loaded"
                    self._model_capabilities[mid] = ["chat"]
                    return {
                        mid: {
                            "id": mid,
                            "object": "model",
                            "owned_by": "llama.cpp",
                        }
                    }
        except Exception:
            pass

        # Fallback: health check only — model name unknown
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                health = resp.json()
                status = health.get("status", "unknown")
                mid = "llamacpp-model"
                self._server_model = mid
                if status == "ok":
                    self._model_states[mid] = "loaded"
                else:
                    self._model_states[mid] = status
                self._model_capabilities[mid] = ["chat"]
                return {
                    mid: {
                        "id": mid,
                        "object": "model",
                        "owned_by": "llama.cpp",
                        "status": status,
                    }
                }
        except Exception as e:
            raise ConnectionError(
                f"Cannot reach llama.cpp server at {self.base_url}: {e}"
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
        """Chat completion via /v1/chat/completions (modern) or /completion (legacy)."""
        has_v1 = await self._detect_api_version()

        if has_v1:
            return await self._call_llm_v1(
                model_id, messages, tools, max_tokens,
                temperature, tool_choice, timeout,
            )
        else:
            return await self._call_llm_legacy(
                model_id, messages, max_tokens, temperature, timeout,
            )

    async def _call_llm_v1(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tool_choice: str = None,
        timeout: float = None,
    ) -> dict:
        """Chat completion via OpenAI-compatible /v1/chat/completions."""
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
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

    async def _call_llm_legacy(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        timeout: float = None,
    ) -> dict:
        """Chat completion via legacy /completion endpoint."""
        prompt = _messages_to_prompt(messages, model_id)

        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stop": ["<|im_end|>", "<|im_start|>"],
            "stream": False,
        }

        async with httpx.AsyncClient(
            timeout=timeout or self.default_timeout
        ) as client:
            resp = await client.post(
                f"{self.base_url}/completion",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return _legacy_response_to_openai(data, model_id)

    async def call_llm_stream(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        on_chunk=None,
    ) -> str:
        """Streaming chat completion.

        Uses /v1/chat/completions SSE (modern) or /completion stream (legacy).
        """
        has_v1 = await self._detect_api_version()

        if has_v1:
            return await self._stream_v1(
                model_id, messages, max_tokens, temperature, on_chunk,
            )
        else:
            return await self._stream_legacy(
                model_id, messages, max_tokens, temperature, on_chunk,
            )

    async def _stream_v1(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        on_chunk=None,
    ) -> str:
        """Stream via /v1/chat/completions SSE (same as OpenAI)."""
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

    async def _stream_legacy(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        on_chunk=None,
    ) -> str:
        """Stream via legacy /completion endpoint.

        llama.cpp streams newline-delimited JSON with 'content' and 'stop' fields.
        """
        prompt = _messages_to_prompt(messages, model_id)

        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stop": ["<|im_end|>", "<|im_start|>"],
            "stream": True,
        }

        full_text = ""
        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/completion", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    # Legacy format: "data: {json}"
                    raw = line
                    if raw.startswith("data: "):
                        raw = raw[6:]
                    try:
                        chunk = json.loads(raw)
                        content = chunk.get("content", "")
                        if content:
                            # Strip ChatML tokens from streamed output
                            if "<|im_end|>" in content:
                                content = content.split("<|im_end|>")[0]
                            if content:
                                full_text += content
                                if on_chunk:
                                    await on_chunk(content)
                        if chunk.get("stop", False):
                            break
                    except json.JSONDecodeError:
                        continue
        return full_text

    # ── Model Lifecycle ──

    async def load_model(self, model_id: str, ttl: int = None, **kwargs) -> bool:
        """Verify the llama.cpp server has a model loaded.

        llama.cpp loads its model at startup via CLI args, so there is no
        dynamic load API. This checks /health or /v1/models to confirm
        the server is ready.
        """
        async with self._model_lock:
            if self._model_states.get(model_id) == "loaded":
                return True

            # Check health
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{self.base_url}/health")
                    if resp.status_code < 400:
                        health = resp.json()
                        if health.get("status") == "ok":
                            self._model_states[model_id] = "loaded"
                            logger.info(
                                "llama.cpp server ready at %s", self.base_url
                            )
                            return True
                        elif health.get("status") == "loading model":
                            logger.info(
                                "llama.cpp is still loading model at %s",
                                self.base_url,
                            )
                            return False
            except Exception as e:
                logger.error(
                    "Cannot reach llama.cpp server at %s: %s",
                    self.base_url, e,
                )
                return False

            logger.warning(
                "llama.cpp server at %s not ready for model %s",
                self.base_url, model_id,
            )
            return False

    async def unload_model(self, model_id: str) -> bool:
        """Unload is not supported by llama.cpp server.

        The model is loaded at startup and cannot be changed at runtime.
        This is a no-op that updates internal state tracking.
        """
        logger.info(
            "llama.cpp does not support dynamic unload; tracking %s as unloaded",
            model_id,
        )
        self._model_states[model_id] = "unloaded"
        return True

    # ── Embedding ──

    async def embed(
        self,
        model_id: str,
        texts: list[str],
        timeout: float = None,
    ) -> list[list[float]]:
        """Generate embeddings via /v1/embeddings (modern) or /embedding (legacy).

        The modern endpoint accepts the OpenAI format. The legacy endpoint
        accepts a single 'content' string per request.
        """
        has_v1 = await self._detect_api_version()

        if has_v1:
            # Modern: OpenAI-compatible /v1/embeddings
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
            embeddings_data = sorted(
                data.get("data", []), key=lambda x: x.get("index", 0)
            )
            return [item["embedding"] for item in embeddings_data]
        else:
            # Legacy: single-text /embedding endpoint
            embeddings = []
            async with httpx.AsyncClient(
                timeout=timeout or self.default_timeout
            ) as client:
                for text in texts:
                    resp = await client.post(
                        f"{self.base_url}/embedding",
                        json={"content": text},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    embedding = data.get("embedding", [])
                    embeddings.append(embedding)
            return embeddings
