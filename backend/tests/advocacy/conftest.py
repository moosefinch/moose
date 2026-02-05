"""
Shared fixtures for advocacy tests.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Set up minimal profile
os.environ["PROFILE_PATH"] = str(BACKEND_DIR.parent / "profile.yaml.example")


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Temporary directory for advocacy state files."""
    state_dir = tmp_path / "advocacy"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def goals_path(tmp_state_dir):
    """Path for goals JSON file."""
    return tmp_state_dir / "goals.json"


@pytest.fixture
def patterns_path(tmp_state_dir):
    """Path for patterns JSON file."""
    return tmp_state_dir / "patterns.json"


@pytest.fixture
def friction_path(tmp_state_dir):
    """Path for friction JSON file."""
    return tmp_state_dir / "friction.json"


@pytest.fixture
def onboarding_path(tmp_state_dir):
    """Path for onboarding JSON file."""
    return tmp_state_dir / "onboarding.json"
