#!/usr/bin/env python3
"""
Quick test script for Memory V2.

Run with: python -m memory_v2.test_memory_v2
Or: pytest memory_v2/test_memory_v2.py -v
"""

import asyncio
import tempfile
import os
from pathlib import Path


async def test_system_awareness():
    """Test system awareness detection."""
    print("\n=== Testing System Awareness ===")

    import sqlite3
    from memory_v2.system_awareness import SystemAwareness

    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = sqlite3.connect(db_path)

        # Create tables
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            db.executescript(schema_path.read_text())
            db.commit()

        # Test
        system = SystemAwareness(db)
        profile = system.detect_hardware()

        print(f"  Hostname: {profile.get('hostname')}")
        print(f"  OS: {profile.get('os_type')} {profile.get('os_version')}")
        print(f"  CPU: {profile.get('cpu_model')}")
        print(f"  Cores: {profile.get('cpu_cores')} ({profile.get('cpu_threads')} threads)")
        print(f"  RAM: {profile.get('ram_total_gb')} GB")
        print(f"  GPU: {profile.get('gpu_model') or 'None'}")
        print(f"  Metal: {profile.get('has_metal')}")
        print(f"  Neural Engine: {profile.get('has_neural_engine')}")
        print(f"  Max model size: {profile.get('max_model_size_gb')} GB")
        print(f"  Context budget: {profile.get('recommended_context_tokens')} tokens")

        # Test adaptive budget
        budget = system.get_adaptive_context_budget()
        print(f"\n  Adaptive budget: {budget}")

        db.close()
        print("  ✓ System awareness test passed")

    finally:
        os.unlink(db_path)


async def test_user_model():
    """Test user model learning."""
    print("\n=== Testing User Model ===")

    import sqlite3
    from memory_v2.user_model import UserModel

    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = sqlite3.connect(db_path)

        # Create tables
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            db.executescript(schema_path.read_text())
            db.commit()

        # Test
        model = UserModel(db)

        # Test identity extraction
        await model.learn_from_interaction(
            "Hi, my name is Finch and I'm a robotics engineer",
            "Hello Finch! Nice to meet you.",
            context={}
        )

        identity = model.get_identity()
        print(f"  Identity: {identity}")

        # Test project detection
        await model.learn_from_interaction(
            "I'm working on /Users/finch/projects/sara-rover today",
            "I can help with your SARA rover project.",
            context={"cwd": "/Users/finch/projects/sara-rover"}
        )

        projects = model.get_active_projects()
        print(f"  Projects: {projects}")

        # Test preferences
        model.set_preference("code", "style", "functional")
        prefs = model.get_preferences()
        print(f"  Preferences: {prefs}")

        # Test core context
        context = model.get_core_context()
        print(f"  Core context length: {len(context)} chars")

        db.close()
        print("  ✓ User model test passed")

    finally:
        os.unlink(db_path)


async def test_episodic_memory():
    """Test episodic memory storage and search."""
    print("\n=== Testing Episodic Memory ===")

    import sqlite3
    from memory_v2.episodic import EpisodicMemory

    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = sqlite3.connect(db_path)

        # Create tables
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            db.executescript(schema_path.read_text())
            db.commit()

        # Mock embedder (returns random vectors for testing)
        import random
        async def mock_embedder(text: str):
            # Deterministic based on text hash for reproducibility
            random.seed(hash(text) % 2**32)
            return [random.random() for _ in range(768)]

        # Test
        memory = EpisodicMemory(db, mock_embedder)

        # Store memories
        id1 = await memory.store(
            content="User prefers functional programming style",
            memory_type="fact",
            domain="engineering"
        )
        print(f"  Stored memory {id1}")

        id2 = await memory.store(
            content="Fixed ROS2 QoS mismatch issue by setting RELIABLE policy",
            memory_type="outcome",
            domain="robotics"
        )
        print(f"  Stored memory {id2}")

        id3 = await memory.store(
            content="User works at Anthropic",
            memory_type="fact",
            entity_type="employer",
            entity_id="current"
        )
        print(f"  Stored memory {id3}")

        # Test supersession
        id4 = await memory.store(
            content="User works at OpenAI",
            memory_type="fact",
            entity_type="employer",
            entity_id="current"
        )
        print(f"  Stored memory {id4} (should supersede {id3})")

        # Check supersession
        mem3 = memory.get_memory(id3)
        print(f"  Memory {id3} superseded_by: {mem3['superseded_by']}")

        # Count
        count = memory.count()
        print(f"  Active memories: {count}")

        # Search
        results = await memory.search("functional programming code style", top_k=3)
        print(f"  Search results: {len(results)} found")
        for r in results:
            print(f"    [{r['score']:.3f}] {r['content'][:50]}...")

        # Stats
        stats = memory.stats()
        print(f"  Stats: {stats}")

        db.close()
        print("  ✓ Episodic memory test passed")

    finally:
        os.unlink(db_path)


async def test_memory_v2_full():
    """Test full Memory V2 system."""
    print("\n=== Testing Full Memory V2 ===")

    from memory_v2.core import MemoryV2

    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Mock embedder
        import random
        async def mock_embedder(text: str):
            random.seed(hash(text) % 2**32)
            return [random.random() for _ in range(768)]

        # Mock LLM client
        async def mock_llm(model: str, messages: list, **kwargs):
            return "Mock LLM response"

        # Initialize
        memory = MemoryV2(
            db_path=db_path,
            embedder=mock_embedder,
            llm_client=mock_llm
        )
        await memory.start()

        # Test system profile
        profile = memory.get_system_profile()
        print(f"  System: {profile.get('cpu_model', 'Unknown')[:30]}")

        # Test session
        session_id = memory.create_session()
        print(f"  Created session: {session_id}")

        # Test interaction processing
        await memory.process_interaction(
            user_msg="How do I fix ROS2 message drops?",
            assistant_msg="You can try adjusting the QoS settings...",
            session_id=session_id
        )
        print("  Processed interaction")

        # Test context building
        context = await memory.build_context(
            "What was that ROS2 fix again?",
            session_id=session_id
        )
        print(f"  Built context: {context['tokens']['total']} tokens")

        # Test memory storage
        mem_id = await memory.store_fact(
            "QoS RELIABLE policy prevents message drops",
            domain="robotics"
        )
        print(f"  Stored fact: {mem_id}")

        # Test debug solution
        await memory.store_debug_solution(
            symptom="ROS2 messages dropping",
            solution="Set QoS to RELIABLE",
            root_cause="QoS mismatch",
            domain="robotics"
        )
        print("  Stored debug solution")

        # Test stats
        stats = memory.get_stats()
        print(f"  Stats: {stats['memory']['active']} memories, {stats['user']['preferences_count']} prefs")

        # Cleanup
        await memory.stop()
        print("  ✓ Full Memory V2 test passed")

    finally:
        os.unlink(db_path)


async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Memory V2 Test Suite")
    print("=" * 60)

    try:
        await test_system_awareness()
        await test_user_model()
        await test_episodic_memory()
        await test_memory_v2_full()

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(run_all_tests()))
