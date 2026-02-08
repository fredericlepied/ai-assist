"""Pytest configuration and fixtures"""

from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_skill_test_fixtures():
    """Create test skill fixtures for skills tests"""
    test_skills_dir = Path("/tmp/test-skills/hello")
    test_skills_dir.mkdir(parents=True, exist_ok=True)

    # Create SKILL.md for hello skill
    skill_md = test_skills_dir / "SKILL.md"
    skill_md.write_text(
        """---
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
"""
    )

    yield

    # Cleanup (optional - /tmp cleans itself)
