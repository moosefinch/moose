"""
Shared database utilities — consistent SQLite connection management.

All connections use WAL mode for concurrent read access and a 5-second
busy timeout to prevent SQLITE_BUSY errors under async load.
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "gps.db"

# WAL mode is persistent per-database (set once, survives restarts).
# We set it on first connection and cache the flag to avoid redundant PRAGMAs.
_wal_initialized = False


def _configure_connection(conn: sqlite3.Connection):
    """Apply standard connection settings: WAL mode, busy timeout, foreign keys."""
    global _wal_initialized
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    if not _wal_initialized:
        conn.execute("PRAGMA journal_mode = WAL")
        _wal_initialized = True


@contextmanager
def db_connection():
    """Context manager for SQLite connections — ensures close on exit.
    Configures WAL mode and busy timeout automatically."""
    conn = sqlite3.connect(str(DB_PATH))
    _configure_connection(conn)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def db_connection_row():
    """Context manager that returns a connection with Row factory enabled.
    Configures WAL mode and busy timeout automatically."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_readonly_connection() -> sqlite3.Connection:
    """Open a read-only connection (for query_database tool).
    Uses URI mode to enforce read-only at the SQLite level."""
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
