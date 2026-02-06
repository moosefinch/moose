"""
AgentCore — Multi-agent orchestration engine.

Architecture:
  - Central inference engine handles all tool-calling agents
  - Classifier: Fast-path query classification (always loaded)
  - Presentation layer: Configurable personality from profile (optional)
  - Security monitor: Continuous advisory screening (always loaded)
  - Embedder: Memory/RAG embeddings (always loaded)
  - Claude: External API, complex code tasks

Features:
  - Agent abstractions (coder, math, reasoner, etc.) with filtered tool sets
  - Fast-path classification (TRIVIAL/SIMPLE/COMPLEX)
  - TRIVIAL → presentation layer responds directly (0 agent coordination)
  - SIMPLE → planner routes single task, agent executes, presentation formats
  - COMPLEX → planner routes multi-task, agents execute, results synthesized
  - Escalation flow: user approval required for Claude
  - Passive security screening
  - Autonomous long-running background tasks
"""

import asyncio
import inspect
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

from config import (
    API_BASE,
    MODELS, MODEL_LABELS,
    ALWAYS_LOADED_MODELS, MANAGED_MODELS,
    DEFAULT_TIMEOUT, MAX_TOOL_ROUNDS,
    TOKEN_LIMITS, TEMPERATURE, CONTEXT_WINDOW_SIZE,
    CLASSIFIER_MAX_TOKENS, CLASSIFIER_TEMPERATURE,
    TRIVIAL_RESPONSE_MAX_TOKENS, TRIVIAL_RESPONSE_TEMPERATURE,
    ESCALATION_CONFIG,
    COGNITIVE_LOOP_CONFIG,
    STATE_DIR, STATE_FILE_PATH, SOUL_FILE_PATH,
)
from profile import get_profile
from inference import InferenceRouter, get_router
from memory import VectorMemory
from memory_v2 import MemoryV2
from tools import get_all_tools, get_execution_tools, get_tools_for_agent, set_core_ref

# Agent system imports — importing agents triggers auto-registration
from agents.base import BaseAgent
import agents  # noqa: F401 — triggers @register_agent_class decorators
from agents.registry import AgentRegistry
from orchestration.messages import MessageBus, AgentMessage, MessageType, MessagePriority
from orchestration.workspace import SharedWorkspace
from orchestration.scheduler import GPUScheduler
from orchestration.model_manager import ModelManager
from orchestration.channels import ChannelManager

# Import prompts from canonical location — no duplicates here
from agents.prompts import (
    SUSPICIOUS_PATTERNS, CLASSIFIER_PROMPT,
    get_presentation_prompt, build_trivial_prompt,
)

# Mixin classes — extracted method groups for modularity
from core.state import _StateMixin
from core.classification import _ClassificationMixin
from core.escalation import _EscalationMixin
from core.chat_pipeline import _ChatPipelineMixin
from core.background_tasks import BackgroundTask


def _build_tool_schemas(tools: list) -> list[dict]:
    """Convert tool functions to OpenAI-compatible tool schemas."""
    schemas = []
    for fn in tools:
        hints = fn.__annotations__
        params = {}
        required = []
        for name, hint in hints.items():
            if name == "return":
                continue
            ptype = "string"
            if hint == int:
                ptype = "integer"
            elif hint == float:
                ptype = "number"
            elif hint == bool:
                ptype = "boolean"
            params[name] = {"type": ptype, "description": f"The {name} parameter"}
            sig = inspect.signature(fn)
            if sig.parameters[name].default is inspect.Parameter.empty:
                required.append(name)

        schemas.append({
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": (fn.__doc__ or "").strip(),
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": required,
                },
            },
        })
    return schemas


class AgentCore(_StateMixin, _ClassificationMixin, _EscalationMixin, _ChatPipelineMixin):
    def __init__(self):
        self.available_models: dict[str, bool] = {}
        self.model_states: dict[str, str] = {}
        self.memory = VectorMemory()
        self.tools = get_all_tools()
        self.tool_schemas = _build_tool_schemas(self.tools)
        self.tool_map = {fn.__name__: fn for fn in self.tools}
        self.exec_tools = get_execution_tools()
        self.exec_tool_schemas = _build_tool_schemas(self.exec_tools)
        self.exec_tool_map = {fn.__name__: fn for fn in self.exec_tools}
        # Per-agent tool schema cache (lazy-built)
        self._agent_tool_schemas: dict[str, list[dict]] = {}
        self.ws_clients: list = []
        self._overlays: dict = {}
        self._ready = False
        # Background tasks
        self._tasks: dict[str, BackgroundTask] = {}
        self._briefings: list[dict] = []
        # Inference router (multi-backend)
        self.inference = get_router()
        # Agent system
        self.bus: Optional[MessageBus] = None
        self.workspace: Optional[SharedWorkspace] = None
        self.registry: Optional[AgentRegistry] = None
        self.scheduler: Optional[GPUScheduler] = None
        self.channel_manager: Optional[ChannelManager] = None
        # Escalation state — pending user decisions
        self._pending_escalations: dict[str, dict] = {}
        # Cognitive loop
        self.cognitive_loop = None
        # Persistent state
        self._state = self._load_state()
        self._startup_time: Optional[float] = None
        # Model lifecycle manager
        self.model_manager: Optional[ModelManager] = None
        # Security heartbeat (set in start())
        self._security_heartbeat = None
        # Loaded plugins
        self._plugins: list = []
        # Soul context for presentation layer
        self._soul_context = ""
        # Memory V2 — self-aware, self-populating memory system
        self.memory_v2: Optional[MemoryV2] = None
        self._current_session_id: Optional[str] = None
        # Advocacy subsystem
        self.advocacy_system = None
        # Self-improvement subsystem
        self.improvement_researcher = None
        self.improvement_executor = None

    # ── Model Discovery ──

    async def _fetch_model_states(self) -> dict[str, dict]:
        """Query inference backend for available models."""
        return await self.inference.discover_models()

    async def _load_model(self, model_key: str, **kwargs) -> bool:
        """Load a model via the inference backend."""
        model_id = MODELS.get(model_key)
        if not model_id:
            logger.warning("Unknown model key: %s", model_key)
            return False
        if self.model_states.get(model_key) == "loaded":
            return True
        success = await self.inference.load_model(model_id, **kwargs)
        if success:
            logger.info("Loaded %s (%s)", model_key, model_id)
            self.model_states[model_key] = "loaded"
        else:
            logger.error("Failed to load %s (%s)", model_key, model_id)
        return success

    async def _unload_model(self, model_key: str) -> bool:
        """Unload a model via the inference backend."""
        model_id = MODELS.get(model_key)
        if not model_id:
            return False
        success = await self.inference.unload_model(model_id)
        if success:
            logger.info("Unloaded %s (%s)", model_key, model_id)
            self.model_states[model_key] = "unloaded"
        return success

    # ── Startup / Shutdown ──

    async def start(self):
        """Connect to inference backend and discover available models."""
        set_core_ref(self)

        # Record startup time and restore persistent state
        self._startup_time = time.time()
        self._state["last_startup"] = datetime.now(timezone.utc).isoformat()
        self._soul_context = self._load_soul()
        if self._soul_context:
            logger.info("Soul loaded (%d chars)", len(self._soul_context))

        try:
            backend_models = await self.inference.discover_models()
        except Exception as e:
            logger.error("Cannot reach inference backend at %s: %s", API_BASE, e)
            return

        for key, model_id in MODELS.items():
            if model_id in backend_models:
                state = self.inference.get_model_state(model_id)
                self.available_models[key] = True
                self.model_states[key] = state
                logger.info("+ %s -> %s (%s)", key, model_id, state)
            else:
                self.available_models[key] = False
                self.model_states[key] = "missing"
                logger.warning("x %s -> %s (not available)", key, model_id)

        logger.info("+ claude -> claude-code CLI (Max plan)")

        if self.available_models.get("embedder"):
            self.memory.set_embedder(API_BASE, MODELS["embedder"])
            logger.info("Memory V1 online (%d entries)", self.memory.count())

        # Initialize agent system (creates ModelManager)
        self._init_agent_system()

        # Initialize Memory V2
        await self._init_memory_v2()

        # Start model lifecycle manager — loads always-on models
        if self.model_manager:
            await self.model_manager.start()
            logger.info("ModelManager: always-loaded=%s, managed=%s",
                        sorted(ALWAYS_LOADED_MODELS), sorted(MANAGED_MODELS))

        self._ready = True

        # Start enabled plugins
        await self._start_plugins()

        # Start cognitive loop
        if COGNITIVE_LOOP_CONFIG.get("enabled", True):
            from cognitive_loop import CognitiveLoop
            self.cognitive_loop = CognitiveLoop(self)
            self.cognitive_loop.cycle_interval = COGNITIVE_LOOP_CONFIG.get("cycle_interval_seconds", 120)
            self.cognitive_loop.min_interval = COGNITIVE_LOOP_CONFIG.get("min_interval_seconds", 30)
            self.cognitive_loop._reflection_every_n = COGNITIVE_LOOP_CONFIG.get("reflection_every_n_cycles", 10)
            self.cognitive_loop._morning_briefing_hour = COGNITIVE_LOOP_CONFIG.get("morning_briefing_hour", 9)
            self.cognitive_loop._evening_briefing_hour = COGNITIVE_LOOP_CONFIG.get("evening_briefing_hour", 18)
            await self.cognitive_loop.start()
            logger.info("Cognitive loop started")

        # Start security heartbeat
        from orchestration.scheduler import SecurityHeartbeat
        self._security_heartbeat = SecurityHeartbeat(self)
        self._security_heartbeat.start()

        # Start cron scheduler
        from orchestration.scheduler import CronScheduler
        from tools import DB_PATH
        self._cron_scheduler = CronScheduler(self, str(DB_PATH))
        self._cron_scheduler.start()

        logger.info("Core ready")

    def _init_agent_system(self):
        """Initialize the multi-agent architecture via auto-registration."""
        try:
            self.bus = MessageBus()
            self.workspace = SharedWorkspace()
            self.registry = AgentRegistry()
            self.channel_manager = ChannelManager(agent_core=self)

            # Create all agents from the auto-registration registry
            agent_instances = BaseAgent.create_all(self)
            for agent in agent_instances.values():
                self.registry.register(agent)

            # Register security agent's monitor hook on the message bus
            security_agent = self.registry.get("security")
            if security_agent:
                self.bus.register_monitor_hook(security_agent.receive_bus_copy)

            # Initialize model lifecycle manager
            system_awareness = None
            if self.memory_v2 and hasattr(self.memory_v2, '_system'):
                system_awareness = self.memory_v2._system
            self.model_manager = ModelManager(
                self.inference,
                always_loaded=ALWAYS_LOADED_MODELS,
                managed=MANAGED_MODELS,
                system_awareness=system_awareness,
            )
            self.model_manager.set_broadcast(self.broadcast)

            # Initialize scheduler with model manager and security monitor
            self.scheduler = GPUScheduler(
                self.registry, self.bus, self.workspace, self,
                model_manager=self.model_manager,
            )
            if security_agent:
                self.scheduler.set_security_monitor(security_agent)

            # Wire desktop tool approval broadcasts to WebSocket
            from tools_desktop import set_ws_broadcast
            set_ws_broadcast(self.broadcast)

            agent_ids = self.registry.ids()
            logger.info("Agent system initialized: %s", ", ".join(agent_ids))
            logger.info("Channels: %s", ", ".join(self.channel_manager._channels.keys()))

            # Initialize advocacy subsystem if enabled
            profile = get_profile()
            if profile.advocacy.enabled:
                try:
                    from advocacy import AdvocacySystem
                    from config import ADVOCACY_STATE_DIR
                    self.advocacy_system = AdvocacySystem(
                        config=profile.advocacy,
                        state_dir=ADVOCACY_STATE_DIR,
                        channel_manager=self.channel_manager,
                        bus=self.bus,
                    )
                    logger.info("Advocacy system initialized")
                except Exception as e:
                    logger.error("Advocacy system init failed: %s", e)
                    self.advocacy_system = None

            # Initialize self-improvement subsystem
            try:
                from improvement.researcher import SolutionResearcher
                from improvement.executor import ProposalExecutor
                self.improvement_researcher = SolutionResearcher()
                self.improvement_executor = ProposalExecutor()
                logger.info("Self-improvement system initialized")
            except Exception as e:
                logger.error("Self-improvement system init failed: %s", e)

            # Initialize marketing engine if CRM plugin is enabled
            if profile.plugins.crm.enabled:
                try:
                    from marketing_engine import get_marketing_engine
                    self._marketing_engine = get_marketing_engine()
                    self._marketing_engine.set_ws_broadcast(self.broadcast)
                    self._marketing_engine.set_task_creator(
                        lambda desc: self.start_task(desc)
                    )
                    self._outreach_engine = self._marketing_engine.outreach_engine
                except ImportError:
                    logger.warning("CRM plugin enabled but marketing_engine not found")
                    self._marketing_engine = None
                    self._outreach_engine = None
        except Exception as e:
            logger.error("Agent system init failed: %s", e)
            raise RuntimeError(f"Agent system initialization failed: {e}")

    async def _init_memory_v2(self):
        """Initialize Memory V2 — self-aware, self-populating memory system."""
        try:
            # Create embedder wrapper using existing infrastructure
            async def embedder(text: str) -> list[float]:
                if not self.memory._api_base or not self.memory._embed_model:
                    raise RuntimeError("Embedder not configured")
                return await self.memory.embed(text)

            # Create LLM client wrapper for extraction/summarization
            async def llm_client(model: str, messages: list, **kwargs) -> str:
                model_id = MODELS.get(model, MODELS.get("classifier"))
                if not model_id:
                    raise RuntimeError(f"Model {model} not found")
                result = await self._call_llm(model_id, messages, **kwargs)
                return result["choices"][0]["message"].get("content", "")

            # Initialize Memory V2
            self.memory_v2 = MemoryV2(
                embedder=embedder if self.available_models.get("embedder") else None,
                llm_client=llm_client,
                inference_url=API_BASE
            )
            await self.memory_v2.start()

            # Create initial session
            self._current_session_id = self.memory_v2.create_session()

            logger.info(
                "Memory V2 online: %s, context budget %d tokens",
                self.memory_v2.get_system_profile().get("cpu_model", "Unknown")[:30],
                self.memory_v2.get_context_budget().get("total", 0)
            )

        except Exception as e:
            logger.error("Memory V2 init failed: %s", e)
            # Don't raise - Memory V2 is optional, V1 still works
            self.memory_v2 = None

    async def _start_plugins(self):
        """Load and start enabled plugins."""
        profile = get_profile()
        enabled = []
        if profile.plugins.crm.enabled:
            enabled.append("crm")
        if profile.plugins.telegram.enabled:
            enabled.append("telegram")
        if profile.plugins.slack.enabled:
            enabled.append("slack")
        if getattr(profile.plugins, "printing", None) and getattr(profile.plugins.printing, "enabled", False):
            enabled.append("printing")
        if not enabled:
            return

        from plugins import load_enabled_plugins
        self._plugins = load_enabled_plugins(enabled)

        for plugin in self._plugins:
            start_fn = getattr(plugin, "start", None)
            if start_fn:
                try:
                    await start_fn(self)
                except Exception as e:
                    plugin_id = getattr(plugin, "PLUGIN_ID", "unknown")
                    logger.error("Plugin '%s' start failed: %s", plugin_id, e)

    async def _stop_plugins(self):
        """Stop all loaded plugins."""
        for plugin in self._plugins:
            stop_fn = getattr(plugin, "stop", None)
            if stop_fn:
                try:
                    await stop_fn()
                except Exception as e:
                    plugin_id = getattr(plugin, "PLUGIN_ID", "unknown")
                    logger.error("Plugin '%s' stop failed: %s", plugin_id, e)

    async def shutdown(self):
        """Clean shutdown — cancel background tasks, stop scheduler, stop cognitive loop, save state."""
        self._ready = False
        # Stop plugins
        await self._stop_plugins()
        # Stop cron scheduler
        if hasattr(self, '_cron_scheduler') and self._cron_scheduler:
            self._cron_scheduler.stop()
        # Stop security heartbeat
        if self._security_heartbeat:
            self._security_heartbeat.stop()
        if self.cognitive_loop:
            await self.cognitive_loop.stop()
        if self.scheduler:
            self.scheduler.stop_loop()
        # Stop model lifecycle manager
        if self.model_manager:
            await self.model_manager.stop()
        for task in self._tasks.values():
            if task._task and not task._task.done():
                task._task.cancel()
        # Stop Memory V2
        if self.memory_v2:
            await self.memory_v2.stop()
        # Save persistent state
        self._save_state()

    # ── LLM Calls ──

    async def _call_llm(self, model_id: str, messages: list[dict],
                        tools: list[dict] = None, max_tokens: int = 2048,
                        temperature: float = 0.7,
                        tool_choice: str = None,
                        draft_model: str = None) -> dict:
        """Make a chat completion request via the inference backend."""
        return await self.inference.call_llm(
            model_id, messages,
            tools=tools, max_tokens=max_tokens,
            temperature=temperature, tool_choice=tool_choice,
            draft_model=draft_model,
        )

    async def _call_llm_stream(self, model_id: str, messages: list[dict],
                               max_tokens: int = 2048, temperature: float = 0.7) -> str:
        """Streaming LLM call — yields text chunks via WebSocket, returns full response."""
        async def on_chunk(content: str):
            await self.broadcast({"type": "stream_chunk", "content": content})

        return await self.inference.call_llm_stream(
            model_id, messages,
            max_tokens=max_tokens, temperature=temperature,
            on_chunk=on_chunk,
        )

    async def _execute_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool function by name."""
        fn = self.tool_map.get(name)
        if not fn:
            return f"Error: unknown tool '{name}'"
        try:
            result = fn(**arguments)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result)
        except Exception as e:
            return f"Error executing {name}: {e}"

    def _build_tool_descriptions(self) -> str:
        """Build human-readable tool list for the planner prompt."""
        lines = []
        for fn in self.exec_tools:
            doc = (fn.__doc__ or "").strip().split("\n")[0]
            lines.append(f"- {fn.__name__}: {doc}")
        return "\n".join(lines)

    def get_agent_tool_schemas(self, agent_id: str) -> list[dict]:
        """Get cached tool schemas for a specific agent (lazy-built)."""
        if agent_id not in self._agent_tool_schemas:
            agent_tools = get_tools_for_agent(agent_id)
            self._agent_tool_schemas[agent_id] = _build_tool_schemas(agent_tools)
        return self._agent_tool_schemas[agent_id]

    # ── Memory V2 Integration ──

    async def _process_memory_v2(self, user_message: str, assistant_response: str,
                                  context: dict = None):
        """Process interaction through Memory V2 (learning + storage)."""
        if not self.memory_v2:
            return

        try:
            await self.memory_v2.process_interaction(
                user_msg=user_message,
                assistant_msg=assistant_response,
                session_id=self._current_session_id,
                context=context
            )
        except Exception as e:
            logger.debug("Memory V2 processing failed: %s", e)

    async def get_memory_v2_context(self, query: str) -> dict:
        """Get context from Memory V2 for a query."""
        if not self.memory_v2:
            return {"context": "", "tokens": {"total": 0}}

        try:
            return await self.memory_v2.build_context(
                query,
                session_id=self._current_session_id
            )
        except Exception as e:
            logger.debug("Memory V2 context building failed: %s", e)
            return {"context": "", "tokens": {"total": 0}}

    def get_memory_v2_stats(self) -> dict:
        """Get Memory V2 statistics."""
        if not self.memory_v2:
            return {"enabled": False}

        try:
            stats = self.memory_v2.get_stats()
            stats["enabled"] = True
            return stats
        except Exception:
            return {"enabled": False}

    # ── Model Auto-Download ──

    async def _ensure_model_available(self, model_key: str) -> bool:
        """Check if a model is available. If not, trigger download."""
        if self.available_models.get(model_key):
            return True

        model_id = MODELS.get(model_key)
        if not model_id:
            return False

        logger.info("Model %s (%s) not available — attempting download", model_key, model_id)
        await self.broadcast({
            "type": "agent_event",
            "event": "model_download",
            "model": model_key,
            "model_id": model_id,
        })

        success = await self.inference.download_model(model_id)
        if success:
            self.available_models[model_key] = True
            self.model_states[model_key] = "downloaded"
            logger.info("Model %s downloaded successfully", model_key)
            await self.broadcast({
                "type": "agent_event",
                "event": "model_download_complete",
                "model": model_key,
            })
        else:
            logger.error("Model %s download failed", model_key)

        return success

    # ── Autonomous Background Tasks ──

    async def start_task(self, description: str, plan: list[dict] = None) -> BackgroundTask:
        """Start an autonomous background task via the agent system.
        The system decomposes the objective into subtasks and executes them through the scheduler."""
        if not self.scheduler or not self.registry:
            raise RuntimeError("Agent system not initialized. Cannot start background tasks.")

        task_id = str(uuid.uuid4())[:12]
        bg_task = BackgroundTask(task_id, description, plan or [])
        self._tasks[task_id] = bg_task

        async def _run():
            try:
                bg_task.log("Task started", step="init")
                await self.broadcast({"type": "task_update", "task_id": task_id, "status": "running", "message": "Task started"})

                # Plan via reasoner agent
                reasoner = self.registry.get("reasoner")
                if not plan and reasoner:
                    bg_task.log("Planning task decomposition...", step="planning")
                    plan_result = await reasoner.plan(description)
                    bg_task.plan = plan_result.get("tasks", [])
                    bg_task.log(f"Plan: {plan_result.get('plan_summary', 'N/A')} ({len(bg_task.plan)} subtasks)", step="planning")
                elif not plan:
                    # Fallback: single coder task
                    bg_task.plan = [{"id": "t1", "model": "coder", "task": description, "tools_needed": True, "depends_on": []}]

                # Submit to scheduler
                mission_id = f"bg-{task_id}"
                synthesize = len(bg_task.plan) > 1

                self.scheduler.submit_mission(
                    mission_id, bg_task.plan,
                    synthesize=synthesize,
                    user_message=description,
                )
                self.scheduler.start_loop()

                bg_task.log(f"Submitted mission {mission_id} ({len(bg_task.plan)} tasks)", step="execution")
                await self.broadcast({"type": "task_update", "task_id": task_id, "status": "running",
                                      "message": f"Executing {len(bg_task.plan)} tasks"})

                # Await completion
                mission = await self.scheduler.await_mission(mission_id, timeout=1200)

                if mission.get("error"):
                    bg_task.status = "failed"
                    bg_task.result = f"Mission error: {mission.get('error')}"
                    bg_task.log(f"Task failed: {bg_task.result}", step="error")
                    await self.broadcast({"type": "task_update", "task_id": task_id, "status": "failed", "message": bg_task.result})
                    return

                # Extract final result
                if mission.get("synthesis_result"):
                    final = mission["synthesis_result"]
                elif mission.get("results"):
                    results = list(mission["results"].values())
                    final = "\n\n---\n\n".join(r.get("result", "") for r in results) if len(results) > 1 else results[0].get("result", "No results.")
                else:
                    final = "No results."

                bg_task.result = final
                bg_task.status = "completed"
                bg_task.log("Task completed", step="done")

                # Create briefing
                briefing = {
                    "id": str(uuid.uuid4())[:12],
                    "task_id": task_id,
                    "content": f"**Task completed:** {description}\n\n{final[:2000]}",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "read": False,
                }
                self._briefings.append(briefing)
                # Cap briefings list
                if len(self._briefings) > self._MAX_BRIEFINGS:
                    self._briefings = self._briefings[-self._MAX_BRIEFINGS:]
                await self.broadcast({"type": "briefing", "data": briefing})
                await self.broadcast({"type": "task_update", "task_id": task_id, "status": "completed"})

            except asyncio.CancelledError:
                bg_task.status = "cancelled"
                bg_task.log("Task cancelled", step="cancelled")
            except Exception as e:
                bg_task.status = "failed"
                bg_task.log(f"Task failed: {e}", step="error")
                bg_task.result = f"Error: {e}"
                await self.broadcast({"type": "task_update", "task_id": task_id, "status": "failed", "message": str(e)})
            finally:
                # Release asyncio.Task reference to avoid memory leak
                bg_task._task = None
                self._evict_old_tasks()

        bg_task._task = asyncio.create_task(_run())
        return bg_task

    _MAX_COMPLETED_TASKS = 100
    _MAX_BRIEFINGS = 200

    def _evict_old_tasks(self):
        """Remove oldest completed/failed/cancelled tasks when over capacity."""
        terminal = [tid for tid, t in self._tasks.items() if t.status in ("completed", "failed", "cancelled")]
        if len(terminal) > self._MAX_COMPLETED_TASKS:
            # Sort by updated_at, evict oldest
            terminal.sort(key=lambda tid: self._tasks[tid].updated_at)
            for tid in terminal[:len(terminal) - self._MAX_COMPLETED_TASKS]:
                del self._tasks[tid]

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running background task."""
        task = self._tasks.get(task_id)
        if not task or task.status != "running":
            return False
        task.status = "cancelled"
        if task._task and not task._task.done():
            task._task.cancel()
        return True

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]

    def get_briefings(self, unread_only: bool = False) -> list[dict]:
        if unread_only:
            return [b for b in self._briefings if not b.get("read")]
        return list(self._briefings)

    def mark_briefing_read(self, briefing_id: str) -> bool:
        for b in self._briefings:
            if b["id"] == briefing_id:
                b["read"] = True
                return True
        return False

    # ── Broadcasting ──

    async def broadcast(self, data: dict):
        """Send data to all connected WebSocket clients."""
        dead = []
        for ws in self.ws_clients:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning("[Core] WebSocket broadcast failed, removing client: %s", e)
                dead.append(ws)
        for ws in dead:
            if ws in self.ws_clients:
                self.ws_clients.remove(ws)

    # ── Status ──

    async def get_status(self) -> dict:
        """Return current system status with live model state."""
        models = {}
        try:
            await self.inference.discover_models()
        except Exception:
            pass

        all_model_keys = list(MODELS.keys()) + ["claude"]
        for key in all_model_keys:
            if key == "claude":
                models["claude"] = {
                    "id": "claude-code-cli",
                    "label": "Claude Code",
                    "loaded": True,
                    "state": "loaded",
                }
                continue

            model_id = MODELS.get(key, "unknown")
            state = self.inference.get_model_state(model_id)
            if state == "unknown":
                state = self.model_states.get(key, "missing")

            # Enrich with ModelManager state if available
            tier = "always_loaded" if key in ALWAYS_LOADED_MODELS else "on_demand"
            refs = 0
            if self.model_manager:
                refs = self.model_manager.get_ref_count(key)
                if self.model_manager.is_loaded(key):
                    state = "loaded"

            models[key] = {
                "id": model_id,
                "label": MODEL_LABELS.get(key, key),
                "loaded": state == "loaded",
                "state": state,
                "tier": tier,
                "refs": refs,
            }

        active_tasks = sum(1 for t in self._tasks.values() if t.status == "running")
        unread_briefings = sum(1 for b in self._briefings if not b.get("read"))
        pending_escalations = sum(1 for e in self._pending_escalations.values() if e["status"] == "pending")

        cognitive = None
        if self.cognitive_loop:
            cognitive = self.cognitive_loop.get_status()

        # Memory V2 stats
        memory_v2_stats = self.get_memory_v2_stats()

        # Model lifecycle status
        model_lifecycle = self.model_manager.get_status() if self.model_manager else None

        return {
            "ready": self._ready,
            "models": models,
            "model_lifecycle": model_lifecycle,
            "memory_entries": self.memory.count(),
            "memory_v2": memory_v2_stats,
            "connected_clients": len(self.ws_clients),
            "tools": [fn.__name__ for fn in self.tools],
            "active_tasks": active_tasks,
            "unread_briefings": unread_briefings,
            "pending_escalations": pending_escalations,
            "cognitive_loop": cognitive,
        }
