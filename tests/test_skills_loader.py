"""Tests for skills loader"""

from pathlib import Path

import pytest

from ai_assist.skills_loader import SkillsLoader


def test_load_skill_from_local():
    """Test loading a skill from local directory"""
    loader = SkillsLoader()

    # Load test skill
    skill_path = Path("/tmp/test-skills/hello")
    content = loader.load_skill_from_local(skill_path)

    # Verify metadata
    assert content.metadata.name == "hello"
    assert "greets users" in content.metadata.description
    assert content.metadata.license == "MIT"
    assert content.metadata.source_type == "local"

    # Verify body
    assert "Hello Skill" in content.body
    assert "warmly and enthusiastically" in content.body


def test_invalid_skill_missing_file():
    """Test loading skill with missing SKILL.md"""
    loader = SkillsLoader()

    with pytest.raises(FileNotFoundError):
        loader.load_skill_from_local(Path("/tmp/nonexistent"))


def test_skill_validation():
    """Test skill metadata validation"""
    from ai_assist.skills_loader import SkillMetadata

    # Valid skill
    valid = SkillMetadata(
        name="test-skill",
        description="A test skill",
        skill_path=Path("/tmp/test-skill"),
        source_type="local",
    )
    valid.validate()  # Should not raise

    # Invalid name (too long)
    invalid_long = SkillMetadata(
        name="a" * 65,  # 65 chars
        description="Test",
        skill_path=Path("/tmp/test"),
        source_type="local",
    )
    with pytest.raises(ValueError, match="must be 1-64 characters"):
        invalid_long.validate()

    # Invalid name (uppercase)
    invalid_upper = SkillMetadata(
        name="Test-Skill",  # Has uppercase
        description="Test",
        skill_path=Path("/tmp/test-skill"),
        source_type="local",
    )
    with pytest.raises(ValueError, match="Invalid name format"):
        invalid_upper.validate()

    # Invalid name (consecutive hyphens)
    invalid_hyphens = SkillMetadata(
        name="test--skill",  # Double hyphen
        description="Test",
        skill_path=Path("/tmp/test--skill"),
        source_type="local",
    )
    with pytest.raises(ValueError, match="consecutive hyphens"):
        invalid_hyphens.validate()
