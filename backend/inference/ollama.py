"""
Ollama inference backend adapter.

Wraps Ollama's native API endpoints:
  - /api/chat for chat completion
  - /api/tags for model listing
  - /api/embeddings for embeddings
  - /api/pull for model download
  - /api/show for model info

Normalizes requests and responses to/from OpenAI format so the rest of the
application can use a uniform interface.
"""

import json
import logging
import time
from typing import Optional

import httpx

from inference.base import InferenceBackend

logger = logging.getLogger(__name__)


def _openai_messages_to_ollama(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-format messages to Ollama format.

    Ollama uses the same role/content structure but does not support
    the 'name' field or complex content arrays. This normalizes those.
    """
    converted = []
    for msg in messages:
        entry = {"role": msg["role"]}
        content = msg.get("content", "")
        # Ollama expects content as a plain string
        if isinstance(content, list):
            # Flatten multi-part content (text only; images handled separately)
            text_parts = []
            images = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        # Ollama accepts base64 images in the images field
                        if url.startswith("data:"):
                            # Extract base64 after the comma
                            b64 = url.split(",", 1)[-1] if "," in url else url
                            images.append(b64)
                else:
                    text_parts.append(str(part))
            entry["content"] = "\n".join(text_parts)
            if images:
                entry["images"] = images
        else:
            entry["content"] = content or ""
        converted.append(entry)
    return converted


def _ollama_response_to_openai(ollama_resp: dict, model_id: str) -> dict:
    """Convert Ollama's /api/chat response to OpenAI-compatible format."""
    message = ollama_resp.get("message", {})
    content = message.get("content", "")

    # Build usage info from Ollama's metrics
    prompt_tokens = ollama_resp.get("prompt_eval_count", 0)
    completion_tokens = ollama_resp.get("eval_count", 0)

    return {
        "id": f"ollama-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": message.get("role", "assistant"),
                    "content": content,
                },
                "finish_reason": "stop" if ollama_resp.get("done") else "length",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


class OllamaBackend(InferenceBackend):
    """Backend adapter for Ollama inference server."""

    def __init__(self, base_url: str = "http://localhost:11434",
                 default_timeout: float = 300):
        super().__init__(base_url, default_timeout)

    # ── Model Discovery ──

    async def discover_models(self) -> dict[str, dict]:
        """List available models via /api/tags.

        Ollama returns models with name, size, modified date, and digest.
        We normalize to an OpenAI-like model dict.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()

        models = {}
        for m in data.get("models", []):
            name = m.get("name", "")
            # Strip :latest tag for cleaner model IDs
            mid = name.removesuffix(":latest")
            models[mid] = {
                "id": mid,
                "object": "model",
                "owned_by": "ollama",
                "name": name,
                "size": m.get("size", 0),
                "digest": m.get("digest", ""),
                "modified_at": m.get("modified_at", ""),
                "details": m.get("details", {}),
            }
            self._model_states[mid] = "downloaded"
            # Determine capabilities from model details
            families = m.get("details", {}).get("families", [])
            caps = ["chat"]
            if "embed" in name.lower() or "embedding" in name.lower():
                caps = ["embedding"]
            self._model_capabilities[mid] = caps
        return models

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
        """Non-streaming chat completion via /api/chat.

        Converts OpenAI-format messages to Ollama format, makes the request,
        and converts the response back to OpenAI format.
        """
        ollama_messages = _openai_messages_to_ollama(messages)

        payload = {
            "model": model_id,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        # Ollama supports tools natively since v0.3+
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(
            timeout=timeout or self.default_timeout
        ) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            ollama_resp = resp.json()

        return _ollama_response_to_openai(ollama_resp, model_id)

    async def call_llm_stream(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        on_chunk=None,
    ) -> str:
        """Streaming chat completion via /api/chat with stream=true.

        Ollama streams newline-delimited JSON objects. Each object has a
        'message' field with partial content and a 'done' field.
        """
        ollama_messages = _openai_messages_to_ollama(messages)

        payload = {
            "model": model_id,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        full_text = ""
        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            full_text += content
                            if on_chunk:
                                await on_chunk(content)
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        return full_text

    # ── Model Lifecycle ──

    async def load_model(self, model_id: str, ttl: int = None, **kwargs) -> bool:
        """Load a model into Ollama's memory.

        Ollama loads models on first use, but we can pre-warm by sending
        a minimal request. If keep_alive is supported, we pass ttl as the
        keep_alive duration.
        """
        async with self._model_lock:
            if self._model_states.get(model_id) == "loaded":
                return True

            # Check if model exists locally
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"{self.base_url}/api/show",
                        json={"name": model_id},
                    )
                    if resp.status_code >= 400:
                        logger.warning(
                            "Model %s not found in Ollama", model_id
                        )
                        return False
            except Exception as e:
                logger.error("Cannot reach Ollama at %s: %s", self.base_url, e)
                return False

            # Pre-warm the model with a minimal chat request
            try:
                payload = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "options": {"num_predict": 1},
                }
                if ttl is not None:
                    payload["keep_alive"] = f"{ttl}s"

                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{self.base_url}/api/chat",
                        json=payload,
                    )
                    if resp.status_code < 400:
                        self._model_states[model_id] = "loaded"
                        logger.info("Pre-warmed %s in Ollama", model_id)
                        return True
            except Exception as e:
                logger.error("Failed to pre-warm %s: %s", model_id, e)

            return False

    async def unload_model(self, model_id: str) -> bool:
        """Unload a model from Ollama's memory.

        Ollama supports keep_alive=0 to immediately unload a model.
        """
        try:
            payload = {
                "model": model_id,
                "messages": [],
                "stream": False,
                "keep_alive": 0,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                if resp.status_code < 400:
                    logger.info("Unloaded %s from Ollama", model_id)
        except Exception as e:
            logger.warning("Failed to unload %s from Ollama: %s", model_id, e)

        self._model_states[model_id] = "unloaded"
        return True

    # ── Embedding ──

    async def embed(
        self,
        model_id: str,
        texts: list[str],
        timeout: float = None,
    ) -> list[list[float]]:
        """Generate embeddings via /api/embeddings.

        Ollama's embedding endpoint processes one text at a time (older API)
        or supports the /api/embed batch endpoint (v0.4+). We try batch
        first, then fall back to single-request loop.
        """
        # Try batch endpoint first (Ollama v0.4+)
        try:
            async with httpx.AsyncClient(
                timeout=timeout or self.default_timeout
            ) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": model_id, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) == len(texts):
                    return embeddings
        except httpx.HTTPStatusError:
            pass  # Endpoint not available, fall through
        except Exception:
            pass

        # Fallback: single-text endpoint
        embeddings = []
        async with httpx.AsyncClient(
            timeout=timeout or self.default_timeout
        ) as client:
            for text in texts:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": model_id, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                embedding = data.get("embedding", [])
                embeddings.append(embedding)
        return embeddings

    # ── Download ──

    async def download_model(self, model_id: str) -> bool:
        """Download a model via Ollama's /api/pull endpoint.

        This streams progress and blocks until complete.
        """
        logger.info("Pulling model via Ollama: %s", model_id)
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/pull",
                    json={"name": model_id, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    last_status = ""
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            status = chunk.get("status", "")
                            if status != last_status:
                                logger.info("Ollama pull %s: %s", model_id, status)
                                last_status = status
                            if chunk.get("error"):
                                logger.error(
                                    "Ollama pull error for %s: %s",
                                    model_id, chunk["error"],
                                )
                                return False
                        except json.JSONDecodeError:
                            continue

            self._model_states[model_id] = "downloaded"
            logger.info("Ollama pull complete: %s", model_id)
            return True
        except Exception as e:
            logger.error("Ollama pull failed for %s: %s", model_id, e)
            return False
