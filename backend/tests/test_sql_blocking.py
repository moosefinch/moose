"""
Tests for SQL query blocking — ensures dangerous operations are rejected.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import query_database


class TestSQLBlocking:
    """Test that query_database blocks dangerous SQL operations."""

    def test_select_allowed(self):
        """Basic SELECT should not return an error prefix."""
        result = query_database("SELECT 1")
        # May fail due to no DB, but should not be blocked by keyword filter
        assert "is not allowed" not in result or "SQL error" in result

    def test_insert_blocked(self):
        assert "INSERT" in query_database("SELECT * FROM (INSERT INTO x VALUES (1))")

    def test_update_blocked(self):
        result = query_database("SELECT * FROM x; UPDATE x SET a=1")
        assert "error" in result.lower()

    def test_delete_blocked(self):
        result = query_database("SELECT * FROM x WHERE DELETE")
        assert "DELETE" in result

    def test_drop_blocked(self):
        result = query_database("SELECT * FROM x WHERE DROP")
        assert "DROP" in result

    def test_attach_blocked(self):
        result = query_database("SELECT * FROM x WHERE ATTACH")
        assert "ATTACH" in result

    def test_load_extension_blocked(self):
        result = query_database("SELECT LOAD_EXTENSION('/tmp/evil.so')")
        assert "LOAD_EXTENSION" in result

    def test_savepoint_blocked(self):
        result = query_database("SELECT * FROM x WHERE SAVEPOINT")
        assert "SAVEPOINT" in result

    def test_release_blocked(self):
        result = query_database("SELECT * FROM x WHERE RELEASE")
        assert "RELEASE" in result

    def test_pragma_blocked(self):
        result = query_database("PRAGMA table_info(x)")
        assert "error" in result.lower()

    def test_recursive_cte_blocked(self):
        result = query_database("WITH RECURSIVE cte AS (SELECT 1 UNION ALL SELECT n+1 FROM cte) SELECT * FROM cte")
        assert "error" in result.lower()

    def test_multi_statement_blocked(self):
        result = query_database("SELECT 1; SELECT 2")
        assert "single" in result.lower()

    def test_non_select_blocked(self):
        result = query_database("INSERT INTO x VALUES (1)")
        assert "only select" in result.lower()

    def test_query_too_long(self):
        result = query_database("SELECT " + "x" * 6000)
        assert "too long" in result.lower()

    def test_vacuum_blocked(self):
        result = query_database("SELECT * FROM x WHERE VACUUM")
        assert "VACUUM" in result
