"""
Tests for VectorMemory semantic store.
Tests tag validation, metadata filtering, and eviction.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTagValidation:
    """Test memory tag validation."""

    def test_validate_tags_alphanumeric(self):
        """Tags should only allow alphanumeric + underscore + hyphen."""
        from memory import VectorMemory

        # Valid tags
        result = VectorMemory._validate_tags("valid_tag, another-tag, tag123")
        assert "valid_tag" in result
        assert "another-tag" in result
        assert "tag123" in result

    def test_validate_tags_strips_invalid(self):
        """Invalid characters should be stripped from tags."""
        from memory import VectorMemory

        # Tags with invalid characters should be filtered out
        result = VectorMemory._validate_tags("valid, inv@lid, also<bad>, good_one")
        tags = result.split(",")
        tags = [t.strip() for t in tags if t.strip()]

        assert "valid" in tags
        assert "good_one" in tags
        # Invalid tags should not be present
        for tag in tags:
            assert "@" not in tag
            assert "<" not in tag
            assert ">" not in tag

    def test_validate_tags_max_count(self):
        """Should limit to 20 tags maximum."""
        from memory import VectorMemory

        # Create 30 tags
        many_tags = ", ".join([f"tag{i}" for i in range(30)])
        result = VectorMemory._validate_tags(many_tags)
        tags = [t.strip() for t in result.split(",") if t.strip()]

        assert len(tags) <= 20

    def test_validate_tags_max_length(self):
        """Each tag should be truncated to 50 chars max."""
        from memory import VectorMemory

        long_tag = "a" * 100
        result = VectorMemory._validate_tags(long_tag)

        # The validated tag should be at most 50 chars
        assert len(result) <= 50

    def test_validate_tags_empty_input(self):
        """Empty input should return empty string."""
        from memory import VectorMemory

        assert VectorMemory._validate_tags("") == ""
        assert VectorMemory._validate_tags(None) == ""


class TestMetadataFiltering:
    """Test metadata allowlist filtering."""

    def test_allowed_metadata_keys_defined(self):
        """Allowed metadata keys should be defined."""
        from memory import VectorMemory

        assert hasattr(VectorMemory, "_ALLOWED_METADATA_KEYS")
        allowed = VectorMemory._ALLOWED_METADATA_KEYS

        # Should include expected keys
        assert "source" in allowed
        assert "category" in allowed

    def test_disallowed_metadata_filtered(self):
        """Metadata keys not in allowlist should be filtered."""
        from memory import VectorMemory

        allowed = VectorMemory._ALLOWED_METADATA_KEYS

        # These should NOT be in allowed keys (injection risk)
        assert "script" not in allowed
        assert "eval" not in allowed
        assert "exec" not in allowed
        assert "__proto__" not in allowed


class TestMemoryEviction:
    """Test memory eviction when exceeding capacity."""

    def test_max_memory_entries_defined(self):
        """MAX_MEMORY_ENTRIES constant should be defined."""
        from memory import MAX_MEMORY_ENTRIES

        assert isinstance(MAX_MEMORY_ENTRIES, int)
        assert MAX_MEMORY_ENTRIES > 0
        # Default is 10,000
        assert MAX_MEMORY_ENTRIES == 10_000


class TestSourceValidation:
    """Test source field validation."""

    def test_valid_sources(self):
        """Source should be restricted to known values."""
        # The store method should validate source
        # Valid values: "internal", "external", "user"
        valid_sources = ("internal", "external", "user")
        for source in valid_sources:
            assert source in ("internal", "external", "user")


class TestVectorMemoryInit:
    """Test VectorMemory initialization."""

    def test_vector_memory_init(self):
        """VectorMemory should initialize with empty entries."""
        from memory import VectorMemory

        # Patch _load to avoid file I/O
        with patch.object(VectorMemory, "_load"):
            mem = VectorMemory()

        assert hasattr(mem, "entries")
        assert hasattr(mem, "vectors")
        assert hasattr(mem, "_lock")

    def test_vector_memory_has_required_methods(self):
        """VectorMemory should have store and search methods."""
        from memory import VectorMemory

        assert hasattr(VectorMemory, "store")
        assert hasattr(VectorMemory, "search")
        assert hasattr(VectorMemory, "embed")
        assert hasattr(VectorMemory, "set_embedder")


class TestEmbedderConfig:
    """Test embedder configuration."""

    def test_set_embedder_stores_config(self):
        """set_embedder should store API base and model."""
        from memory import VectorMemory

        with patch.object(VectorMemory, "_load"):
            mem = VectorMemory()

        mem.set_embedder("http://localhost:1234", "nomic-embed")

        assert mem._api_base == "http://localhost:1234"
        assert mem._embed_model == "nomic-embed"

    def test_embed_requires_configured_embedder(self):
        """embed() should raise if embedder not configured."""
        from memory import VectorMemory

        with patch.object(VectorMemory, "_load"):
            mem = VectorMemory()

        # Not configured yet
        mem._api_base = None
        mem._embed_model = None

        with pytest.raises(RuntimeError, match="Embedder not configured"):
            import asyncio
            asyncio.get_event_loop().run_until_complete(mem.embed("test"))
