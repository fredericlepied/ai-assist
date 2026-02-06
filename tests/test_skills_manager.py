"""Tests for skills manager"""

import json

import pytest

from ai_assist.skills_loader import SkillsLoader
from ai_assist.skills_manager import SkillsManager


@pytest.fixture
def temp_installed_skills_file(tmp_path):
    """Create temporary installed-skills.json file"""
    installed_file = tmp_path / "installed-skills.json"
    return installed_file


@pytest.fixture
def skills_manager(temp_installed_skills_file):
    """Create SkillsManager with temporary file"""
    loader = SkillsLoader()
    manager = SkillsManager(loader)
    manager.installed_skills_file = temp_installed_skills_file
    return manager


def test_install_local_skill(skills_manager):
    """Test installing a skill from local path"""
    result = skills_manager.install_skill("/tmp/test-skills/hello@main")

    assert "installed successfully" in result
    assert len(skills_manager.installed_skills) == 1
    assert "hello" in skills_manager.loaded_skills

    skill = skills_manager.installed_skills[0]
    assert skill.name == "hello"
    assert skill.source_type == "local"
    assert skill.branch == "main"


def test_uninstall_skill(skills_manager):
    """Test uninstalling a skill"""
    # Install first
    skills_manager.install_skill("/tmp/test-skills/hello@main")
    assert len(skills_manager.installed_skills) == 1

    # Uninstall
    result = skills_manager.uninstall_skill("hello")
    assert "uninstalled successfully" in result
    assert len(skills_manager.installed_skills) == 0
    assert "hello" not in skills_manager.loaded_skills


def test_list_installed(skills_manager):
    """Test listing installed skills"""
    # No skills
    result = skills_manager.list_installed()
    assert "No skills installed" in result

    # Install skill
    skills_manager.install_skill("/tmp/test-skills/hello@main")

    # List again
    result = skills_manager.list_installed()
    assert "hello" in result
    assert "greets users" in result


def test_system_prompt_section(skills_manager):
    """Test generating system prompt section"""
    # No skills
    result = skills_manager.get_system_prompt_section()
    assert result == ""

    # Install skill
    skills_manager.install_skill("/tmp/test-skills/hello@main")

    # Generate prompt
    result = skills_manager.get_system_prompt_section()
    assert "Agent Skills" in result
    assert "hello" in result
    assert "Hello Skill" in result


def test_parse_source_spec(skills_manager):
    """Test parsing source specifications"""
    # With branch
    source, branch = skills_manager._parse_source_spec("anthropics/skills/skills/pdf@main")
    assert source == "anthropics/skills/skills/pdf"
    assert branch == "main"

    # Without branch (default to main)
    source, branch = skills_manager._parse_source_spec("/path/to/skill")
    assert source == "/path/to/skill"
    assert branch == "main"


def test_persistence(skills_manager, temp_installed_skills_file):
    """Test that skills are persisted to JSON"""
    # Install skill
    skills_manager.install_skill("/tmp/test-skills/hello@main")

    # Check JSON file was created
    assert temp_installed_skills_file.exists()

    # Read and verify
    with open(temp_installed_skills_file) as f:
        data = json.load(f)

    assert len(data["skills"]) == 1
    assert data["skills"][0]["name"] == "hello"

    # Create new manager and load
    loader = SkillsLoader()
    new_manager = SkillsManager(loader)
    new_manager.installed_skills_file = temp_installed_skills_file
    new_manager.load_installed_skills()

    assert len(new_manager.installed_skills) == 1
    assert new_manager.installed_skills[0].name == "hello"
