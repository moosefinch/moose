"""
Test fixtures for the Moose security test suite.
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Set up a minimal profile before importing anything that reads config
os.environ["PROFILE_PATH"] = str(BACKEND_DIR.parent / "profile.yaml.example")


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS rate_limits (
        ip TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        timestamp REAL NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_ip ON rate_limits(ip, endpoint)")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        key_hash TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        expires_at REAL,
        active INTEGER DEFAULT 1
    )""")
    conn.commit()
    yield db_path, conn
    conn.close()
    os.unlink(db_path)


@pytest.fixture
def mock_profile():
    """Create a mock profile for testing."""
    profile = MagicMock()
    profile.system.name = "TestSystem"
    profile.owner.name = "TestOwner"
    profile.web.cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    profile.smtp.enabled = False
    profile.plugins.crm.enabled = False
    return profile
