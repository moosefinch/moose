"""
Migration — Migrate from Memory V1 (JSONL) to Memory V2 (SQLite).

Handles:
- Loading existing memory.jsonl entries
- Classifying memory types and domains
- Preserving embeddings
- Maintaining timestamps
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def classify_memory_type(tags: str, content: str) -> str:
    """Classify memory type from V1 tags and content."""
    tags_lower = (tags or "").lower()
    content_lower = (content or "").lower()

    # Check tags first
    if "pattern" in tags_lower:
        return "observation"
    if "reflection" in tags_lower:
        return "observation"
    if "cognitive_loop" in tags_lower:
        return "observation"

    # Check content
    if any(w in content_lower for w in ["decided", "chose", "will use", "going with"]):
        return "decision"
    if any(w in content_lower for w in ["fixed", "solved", "resolved", "error was"]):
        return "outcome"
    if any(w in content_lower for w in ["user:", "assistant:"]):
        return "interaction"
    if any(w in content_lower for w in ["pattern", "noticed", "observed"]):
        return "observation"

    return "fact"


def classify_domain(content: str) -> Optional[str]:
    """Classify domain from content."""
    content_lower = (content or "").lower()

    domain_signals = {
        "engineering": [
            "code", "function", "class", "bug", "error", "debug",
            "compile", "build", "test", "api", "endpoint"
        ],
        "robotics": [
            "ros", "robot", "sensor", "motor", "lidar", "slam",
            "navigation", "actuator", "urdf"
        ],
        "embedded": [
            "arduino", "esp32", "firmware", "gpio", "uart", "spi",
            "microcontroller", "interrupt"
        ],
        "web": [
            "http", "frontend", "backend", "react", "vue", "django",
            "fastapi", "database", "sql"
        ],
        "ml": [
            "model", "training", "neural", "tensor", "pytorch",
            "tensorflow", "dataset"
        ],
        "communication": [
            "email", "message", "draft", "outreach", "marketing"
        ],
    }

    for domain, signals in domain_signals.items():
        if any(signal in content_lower for signal in signals):
            return domain

    return None


def extract_entity_info(content: str, tags: str) -> tuple:
    """Try to extract entity_type and entity_id from content."""
    content_lower = (content or "").lower()

    # Common entity patterns
    patterns = [
        # User works at X
        (r"(?:user |i )(?:work|works) (?:at|for) ([a-z0-9]+)", "employer", None),
        # User's name is X
        (r"(?:user'?s? name is|my name is|i'm|i am) ([a-z]+)", "user_name", None),
        # Project X
        (r"project[: ]+([a-z0-9\-_]+)", "project", None),
        # User prefers X
        (r"(?:user |i )prefer[s]? ([a-z]+)", "preference", None),
    ]

    for pattern, entity_type, default_id in patterns:
        match = re.search(pattern, content_lower)
        if match:
            entity_id = match.group(1) if match.groups() else default_id
            return entity_type, entity_id

    return None, None


async def migrate_v1_to_v2(v1_path: str, memory_v2, batch_size: int = 100):
    """
    Migrate from V1 JSONL to V2 SQLite.

    Args:
        v1_path: Path to memory.jsonl
        memory_v2: MemoryV2 instance
        batch_size: Number of entries to process at once
    """
    v1_path = Path(v1_path)
    if not v1_path.exists():
        logger.info("No V1 memory file found at %s", v1_path)
        return {"migrated": 0, "skipped": 0, "errors": 0}

    # Load V1 memories
    v1_memories = []
    skipped = 0
    with open(v1_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                v1_memories.append(entry)
            except json.JSONDecodeError as e:
                logger.warning("Skipping corrupt entry at line %d: %s", line_num, e)
                skipped += 1

    logger.info("Loaded %d V1 memories (%d skipped)", len(v1_memories), skipped)

    # Check for existing V2 memories to avoid duplicates
    existing_count = memory_v2.memory.count()
    if existing_count > 0:
        logger.info("V2 already has %d memories - checking for duplicates", existing_count)

    migrated = 0
    errors = 0

    for i, mem in enumerate(v1_memories):
        try:
            content = mem.get("text", "")
            if not content:
                continue

            tags = mem.get("tags", "")
            timestamp = mem.get("timestamp", time.time())

            # Classify
            mem_type = classify_memory_type(tags, content)
            domain = classify_domain(content)
            entity_type, entity_id = extract_entity_info(content, tags)

            # Check for duplicate (same content within 1 second)
            # This is a simple check - could be more sophisticated
            existing = memory_v2.db.execute("""
                SELECT id FROM memories
                WHERE content = ? AND ABS(created_at - ?) < 1
            """, (content, timestamp)).fetchone()

            if existing:
                continue

            # Prepare data
            embedding = mem.get("vector")
            if embedding:
                import numpy as np
                embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
            else:
                embedding_blob = None

            # Insert directly (bypass async store for speed)
            memory_v2.db.execute("""
                INSERT INTO memories
                (content, embedding, memory_type, domain, importance,
                 created_at, source, entity_type, entity_id,
                 valid_from, valid_to)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                content,
                embedding_blob,
                mem_type,
                domain,
                0.5,  # Default importance
                timestamp,
                mem.get("source", "internal"),
                entity_type,
                entity_id,
                mem.get("valid_from"),
                mem.get("valid_to"),
            ))

            migrated += 1

            # Commit in batches
            if migrated % batch_size == 0:
                memory_v2.db.commit()
                logger.info("Migrated %d/%d memories", migrated, len(v1_memories))

        except Exception as e:
            logger.warning("Error migrating memory: %s", e)
            errors += 1

    # Final commit
    memory_v2.db.commit()

    result = {
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "total_v1": len(v1_memories),
    }

    logger.info(
        "Migration complete: %d migrated, %d skipped, %d errors",
        migrated, skipped, errors
    )

    return result


async def migrate_conversations_to_sessions(db_path: str, memory_v2):
    """
    Migrate conversation history from conversations.db to sessions.

    This is optional - only needed if you want to preserve conversation history.
    """
    conv_db_path = Path(db_path)
    if not conv_db_path.exists():
        logger.info("No conversations database found")
        return {"sessions": 0, "messages": 0}

    import sqlite3
    conv_db = sqlite3.connect(str(conv_db_path))

    # Check if conversations table exists
    tables = conv_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]

    if "conversations" not in table_names:
        logger.info("No conversations table found")
        conv_db.close()
        return {"sessions": 0, "messages": 0}

    # Get conversations
    conversations = conv_db.execute("""
        SELECT id, created_at, updated_at FROM conversations
        ORDER BY created_at
    """).fetchall()

    sessions_created = 0
    messages_migrated = 0

    for conv_id, created_at, updated_at in conversations:
        # Create session
        session_id = f"migrated-{conv_id}"

        memory_v2.db.execute("""
            INSERT OR IGNORE INTO sessions (id, started_at, ended_at)
            VALUES (?, ?, ?)
        """, (session_id, created_at, updated_at))

        # Get messages
        if "messages" in table_names:
            messages = conv_db.execute("""
                SELECT role, content, created_at FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at
            """, (conv_id,)).fetchall()

            for role, content, msg_time in messages:
                memory_v2.db.execute("""
                    INSERT INTO session_messages
                    (session_id, role, content, timestamp, extracted)
                    VALUES (?, ?, ?, ?, 1)
                """, (session_id, role, content, msg_time))
                messages_migrated += 1

        sessions_created += 1

    memory_v2.db.commit()
    conv_db.close()

    logger.info(
        "Conversation migration: %d sessions, %d messages",
        sessions_created, messages_migrated
    )

    return {"sessions": sessions_created, "messages": messages_migrated}


def backup_v1_memory(v1_path: str) -> Optional[str]:
    """
    Create a backup of V1 memory before migration.

    Returns backup path or None if no backup needed.
    """
    v1_path = Path(v1_path)
    if not v1_path.exists():
        return None

    backup_path = v1_path.with_suffix(".jsonl.backup")
    counter = 1
    while backup_path.exists():
        backup_path = v1_path.with_suffix(f".jsonl.backup.{counter}")
        counter += 1

    import shutil
    shutil.copy(v1_path, backup_path)
    logger.info("Backed up V1 memory to %s", backup_path)

    return str(backup_path)


async def run_migration(memory_v2, v1_memory_path: str = None,
                       conversations_db_path: str = None):
    """
    Run full migration from V1 to V2.

    Args:
        memory_v2: MemoryV2 instance (already initialized)
        v1_memory_path: Path to memory.jsonl (default: backend/memory.jsonl)
        conversations_db_path: Path to conversations.db (optional)
    """
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent

    # Default paths
    if v1_memory_path is None:
        v1_memory_path = backend_dir / "memory.jsonl"
    if conversations_db_path is None:
        conversations_db_path = backend_dir / "conversations.db"

    results = {}

    # Backup V1 memory
    backup = backup_v1_memory(str(v1_memory_path))
    results["backup"] = backup

    # Migrate memories
    memory_result = await migrate_v1_to_v2(str(v1_memory_path), memory_v2)
    results["memories"] = memory_result

    # Migrate conversations (optional)
    if Path(conversations_db_path).exists():
        conv_result = await migrate_conversations_to_sessions(
            str(conversations_db_path), memory_v2
        )
        results["conversations"] = conv_result

    return results
