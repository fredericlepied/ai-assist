"""Pytest configuration and fixtures"""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def isolate_config_dir(tmp_path):
    """Prevent tests from writing to ~/.ai-assist by redirecting get_config_dir() to a temp directory."""
    test_config_dir = tmp_path / ".ai-assist"
    test_config_dir.mkdir(exist_ok=True)
    with patch("ai_assist.config.get_config_dir", return_value=test_config_dir):
        yield test_config_dir


@pytest.fixture(scope="session", autouse=True)
def preload_embedding_model():
    """Preload the embedding model once per worker so individual tests don't pay the cost."""
    from ai_assist.embedding import EmbeddingModel

    EmbeddingModel.get()._load()


@pytest.fixture(scope="session", autouse=True)
def setup_skill_test_fixtures():
    """Create test skill fixtures for skills tests"""
    test_skills_dir = Path("/tmp/test-skills/hello")
    test_skills_dir.mkdir(parents=True, exist_ok=True)

    # Create SKILL.md for hello skill
    skill_md = test_skills_dir / "SKILL.md"
    skill_md.write_text("""---
name: hello
description: A test skill that greets users
license: MIT
---

# Hello Skill

This is a test skill for testing the skills system.

## Instructions

When greeting users, be warmly and enthusiastically welcoming.

## Examples

**User**: Hello!
**Assistant**: Hello! How can I help you today?
""")

    yield

    # Cleanup (optional - /tmp cleans itself)
