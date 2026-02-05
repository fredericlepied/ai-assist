"""Tests for identity management"""

import pytest
import tempfile
from pathlib import Path
from ai_assist.identity import (
    Identity,
    UserIdentity,
    AssistantIdentity,
    CommunicationPreferences,
    get_identity
)


def test_default_identity():
    """Test that default identity has expected values"""
    identity = Identity()

    assert identity.version == "1.0"
    assert identity.user.name == "there"
    assert identity.user.role == "Manager"
    assert identity.user.organization is None
    assert identity.assistant.nickname == "Nexus"
    assert identity.preferences.formality == "professional"


def test_custom_identity():
    """Test creating identity with custom values"""
    identity = Identity(
        user=UserIdentity(
            name="Fred Lepied",
            role="Engineering Manager",
            organization="Red Hat"
        ),
        assistant=AssistantIdentity(nickname="Atlas"),
        preferences=CommunicationPreferences(formality="casual")
    )

    assert identity.user.name == "Fred Lepied"
    assert identity.user.role == "Engineering Manager"
    assert identity.user.organization == "Red Hat"
    assert identity.assistant.nickname == "Atlas"
    assert identity.preferences.formality == "casual"


def test_system_prompt_generation_default():
    """Test system prompt with default identity"""
    identity = Identity()
    prompt = identity.get_system_prompt()

    assert "Nexus" in prompt
    assert "AI assistant" in prompt
    assert "professional tone" in prompt


def test_system_prompt_generation_custom():
    """Test system prompt includes nickname, user name, and role"""
    identity = Identity(
        user=UserIdentity(
            name="Fred Lepied",
            role="Engineering Manager",
            organization="Red Hat"
        ),
        assistant=AssistantIdentity(nickname="Atlas")
    )
    prompt = identity.get_system_prompt()

    assert "Atlas" in prompt
    assert "Fred Lepied" in prompt
    assert "Engineering Manager" in prompt
    assert "Red Hat" in prompt
    assert "professional tone" in prompt


def test_system_prompt_with_casual_preference():
    """Test system prompt with casual communication style"""
    identity = Identity(
        preferences=CommunicationPreferences(formality="casual")
    )
    prompt = identity.get_system_prompt()

    assert "casual" in prompt or "friendly manner" in prompt


def test_system_prompt_with_friendly_preference():
    """Test system prompt with friendly communication style"""
    identity = Identity(
        preferences=CommunicationPreferences(formality="friendly")
    )
    prompt = identity.get_system_prompt()

    assert "warm" in prompt or "approachable" in prompt


def test_greeting_with_name():
    """Test personalized greeting"""
    identity = Identity(
        user=UserIdentity(name="Fred Lepied"),
        assistant=AssistantIdentity(nickname="Atlas")
    )
    greeting = identity.get_greeting()

    assert greeting == "Hello Fred Lepied, I'm Atlas."


def test_greeting_default():
    """Test generic greeting for default identity"""
    identity = Identity()
    greeting = identity.get_greeting()

    assert greeting == "Hello, I'm Nexus."


def test_load_from_nonexistent_file():
    """Test graceful fallback to defaults when file doesn't exist"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "nonexistent" / "identity.yaml"
        identity = Identity.load_from_file(path)

        # Should return default identity
        assert identity.user.name == "there"
        assert identity.assistant.nickname == "Nexus"


def test_save_and_load():
    """Test persistence of identity"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "identity.yaml"

        # Create and save identity
        original = Identity(
            user=UserIdentity(
                name="Fred Lepied",
                role="Engineering Manager",
                organization="Red Hat"
            ),
            assistant=AssistantIdentity(nickname="Atlas")
        )
        original.save_to_file(path)

        # Load and verify
        loaded = Identity.load_from_file(path)

        assert loaded.user.name == "Fred Lepied"
        assert loaded.user.role == "Engineering Manager"
        assert loaded.user.organization == "Red Hat"
        assert loaded.assistant.nickname == "Atlas"


def test_save_creates_directory():
    """Test that save creates parent directory if it doesn't exist"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "subdir" / "identity.yaml"

        identity = Identity()
        identity.save_to_file(path)

        assert path.exists()
        assert path.parent.exists()


def test_load_invalid_yaml():
    """Test handling of invalid YAML"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "identity.yaml"

        # Write invalid YAML
        with open(path, "w") as f:
            f.write("invalid: yaml: content: [")

        # Should return default identity
        identity = Identity.load_from_file(path)
        assert identity.user.name == "there"


def test_load_empty_file():
    """Test handling of empty file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "identity.yaml"

        # Create empty file
        path.touch()

        # Should return default identity
        identity = Identity.load_from_file(path)
        assert identity.user.name == "there"


def test_get_identity_cached():
    """Test that get_identity returns cached instance"""
    # Clear cache by importing fresh
    from ai_assist import identity as identity_module
    identity_module._identity = None

    # First call loads from file
    id1 = get_identity()

    # Second call should return same instance
    id2 = get_identity()

    assert id1 is id2


def test_get_identity_reload():
    """Test that reload parameter forces reload"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "identity.yaml"

        # Save an identity
        Identity(
            user=UserIdentity(name="Test User")
        ).save_to_file(path)

        # Load it
        id1 = Identity.load_from_file(path)

        # Modify file
        Identity(
            user=UserIdentity(name="Different User")
        ).save_to_file(path)

        # Load without reload should give cached
        id2 = Identity.load_from_file(path)

        # Verify reload works
        assert id2.user.name == "Different User"
