"""
Rust Inference Router - Drop-in replacement using Rust backend.

This module provides a Python wrapper around the Rust InferenceRouter implementation
for backwards compatibility with existing code.
"""

from typing import Any, Callable, Optional

try:
    from moose_core import InferenceRouter as RustInferenceRouter
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    RustInferenceRouter = None


class InferenceRouter:
    """
    Drop-in replacement for the Python InferenceRouter using Rust backend.

    Features:
    - Multiple backend support (LlamaCpp, Ollama, OpenAI-compatible)
    - Model key mapping (primary, classifier, security, embedder)
    - Semaphore-based slot management
    - Streaming support with channels
    - Connection pooling per backend
    """

    def __init__(self):
        """Initialize the InferenceRouter."""
        if not RUST_AVAILABLE:
            raise ImportError(
                "moose_core Rust extension not available. "
                "Build with: cd backend/rust_core && maturin develop --release"
            )

        self._inner = RustInferenceRouter()

    def initialize(self, config: dict) -> None:
        """
        Initialize the router with configuration.

        Args:
            config: Configuration dictionary with keys:
                - backends: Dict of backend configurations
                    - type: Backend type (llamacpp, ollama, openai)
                    - base_url: Backend URL
                    - api_key: Optional API key
                    - max_slots: Optional max concurrent requests
                - models: Dict of model key mappings
                    - backend: Backend name
                    - model_id: Model identifier
        """
        self._inner.initialize(config)

    async def discover_models(
        self,
        backend_name: Optional[str] = None,
    ) -> dict[str, dict]:
        """
        Discover available models from backends.

        Args:
            backend_name: Optional backend to query (all if None)

        Returns:
            Dict of model ID to model info
        """
        return await self._inner.discover_models(backend_name)

    async def call_llm(
        self,
        model_key_or_id: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tool_choice: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """
        Call an LLM with messages.

        Args:
            model_key_or_id: Model key (primary, classifier, etc.) or model ID
            messages: List of message dictionaries
            tools: Optional list of tool schemas
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            tool_choice: Tool choice mode
            timeout: Request timeout in seconds

        Returns:
            Response dictionary with keys:
                - content: Generated text
                - model: Model used
                - finish_reason: Why generation stopped
                - tool_calls: List of tool calls
                - usage: Token usage info
        """
        return await self._inner.call_llm(
            model_key_or_id,
            messages,
            tools,
            max_tokens,
            temperature,
            tool_choice,
            timeout,
        )

    async def call_llm_stream(
        self,
        model_key_or_id: str,
        messages: list[dict],
        on_chunk: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Call an LLM with streaming response.

        Args:
            model_key_or_id: Model key or model ID
            messages: List of message dictionaries
            on_chunk: Callback for each streamed chunk
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Full generated text
        """
        return await self._inner.call_llm_stream(
            model_key_or_id,
            messages,
            on_chunk,
            max_tokens,
            temperature,
        )

    async def embed(
        self,
        model_key_or_id: str,
        texts: list[str],
        timeout: Optional[float] = None,
    ) -> list[list[float]]:
        """
        Generate embeddings.

        Args:
            model_key_or_id: Model key or model ID
            texts: List of texts to embed
            timeout: Request timeout in seconds

        Returns:
            List of embedding vectors
        """
        return await self._inner.embed(model_key_or_id, texts, timeout)

    def has_slot(self, model_key: str) -> bool:
        """
        Check if a slot is available for a model.

        Args:
            model_key: Model key

        Returns:
            True if slot is available
        """
        return self._inner.has_slot(model_key)

    async def acquire_slot(self, model_key: str) -> bool:
        """
        Acquire a slot for a model.

        Args:
            model_key: Model key

        Returns:
            True if slot was acquired
        """
        return await self._inner.acquire_slot(model_key)

    def release_slot(self, model_key: str) -> None:
        """
        Release a slot for a model.

        Args:
            model_key: Model key
        """
        self._inner.release_slot(model_key)

    async def load_model(
        self,
        model_key_or_id: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Load a model into memory.

        Args:
            model_key_or_id: Model key or model ID
            ttl: Time to live in seconds

        Returns:
            True if model was loaded
        """
        return await self._inner.load_model(model_key_or_id, ttl)

    async def unload_model(self, model_key_or_id: str) -> bool:
        """
        Unload a model from memory.

        Args:
            model_key_or_id: Model key or model ID

        Returns:
            True if model was unloaded
        """
        return await self._inner.unload_model(model_key_or_id)

    def add_model_mapping(
        self,
        key: str,
        backend_name: str,
        model_id: str,
    ) -> None:
        """
        Add a model mapping.

        Args:
            key: Model key (e.g., "primary", "classifier")
            backend_name: Backend name
            model_id: Model identifier
        """
        self._inner.add_model_mapping(key, backend_name, model_id)

    def get_model_mapping(self) -> dict[str, tuple[str, str]]:
        """
        Get current model mappings.

        Returns:
            Dict of model key to (backend_name, model_id)
        """
        return self._inner.get_model_mapping()

    def list_backends(self) -> list[str]:
        """
        List configured backends.

        Returns:
            List of backend names
        """
        return self._inner.list_backends()


# Singleton instance
_router: Optional[InferenceRouter] = None


def get_router() -> InferenceRouter:
    """
    Get the singleton InferenceRouter instance.

    Returns:
        InferenceRouter instance
    """
    global _router
    if _router is None:
        _router = InferenceRouter()
    return _router


# Export for backwards compatibility
__all__ = ["InferenceRouter", "get_router", "RUST_AVAILABLE"]
