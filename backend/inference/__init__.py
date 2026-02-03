"""
Inference package — Multi-backend inference abstraction layer.

Provides adapters for multiple LLM inference servers and a router that
maps model keys to the correct backend based on profile configuration.

Quick start:
    from inference import get_router
    router = get_router()
    result = await router.call_llm("primary", messages=[...])

Backward compatibility:
    from inference import InferenceBackend  # imports OpenAICompatBackend
"""

from inference.base import InferenceBackend as BaseInferenceBackend
from inference.openai_compat import OpenAICompatBackend
from inference.ollama import OllamaBackend
from inference.llamacpp import LlamaCppBackend
from inference.router import InferenceRouter, get_router

# Backward compatibility: `from inference import InferenceBackend` returns
# the OpenAI-compatible adapter, which is what the old inference.py provided.
# Code that used `InferenceBackend(base_url)` will continue to work unchanged.
InferenceBackend = OpenAICompatBackend

__all__ = [
    "InferenceBackend",
    "BaseInferenceBackend",
    "OpenAICompatBackend",
    "OllamaBackend",
    "LlamaCppBackend",
    "InferenceRouter",
    "get_router",
]
