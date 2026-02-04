"""
ModelManager — VRAM-aware model lifecycle management.

The traffic cop's engine room. Manages which models are loaded in LM Studio
based on task demand, reference counting, and live system resource monitoring.

Architecture:
  - Always-loaded tier: classifier, embedder, conversational, orchestrator
    These stay resident in VRAM at all times.
  - On-demand tier: primary (70B), security, coder, etc.
    Spun up before task dispatch, spun down after a cooldown TTL.
  - VRAM monitoring: queries live state from system_awareness + LM Studio API.
  - Collision prevention: only one large model loads at a time.
  - Reference counting: models stay loaded while tasks reference them.
  - Deferred unload: on-demand models get a TTL grace period before eviction.
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class ModelManager:
    """VRAM-aware model lifecycle manager.

    Tracks model load state, reference counts, and coordinates with
    the inference router for load/unload operations. Uses live system
    monitoring (not hardcoded budgets) to make eviction decisions.
    """

    def __init__(self, inference_router, always_loaded: set[str],
                 managed: set[str], system_awareness=None):
        self._router = inference_router
        self._system = system_awareness
        self._always_loaded = frozenset(always_loaded)
        self._managed = frozenset(managed)

        # State tracking
        self._lock = asyncio.Lock()
        self._refs: dict[str, int] = {}           # model_key -> active reference count
        self._loaded: dict[str, bool] = {}         # model_key -> is currently loaded
        self._last_used: dict[str, float] = {}     # model_key -> timestamp of last release
        self._unload_tasks: dict[str, asyncio.Task] = {}  # model_key -> pending unload task
        self._load_lock = asyncio.Lock()           # serialize large model loads

        # Tunables
        self._ttl_seconds = 300        # 5 min cooldown before unloading on-demand models
        self._large_model_threshold = 20  # GB — models above this are "large"

        # Event for broadcasting model state changes
        self._broadcast = None

        self._running = False

    def set_broadcast(self, broadcast_fn):
        """Set the WebSocket broadcast function for model state events."""
        self._broadcast = broadcast_fn

    # ── Startup ──

    async def start(self):
        """Initialize model states from LM Studio and load always-loaded models."""
        self._running = True

        # Discover what's currently loaded
        await self._sync_loaded_state()

        # Ensure always-loaded models are resident
        for model_key in self._always_loaded:
            if not self._loaded.get(model_key):
                logger.info("Loading always-on model: %s", model_key)
                success = await self._do_load(model_key)
                if not success:
                    logger.warning("Failed to load always-on model: %s", model_key)

        loaded = [k for k, v in self._loaded.items() if v]
        logger.info("ModelManager started — loaded: %s", ", ".join(loaded) or "none")

    async def stop(self):
        """Cancel pending unload tasks."""
        self._running = False
        for task in self._unload_tasks.values():
            task.cancel()
        self._unload_tasks.clear()

    # ── Core Lifecycle API ──

    async def ensure_loaded(self, model_key: str) -> bool:
        """Ensure a model is loaded and acquire a reference.

        Call this before dispatching a task to an agent. The reference
        prevents the model from being unloaded while the task runs.

        Returns True if the model is loaded and ready.
        """
        async with self._lock:
            # Cancel any pending unload for this model
            pending = self._unload_tasks.pop(model_key, None)
            if pending:
                pending.cancel()
                logger.debug("Cancelled pending unload for %s", model_key)

            # Increment reference count
            self._refs[model_key] = self._refs.get(model_key, 0) + 1

            # Already loaded — fast path
            if self._loaded.get(model_key):
                return True

        # Need to load — this may take time, so release the state lock
        # but hold the load lock to prevent concurrent large model loads
        if model_key in self._managed:
            async with self._load_lock:
                # Check again under load lock (another task may have loaded it)
                if self._loaded.get(model_key):
                    return True

                # Make room if needed
                await self._make_room(model_key)
                success = await self._do_load(model_key)
                return success
        else:
            # Always-loaded models just load directly
            success = await self._do_load(model_key)
            return success

    async def release(self, model_key: str):
        """Release a model reference after task completion.

        If no more references remain and the model is on-demand,
        schedules a deferred unload after TTL cooldown.
        """
        async with self._lock:
            refs = max(0, self._refs.get(model_key, 1) - 1)
            self._refs[model_key] = refs
            self._last_used[model_key] = time.time()

            # Always-loaded models never get unloaded
            if model_key in self._always_loaded:
                return

            # On-demand: schedule deferred unload if no more references
            if refs <= 0 and model_key not in self._unload_tasks:
                self._unload_tasks[model_key] = asyncio.create_task(
                    self._deferred_unload(model_key)
                )

    async def force_unload(self, model_key: str) -> bool:
        """Immediately unload a model (bypasses TTL). For VRAM pressure relief."""
        if model_key in self._always_loaded:
            logger.warning("Cannot force-unload always-loaded model: %s", model_key)
            return False

        # Cancel pending deferred unload
        pending = self._unload_tasks.pop(model_key, None)
        if pending:
            pending.cancel()

        return await self._do_unload(model_key)

    # ── Internal Operations ──

    async def _do_load(self, model_key: str) -> bool:
        """Actually load a model via the inference router."""
        try:
            success = await self._router.load_model(model_key)
            async with self._lock:
                self._loaded[model_key] = success

            if success:
                logger.info("Loaded model: %s", model_key)
                await self._broadcast_state("model_loaded", model_key)
            else:
                logger.error("Failed to load model: %s", model_key)

            return success
        except Exception as e:
            logger.error("Error loading model %s: %s", model_key, e)
            return False

    async def _do_unload(self, model_key: str) -> bool:
        """Actually unload a model via the inference router."""
        try:
            success = await self._router.unload_model(model_key)
            async with self._lock:
                self._loaded[model_key] = False
                self._refs.pop(model_key, None)

            logger.info("Unloaded model: %s", model_key)
            await self._broadcast_state("model_unloaded", model_key)
            return success
        except Exception as e:
            logger.error("Error unloading model %s: %s", model_key, e)
            return False

    async def _deferred_unload(self, model_key: str):
        """Wait TTL then unload if still unreferenced."""
        try:
            await asyncio.sleep(self._ttl_seconds)
        except asyncio.CancelledError:
            return

        async with self._lock:
            refs = self._refs.get(model_key, 0)
            if refs > 0:
                # Something grabbed a reference during the TTL window
                self._unload_tasks.pop(model_key, None)
                return

        await self._do_unload(model_key)
        async with self._lock:
            self._unload_tasks.pop(model_key, None)

    async def _make_room(self, needed_model_key: str):
        """Evict on-demand models if system memory is under pressure.

        Uses live resource monitoring — not hardcoded budgets.
        Evicts least-recently-used on-demand models first.
        """
        # Get live resource snapshot
        available_gb = await self._get_available_memory_gb()
        if available_gb is None:
            # Can't determine memory state — proceed optimistically
            return

        # If we have plenty of headroom, no eviction needed
        # Reserve 8 GB for system + inference overhead
        if available_gb > 12:
            return

        logger.info("Memory pressure detected (%.1f GB available) — evicting on-demand models",
                     available_gb)

        # Find eviction candidates: loaded, on-demand, unreferenced
        candidates = []
        async with self._lock:
            for mk in self._managed:
                if mk == needed_model_key:
                    continue  # Don't evict the model we're about to load
                if self._loaded.get(mk) and self._refs.get(mk, 0) <= 0:
                    candidates.append((mk, self._last_used.get(mk, 0)))

        # Sort by least recently used
        candidates.sort(key=lambda x: x[1])

        for mk, _ in candidates:
            logger.info("Evicting on-demand model for VRAM: %s", mk)
            # Cancel any pending deferred unload
            pending = self._unload_tasks.pop(mk, None)
            if pending:
                pending.cancel()
            await self._do_unload(mk)

            # Re-check memory after each eviction
            available_gb = await self._get_available_memory_gb()
            if available_gb and available_gb > 12:
                break

    async def _get_available_memory_gb(self) -> Optional[float]:
        """Get available system memory in GB using live monitoring.

        On Apple Silicon (unified memory), this is RAM available.
        On discrete GPU systems, this would check VRAM via nvidia-smi.
        """
        if self._system:
            try:
                snapshot = self._system.snapshot_resources()
                available = snapshot.get("ram_available_gb")
                if available is not None:
                    return float(available)
                # Try GPU available (NVIDIA)
                gpu_available = snapshot.get("gpu_available_gb")
                if gpu_available is not None:
                    return float(gpu_available)
            except Exception as e:
                logger.debug("Resource snapshot failed: %s", e)

        # Fallback: use psutil directly
        try:
            import psutil
            mem = psutil.virtual_memory()
            return round(mem.available / (1024**3), 2)
        except ImportError:
            return None

    async def _sync_loaded_state(self):
        """Query LM Studio for currently loaded models and sync internal state."""
        try:
            from config import MODELS
            discovered = await self._router.discover_models()
            loaded_ids = set(discovered.keys())

            async with self._lock:
                for model_key, model_id in MODELS.items():
                    self._loaded[model_key] = model_id in loaded_ids
                    if model_id in loaded_ids:
                        logger.debug("Synced: %s is loaded", model_key)
        except Exception as e:
            logger.warning("Failed to sync model states from LM Studio: %s", e)

    # ── Broadcast ──

    async def _broadcast_state(self, event: str, model_key: str):
        """Broadcast model lifecycle events via WebSocket."""
        if self._broadcast:
            try:
                await self._broadcast({
                    "type": "model_lifecycle",
                    "event": event,
                    "model_key": model_key,
                    "loaded_models": self.get_loaded_models(),
                    "managed_refs": {k: v for k, v in self._refs.items() if v > 0},
                })
            except Exception:
                pass

    # ── Status / Introspection ──

    def get_loaded_models(self) -> list[str]:
        """Get list of currently loaded model keys."""
        return [k for k, v in self._loaded.items() if v]

    def get_status(self) -> dict:
        """Get full model manager status for monitoring/UI."""
        return {
            "always_loaded": sorted(self._always_loaded),
            "managed": sorted(self._managed),
            "currently_loaded": self.get_loaded_models(),
            "references": {k: v for k, v in self._refs.items() if v > 0},
            "pending_unloads": list(self._unload_tasks.keys()),
            "last_used": {
                k: round(time.time() - v, 1)
                for k, v in self._last_used.items()
            },
            "ttl_seconds": self._ttl_seconds,
        }

    def is_loaded(self, model_key: str) -> bool:
        """Check if a model is currently loaded."""
        return self._loaded.get(model_key, False)

    def get_ref_count(self, model_key: str) -> int:
        """Get the current reference count for a model."""
        return self._refs.get(model_key, 0)
