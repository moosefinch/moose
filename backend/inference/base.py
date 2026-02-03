"""
Abstract base class for all inference backend adapters.

Every backend adapter (OpenAI-compatible, Ollama, llama.cpp) must implement
this interface so the InferenceRouter can treat them interchangeably.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class InferenceBackend(ABC):
    """Abstract inference backend interface.

    Concrete adapters implement the HTTP-specific details for their server type
    while exposing a uniform interface for model discovery, chat completion,
    streaming, embedding, and model lifecycle management.
    """

    def __init__(self, base_url: str, default_timeout: float = 300):
        self.base_url = base_url.rstrip("/")
        self.default_timeout = default_timeout
        self._model_lock = asyncio.Lock()
        self._model_states: dict[str, str] = {}  # model_id -> state
        self._active_requests: dict[str, int] = {}
        self._max_slots = 4
        self._model_capabilities: dict[str, list[str]] = {}
        self._slot_lock = asyncio.Lock()

    # ── Model Discovery ──

    @abstractmethod
    async def discover_models(self) -> dict[str, dict]:
        """Query the backend for available models.

        Returns:
            Dict keyed by model_id, values are metadata dicts with at least
            'id' and optionally 'state', 'capabilities', etc.
        """
        ...

    # ── Chat Completion ──

    @abstractmethod
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
        """Non-streaming chat completion.

        Args:
            model_id: Model identifier as known by the backend.
            messages: OpenAI-format message list.
            tools: Optional tool definitions (OpenAI function-calling schema).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            tool_choice: How to select tools ('auto', 'none', or a tool name).
            timeout: Per-request timeout override.
            draft_model: Speculative-decoding draft model (backend-specific).

        Returns:
            OpenAI-compatible response dict with 'choices', 'usage', etc.
        """
        ...

    @abstractmethod
    async def call_llm_stream(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        on_chunk=None,
    ) -> str:
        """Streaming chat completion.

        Args:
            model_id: Model identifier.
            messages: OpenAI-format message list.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            on_chunk: Optional async callable(content: str) invoked per chunk.

        Returns:
            Full accumulated response text.
        """
        ...

    # ── Model Lifecycle ──

    @abstractmethod
    async def load_model(self, model_id: str, ttl: int = None, **kwargs) -> bool:
        """Load or verify a model is ready for inference.

        Returns True if the model is loaded and ready.
        """
        ...

    @abstractmethod
    async def unload_model(self, model_id: str) -> bool:
        """Unload a model from the backend.

        Returns True on success. Some backends may treat this as a no-op.
        """
        ...

    # ── Embedding ──

    @abstractmethod
    async def embed(
        self,
        model_id: str,
        texts: list[str],
        timeout: float = None,
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            model_id: Embedding model identifier.
            texts: List of strings to embed.
            timeout: Per-request timeout override.

        Returns:
            List of embedding vectors (one per input text).
        """
        ...

    # ── Model Info ──

    def estimate_model(self, model_id: str) -> dict:
        """Return cached model info for VRAM estimation and capabilities."""
        return {
            "model_id": model_id,
            "state": self._model_states.get(model_id, "unknown"),
            "capabilities": self._model_capabilities.get(model_id, []),
        }

    def get_model_state(self, model_id: str) -> str:
        """Return the cached state of a model."""
        return self._model_states.get(model_id, "unknown")

    # ── Download ──

    async def download_model(self, model_id: str) -> bool:
        """Download a model. Default implementation uses huggingface-cli.

        Subclasses can override for backend-specific download (e.g. ollama pull).
        """
        logger.info("Downloading model: %s", model_id)
        try:
            proc = await asyncio.create_subprocess_exec(
                "huggingface-cli", "download", model_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info("Download complete: %s", model_id)
                return True
            else:
                err = stderr.decode().strip()[:500] if stderr else "unknown error"
                logger.error("Download failed for %s: %s", model_id, err)
                return False
        except FileNotFoundError:
            logger.error(
                "huggingface-cli not found — install with: pip install huggingface_hub[cli]"
            )
            return False
        except Exception as e:
            logger.error("Download error for %s: %s", model_id, e)
            return False

    # ── Slot Management ──

    def has_slot(self, model_id: str) -> bool:
        """Check if a model has an available inference slot."""
        return self._active_requests.get(model_id, 0) < self._max_slots

    async def acquire_slot(self, model_id: str) -> bool:
        """Acquire an inference slot. Returns False if at capacity."""
        async with self._slot_lock:
            current = self._active_requests.get(model_id, 0)
            if current >= self._max_slots:
                return False
            self._active_requests[model_id] = current + 1
            return True

    async def release_slot(self, model_id: str):
        """Release an inference slot."""
        async with self._slot_lock:
            current = self._active_requests.get(model_id, 0)
            self._active_requests[model_id] = max(0, current - 1)
