"""
Tests for rate limiting persistence across simulated restarts.
"""

import sqlite3
import time

import pytest


class TestRateLimiting:
    """Test DB-backed rate limiting."""

    def test_rate_limit_persists(self, temp_db):
        """Rate limits should persist in the database."""
        db_path, conn = temp_db
        now = time.time()

        # Simulate 5 requests from same IP
        for i in range(5):
            conn.execute("INSERT INTO rate_limits (ip, endpoint, timestamp) VALUES (?, 'lead', ?)",
                         ("192.168.1.1", now + i))
        conn.commit()

        # Check count
        count = conn.execute(
            "SELECT COUNT(*) FROM rate_limits WHERE ip = ? AND endpoint = 'lead' AND timestamp > ?",
            ("192.168.1.1", now - 3600)).fetchone()[0]
        assert count == 5

    def test_stale_entries_cleaned(self, temp_db):
        """Old entries beyond the window should be cleanable."""
        db_path, conn = temp_db
        old_time = time.time() - 7200  # 2 hours ago
        now = time.time()

        conn.execute("INSERT INTO rate_limits (ip, endpoint, timestamp) VALUES (?, 'lead', ?)",
                     ("192.168.1.1", old_time))
        conn.execute("INSERT INTO rate_limits (ip, endpoint, timestamp) VALUES (?, 'lead', ?)",
                     ("192.168.1.1", now))
        conn.commit()

        # Clean stale
        cutoff = now - 3600
        conn.execute("DELETE FROM rate_limits WHERE timestamp < ?", (cutoff,))
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM rate_limits WHERE ip = ?",
                             ("192.168.1.1",)).fetchone()[0]
        assert count == 1

    def test_different_ips_independent(self, temp_db):
        """Different IPs should have independent rate limits."""
        db_path, conn = temp_db
        now = time.time()

        for i in range(5):
            conn.execute("INSERT INTO rate_limits (ip, endpoint, timestamp) VALUES (?, 'lead', ?)",
                         ("10.0.0.1", now + i))
        conn.execute("INSERT INTO rate_limits (ip, endpoint, timestamp) VALUES (?, 'lead', ?)",
                     ("10.0.0.2", now))
        conn.commit()

        count_1 = conn.execute(
            "SELECT COUNT(*) FROM rate_limits WHERE ip = '10.0.0.1' AND endpoint = 'lead'").fetchone()[0]
        count_2 = conn.execute(
            "SELECT COUNT(*) FROM rate_limits WHERE ip = '10.0.0.2' AND endpoint = 'lead'").fetchone()[0]
        assert count_1 == 5
        assert count_2 == 1
