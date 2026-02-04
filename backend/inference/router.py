"""
InferenceRouter — Multiplexing layer that routes model requests to backends.

Reads the profile config to determine which backend adapter handles each
model key (primary, classifier, security, embedder). Presents the same
interface as InferenceBackend so it's a drop-in replacement anywhere the
old single-backend InferenceBackend was used.

Usage:
    from inference import get_router
    router = get_router()
    result = await router.call_llm("primary", messages=[...])
"""

import asyncio
import logging
from typing import Optional

from profile import get_profile

from inference.base import InferenceBackend
from inference.openai_compat import OpenAICompatBackend
from inference.ollama import OllamaBackend
from inference.llamacpp import LlamaCppBackend

logger = logging.getLogger(__name__)

# Map of backend type strings to adapter classes
_BACKEND_CLASSES: dict[str, type[InferenceBackend]] = {
    "openai": OpenAICompatBackend,
    "ollama": OllamaBackend,
    "llamacpp": LlamaCppBackend,
}


class InferenceRouter:
    """Routes inference calls to the correct backend adapter based on profile config.

    The router reads `profile.inference.backends` to instantiate adapter objects,
    and `profile.inference.models` to map model keys to their backend and model_id.

    It exposes the same method signatures as InferenceBackend, making it a
    drop-in replacement. Model keys (like 'primary', 'classifier') are resolved
    to (backend_adapter, actual_model_id) pairs internally.
    """

    def __init__(self):
        self._backends: dict[str, InferenceBackend] = {}
        self._model_map: dict[str, tuple[str, str]] = {}  # key -> (backend_name, model_id)
        self._default_backend: Optional[str] = None
        self._initialized = False

    def initialize(self):
        """Read profile config and set up backend adapters and model routing.

        Can be called multiple times to re-read config (e.g., after profile reload).
        """
        profile = get_profile()
        inference_cfg = profile.inference

        # ── Build backend adapters ──
        self._backends.clear()
        for backend_cfg in inference_cfg.backends:
            if not backend_cfg.enabled:
                logger.info("Skipping disabled backend: %s", backend_cfg.name)
                continue

            backend_type = backend_cfg.type.lower()
            adapter_cls = _BACKEND_CLASSES.get(backend_type)
            if adapter_cls is None:
                logger.error(
                    "Unknown backend type '%s' for backend '%s'. "
                    "Supported types: %s",
                    backend_type, backend_cfg.name,
                    ", ".join(_BACKEND_CLASSES.keys()),
                )
                continue

            adapter = adapter_cls(base_url=backend_cfg.endpoint)
            self._backends[backend_cfg.name] = adapter
            logger.info(
                "Registered backend '%s' (%s) at %s",
                backend_cfg.name, backend_type, backend_cfg.endpoint,
            )

        # Set default backend (first enabled one, or the one named 'default')
        if "default" in self._backends:
            self._default_backend = "default"
        elif self._backends:
            self._default_backend = next(iter(self._backends))
        else:
            logger.warning("No backends configured or enabled")
            self._default_backend = None

        # ── Build model key -> (backend_name, model_id) map ──
        self._model_map.clear()
        models_cfg = inference_cfg.models

        # Iterate over the ModelsConfig dataclass fields
        for key in ("primary", "conversational", "orchestrator", "classifier", "security", "embedder"):
            model_cfg = getattr(models_cfg, key, None)
            if model_cfg is None:
                continue

            backend_name = model_cfg.backend or "default"
            model_id = model_cfg.model_id

            if not model_id:
                logger.debug("No model_id for key '%s', skipping", key)
                continue

            if backend_name not in self._backends:
                # Try default backend as fallback
                if self._default_backend and self._default_backend in self._backends:
                    logger.warning(
                        "Backend '%s' for model key '%s' not found; "
                        "falling back to '%s'",
                        backend_name, key, self._default_backend,
                    )
                    backend_name = self._default_backend
                else:
                    logger.error(
                        "Backend '%s' for model key '%s' not found and no default",
                        backend_name, key,
                    )
                    continue

            self._model_map[key] = (backend_name, model_id)
            logger.info(
                "Model key '%s' -> model '%s' on backend '%s'",
                key, model_id, backend_name,
            )

        self._initialized = True

    def _ensure_initialized(self):
        """Lazily initialize on first use."""
        if not self._initialized:
            self.initialize()

    def _resolve(self, model_key_or_id: str) -> tuple[InferenceBackend, str]:
        """Resolve a model key or raw model_id to (adapter, model_id).

        Resolution order:
        1. If it's a known model key (primary, classifier, etc.), use the mapping.
        2. If it looks like a model_id (contains '/' or is not a known key),
           route to the default backend.
        3. Raise ValueError if no backend can handle it.
        """
        self._ensure_initialized()

        # Check model key map first
        if model_key_or_id in self._model_map:
            backend_name, model_id = self._model_map[model_key_or_id]
            return self._backends[backend_name], model_id

        # Treat as a raw model_id — route to default backend
        if self._default_backend and self._default_backend in self._backends:
            return self._backends[self._default_backend], model_key_or_id

        raise ValueError(
            f"Cannot resolve model '{model_key_or_id}': no mapping found "
            f"and no default backend available"
        )

    def get_backend(self, name: str) -> Optional[InferenceBackend]:
        """Get a specific backend adapter by name."""
        self._ensure_initialized()
        return self._backends.get(name)

    def get_model_config(self, key: str):
        """Get the ModelConfig for a model key from the profile."""
        profile = get_profile()
        return getattr(profile.inference.models, key, None)

    @property
    def backends(self) -> dict[str, InferenceBackend]:
        """All registered backend adapters."""
        self._ensure_initialized()
        return dict(self._backends)

    @property
    def model_map(self) -> dict[str, tuple[str, str]]:
        """Model key -> (backend_name, model_id) mapping."""
        self._ensure_initialized()
        return dict(self._model_map)

    # ── InferenceBackend-compatible interface ──
    # Each method resolves the model key/id and forwards to the right adapter.

    async def discover_models(self, backend_name: str = None) -> dict[str, dict]:
        """Discover models on one or all backends.

        Args:
            backend_name: If given, discover only on that backend.
                         If None, discover on all backends and merge results.
        """
        self._ensure_initialized()

        if backend_name:
            backend = self._backends.get(backend_name)
            if not backend:
                raise ValueError(f"Unknown backend: {backend_name}")
            return await backend.discover_models()

        # Discover on all backends concurrently
        all_models = {}
        tasks = {}
        for name, backend in self._backends.items():
            tasks[name] = asyncio.create_task(backend.discover_models())

        for name, task in tasks.items():
            try:
                models = await task
                # Prefix model IDs with backend name to avoid collisions
                for mid, meta in models.items():
                    meta["_backend"] = name
                    all_models[mid] = meta
            except Exception as e:
                logger.error("Failed to discover models on '%s': %s", name, e)

        return all_models

    async def call_llm(
        self,
        model_key_or_id: str,
        messages: list[dict],
        tools: list[dict] = None,
        max_tokens: int = None,
        temperature: float = None,
        tool_choice: str = None,
        timeout: float = None,
        draft_model: str = None,
    ) -> dict:
        """Route a chat completion to the correct backend.

        If max_tokens or temperature are None, values from the model's
        profile config are used (if the key maps to a known model config).
        """
        backend, model_id = self._resolve(model_key_or_id)

        # Apply profile defaults for known model keys
        model_cfg = self.get_model_config(model_key_or_id)
        if model_cfg:
            if max_tokens is None:
                max_tokens = model_cfg.max_tokens
            if temperature is None:
                temperature = model_cfg.temperature
        if max_tokens is None:
            max_tokens = 2048
        if temperature is None:
            temperature = 0.7

        return await backend.call_llm(
            model_id=model_id,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            tool_choice=tool_choice,
            timeout=timeout,
            draft_model=draft_model,
        )

    async def call_llm_stream(
        self,
        model_key_or_id: str,
        messages: list[dict],
        max_tokens: int = None,
        temperature: float = None,
        on_chunk=None,
    ) -> str:
        """Route a streaming chat completion to the correct backend."""
        backend, model_id = self._resolve(model_key_or_id)

        model_cfg = self.get_model_config(model_key_or_id)
        if model_cfg:
            if max_tokens is None:
                max_tokens = model_cfg.max_tokens
            if temperature is None:
                temperature = model_cfg.temperature
        if max_tokens is None:
            max_tokens = 2048
        if temperature is None:
            temperature = 0.7

        return await backend.call_llm_stream(
            model_id=model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            on_chunk=on_chunk,
        )

    async def load_model(self, model_key_or_id: str, ttl: int = None, **kwargs) -> bool:
        """Load a model on the appropriate backend."""
        backend, model_id = self._resolve(model_key_or_id)
        return await backend.load_model(model_id, ttl=ttl, **kwargs)

    async def unload_model(self, model_key_or_id: str) -> bool:
        """Unload a model from the appropriate backend."""
        backend, model_id = self._resolve(model_key_or_id)
        return await backend.unload_model(model_id)

    async def embed(
        self,
        model_key_or_id: str,
        texts: list[str],
        timeout: float = None,
    ) -> list[list[float]]:
        """Route an embedding request to the correct backend."""
        backend, model_id = self._resolve(model_key_or_id)
        return await backend.embed(model_id, texts, timeout=timeout)

    def estimate_model(self, model_key_or_id: str) -> dict:
        """Get cached model info from the appropriate backend."""
        backend, model_id = self._resolve(model_key_or_id)
        return backend.estimate_model(model_id)

    def get_model_state(self, model_key_or_id: str) -> str:
        """Get cached model state from the appropriate backend."""
        backend, model_id = self._resolve(model_key_or_id)
        return backend.get_model_state(model_id)

    async def download_model(self, model_key_or_id: str) -> bool:
        """Download a model via the appropriate backend."""
        backend, model_id = self._resolve(model_key_or_id)
        return await backend.download_model(model_id)

    def has_slot(self, model_key_or_id: str) -> bool:
        """Check if the model has an available inference slot."""
        backend, model_id = self._resolve(model_key_or_id)
        return backend.has_slot(model_id)

    async def acquire_slot(self, model_key_or_id: str) -> bool:
        """Acquire an inference slot for the model."""
        backend, model_id = self._resolve(model_key_or_id)
        return await backend.acquire_slot(model_id)

    async def release_slot(self, model_key_or_id: str):
        """Release an inference slot for the model."""
        backend, model_id = self._resolve(model_key_or_id)
        return await backend.release_slot(model_id)


# ── Singleton ──

_router: Optional[InferenceRouter] = None


def get_router() -> InferenceRouter:
    """Return the global InferenceRouter singleton. Initializes on first call."""
    global _router
    if _router is None:
        _router = InferenceRouter()
        _router.initialize()
    return _router
