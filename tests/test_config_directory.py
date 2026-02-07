"""Tests for configurable config directory support"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from ai_assist.config import get_config_dir


def test_get_config_dir_default():
    """Test that default config dir is ~/.ai-assist"""
    with patch.dict(os.environ, {}, clear=False):
        # Remove AI_ASSIST_CONFIG_DIR if it exists
        os.environ.pop("AI_ASSIST_CONFIG_DIR", None)
        config_dir = get_config_dir()
        assert config_dir == Path.home() / ".ai-assist"


def test_get_config_dir_from_env_var():
    """Test that config dir can be set via environment variable"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "custom-config"
        with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": str(test_dir)}):
            config_dir = get_config_dir()
            assert config_dir == test_dir


def test_get_config_dir_expands_tilde():
    """Test that ~ is expanded in config dir path"""
    with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": "~/my-ai-assist"}):
        config_dir = get_config_dir()
        assert config_dir == Path.home() / "my-ai-assist"
        assert "~" not in str(config_dir)


def test_get_config_dir_creates_directory():
    """Test that config directory is created if it doesn't exist"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "new-config"
        assert not test_dir.exists()

        with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": str(test_dir)}):
            config_dir = get_config_dir()
            assert config_dir.exists()
            assert config_dir.is_dir()


def test_get_config_dir_override_parameter():
    """Test that override parameter takes precedence over environment"""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_dir = Path(tmpdir) / "env-config"
        override_dir = Path(tmpdir) / "override-config"

        with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": str(env_dir)}):
            config_dir = get_config_dir(override=str(override_dir))
            assert config_dir == override_dir
            assert config_dir.exists()


def test_multiple_instances_different_config_dirs():
    """Test that multiple instances can use different config directories"""
    with tempfile.TemporaryDirectory() as tmpdir:
        instance1_dir = Path(tmpdir) / "instance1"
        instance2_dir = Path(tmpdir) / "instance2"

        # Instance 1
        with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": str(instance1_dir)}):
            config1 = get_config_dir()
            assert config1 == instance1_dir

        # Instance 2
        with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": str(instance2_dir)}):
            config2 = get_config_dir()
            assert config2 == instance2_dir

        # Both should exist and be different
        assert config1.exists()
        assert config2.exists()
        assert config1 != config2
