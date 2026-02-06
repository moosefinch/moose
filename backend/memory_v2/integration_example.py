"""
Integration Example — How to wire Memory V2 into Moose core.

This file shows how to integrate MemoryV2 with the existing AgentCore.
Not meant to be imported directly - copy relevant parts into core.py.
"""

# ============================================================================
# Option 1: Minimal Integration (alongside existing memory)
# ============================================================================

"""
In core.py, add to __init__:
"""

# from memory_v2 import MemoryV2

# class AgentCore:
#     def __init__(self):
#         # ... existing code ...
#
#         # Memory V2 (new)
#         self.memory_v2 = None  # Initialized in start()

"""
In core.py, add to start():
"""

# async def start(self):
#     # ... existing code ...
#
#     # Initialize Memory V2
#     from memory_v2 import MemoryV2
#
#     async def embedder(text: str):
#         """Wrapper for existing embed functionality."""
#         return await self.memory.embed(text)
#
#     async def llm_client(model: str, messages: list, **kwargs):
#         """Wrapper for LLM calls."""
#         model_id = MODELS.get(model, MODELS.get("classifier"))
#         result = await self._call_llm(model_id, messages, **kwargs)
#         return result["choices"][0]["message"].get("content", "")
#
#     self.memory_v2 = MemoryV2(
#         embedder=embedder,
#         llm_client=llm_client,
#         inference_url=API_BASE
#     )
#     await self.memory_v2.start()
#
#     logger.info("Memory V2 initialized")


# ============================================================================
# Option 2: Full Integration (replace old memory)
# ============================================================================

"""
Full integration example - shows the complete picture.
"""


async def example_full_integration():
    """Example of full Memory V2 integration."""

    # This would go in core.py

    from memory_v2 import MemoryV2

    class AgentCoreWithMemoryV2:
        """Example showing Memory V2 integration points."""

        async def start(self):
            # ... other initialization ...

            # Create embedder wrapper
            async def embedder(text: str):
                if not self._api_base or not self._embed_model:
                    raise RuntimeError("Embedder not configured")
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{self._api_base}/v1/embeddings",
                        json={"model": self._embed_model, "input": text},
                    )
                    resp.raise_for_status()
                    return resp.json()["data"][0]["embedding"]

            # Create LLM client wrapper
            async def llm_client(model: str, messages: list, **kwargs):
                model_id = self.MODELS.get(model, self.MODELS.get("classifier"))
                result = await self._call_llm(model_id, messages, **kwargs)
                return result["choices"][0]["message"].get("content", "")

            # Initialize Memory V2
            self.memory_v2 = MemoryV2(
                embedder=embedder,
                llm_client=llm_client,
                inference_url=self._api_base
            )
            await self.memory_v2.start()

        async def chat(self, message: str, history: list = None, ...):
            """Modified chat to use Memory V2."""

            # ... classification code ...

            # Build context using Memory V2
            session_id = self._current_session_id or self.memory_v2.create_session()
            context_result = await self.memory_v2.build_context(
                message,
                session_id=session_id
            )

            # Inject context into system prompt
            system_prompt = f"""You are Moose, a personal AI assistant.

{context_result['context']}

Respond helpfully based on your understanding of the user."""

            # ... rest of chat logic ...

            # After getting response, process the interaction
            await self.memory_v2.process_interaction(
                user_msg=message,
                assistant_msg=response,
                session_id=session_id,
                context={"cwd": self._current_cwd}  # Pass relevant context
            )

            return response

        async def shutdown(self):
            # ... other cleanup ...
            if self.memory_v2:
                await self.memory_v2.stop()


# ============================================================================
# Usage Examples
# ============================================================================

async def usage_examples():
    """Examples of using Memory V2 API."""

    from memory_v2 import MemoryV2

    # Initialize
    memory = MemoryV2()
    await memory.start()

    # --- Context Building ---

    # Build context for a query
    context = await memory.build_context(
        "How do I fix the ROS2 node dropping messages?",
        session_id="session-123"
    )
    print(f"Context tokens: {context['tokens']}")
    print(f"Context: {context['context'][:500]}...")

    # --- Memory Storage ---

    # Store a fact
    await memory.store_fact(
        "User prefers functional programming style",
        entity_type="preference",
        entity_id="code_style",
        domain="engineering"
    )

    # Store a debug solution
    await memory.store_debug_solution(
        symptom="ROS2 messages dropping",
        solution="Changed QoS to RELIABLE",
        root_cause="QoS mismatch between publisher and subscriber",
        domain="robotics",
        project_id="sara-rover"
    )

    # Store a decision
    await memory.store_decision(
        "Using FastAPI instead of Flask for the backend API",
        project_id="moose",
        domain="web"
    )

    # --- Memory Search ---

    # Search by semantic similarity
    results = await memory.search_memory(
        "QoS settings in ROS2",
        top_k=5,
        filters={"domain": "robotics"}
    )
    for r in results:
        print(f"[{r['score']:.2f}] {r['content'][:100]}")

    # --- User Model ---

    # Get user identity
    identity = memory.get_user_identity()
    print(f"User: {identity}")

    # Set preference explicitly
    memory.set_user_preference("code", "indentation", "4 spaces")

    # Get preferences
    prefs = memory.get_user_preferences(domain="code")
    print(f"Code preferences: {prefs}")

    # --- Projects ---

    projects = memory.get_active_projects()
    print(f"Active projects: {projects}")

    # Store project knowledge
    await memory.store_project_knowledge(
        project_id="sara-rover",
        content="Thermal camera uses FLIR Lepton 3.5, connected via SPI",
        knowledge_type="architecture"
    )

    # --- Patterns ---

    # Store observed pattern
    memory.store_pattern(
        pattern_type="debug_approach",
        description="User adds print statements before using debugger",
        confidence=0.6
    )

    patterns = memory.get_patterns(min_confidence=0.5)
    print(f"Patterns: {patterns}")

    # --- System Info ---

    profile = memory.get_system_profile()
    print(f"Running on: {profile['cpu_model']}, {profile['ram_total_gb']}GB RAM")

    budget = memory.get_context_budget()
    print(f"Context budget: {budget['total']} tokens")

    # --- Statistics ---

    stats = memory.get_stats()
    print(f"Stats: {stats}")

    # --- Cleanup ---

    await memory.stop()


# ============================================================================
# Migration Example
# ============================================================================

async def migration_example():
    """Example of running migration from V1 to V2."""

    from memory_v2 import MemoryV2
    from memory_v2.migration import run_migration

    # Initialize Memory V2
    memory = MemoryV2()
    await memory.start()

    # Run migration
    results = await run_migration(
        memory,
        v1_memory_path="backend/memory.jsonl",
        conversations_db_path="backend/conversations.db"
    )

    print(f"Migration results: {results}")

    await memory.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(usage_examples())
