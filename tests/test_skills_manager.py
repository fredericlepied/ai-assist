"""Tests for skills manager"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_assist.skills_loader import SkillContent, SkillMetadata, SkillsLoader
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


def test_system_prompt_with_script_execution_disabled(skills_manager):
    """Test system prompt without script execution enabled"""
    skills_manager.install_skill("/tmp/test-skills/hello@main")

    # With script execution disabled
    result = skills_manager.get_system_prompt_section(script_execution_enabled=False)
    assert "Agent Skills" in result
    assert "Script Execution" not in result
    assert "internal__execute_skill_script" not in result


def test_system_prompt_with_script_execution_enabled(skills_manager):
    """Test system prompt includes script execution instructions when skill has scripts"""
    # Install skill without scripts
    skills_manager.install_skill("/tmp/test-skills/hello@main")

    # With script execution enabled but no scripts
    result = skills_manager.get_system_prompt_section(script_execution_enabled=True)
    assert "Agent Skills" in result
    # Should NOT have script section since hello has no scripts
    assert "Script Execution" not in result

    # Note: This test verifies that script execution section only appears
    # when skills actually have scripts. See test_script_execution_tools.py
    # for tests with actual scripts.


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


def test_normalize_github_url(skills_manager):
    """Test normalizing GitHub URLs to owner/repo format"""
    # Full HTTPS URL
    source, branch = skills_manager._normalize_github_url("https://github.com/owner/repo")
    assert source == "owner/repo"
    assert branch is None

    # Full HTTPS URL with trailing slash
    source, branch = skills_manager._normalize_github_url("https://github.com/owner/repo/")
    assert source == "owner/repo"
    assert branch is None

    # URL with .git suffix
    source, branch = skills_manager._normalize_github_url("https://github.com/owner/repo.git")
    assert source == "owner/repo"
    assert branch is None

    # URL with /tree/branch/path
    source, branch = skills_manager._normalize_github_url("https://github.com/owner/repo/tree/develop/skills/pdf")
    assert source == "owner/repo/skills/pdf"
    assert branch == "develop"

    # URL with /blob/branch/path
    source, branch = skills_manager._normalize_github_url("https://github.com/owner/repo/blob/main/skills/pdf")
    assert source == "owner/repo/skills/pdf"
    assert branch == "main"

    # URL with /tree/branch but no subpath (top-level)
    source, branch = skills_manager._normalize_github_url("https://github.com/owner/repo/tree/main")
    assert source == "owner/repo"
    assert branch == "main"

    # Already in owner/repo format (no change)
    source, branch = skills_manager._normalize_github_url("owner/repo/skills/pdf")
    assert source == "owner/repo/skills/pdf"
    assert branch is None

    # HTTP URL
    source, branch = skills_manager._normalize_github_url("http://github.com/owner/repo")
    assert source == "owner/repo"
    assert branch is None

    # Top-level repo URL (the main use case)
    source, branch = skills_manager._normalize_github_url(
        "https://github.com/199-biotechnologies/claude-deep-research-skill"
    )
    assert source == "199-biotechnologies/claude-deep-research-skill"
    assert branch is None


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


def _make_clawhub_content(slug="test-skill", version="1.0.0"):
    """Helper: build a SkillContent as if returned by load_skill_from_clawhub"""
    cache_path = f"/tmp/skills-cache/clawhub_{slug}_{version}"
    return SkillContent(
        metadata=SkillMetadata(
            name=slug,
            description="A skill from ClawHub",
            skill_path=Path(cache_path),
            source_type="clawhub",
            source_url="https://clawhub.ai",
        ),
        body="# Test\nClawHub skill body",
    )


def test_install_clawhub_skill(skills_manager):
    """Test installing a skill with clawhub: prefix stores version not branch"""
    content = _make_clawhub_content(version="1.2.3")

    with patch.object(skills_manager.skills_loader, "load_skill_from_clawhub", return_value=content) as mock_load:
        result = skills_manager.install_skill("clawhub:test-skill@1.2.3")

    assert "installed successfully" in result
    assert len(skills_manager.installed_skills) == 1

    skill = skills_manager.installed_skills[0]
    assert skill.source_type == "clawhub"
    assert skill.name == "test-skill"
    assert skill.branch == "1.2.3"

    mock_load.assert_called_once_with("test-skill", "1.2.3")


def test_install_clawhub_skill_default_version(skills_manager):
    """Test that clawhub:slug without @version passes None to loader"""
    content = _make_clawhub_content(version="2.0.0")

    with patch.object(skills_manager.skills_loader, "load_skill_from_clawhub", return_value=content) as mock_load:
        result = skills_manager.install_skill("clawhub:test-skill")

    assert "installed successfully" in result
    mock_load.assert_called_once_with("test-skill", None)
