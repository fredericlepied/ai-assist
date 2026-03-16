"""Tests for systemd user service management"""

import os
from pathlib import Path
from unittest.mock import patch

from ai_assist.service import (
    SUBCOMMANDS,
    _resolve_config_dir,
    _resolve_reports_dir,
    _service_content,
    _service_file,
    _service_name,
    install_service,
    remove_service,
    service_logs,
    service_status,
    service_systemctl,
)


class TestServiceName:
    def test_dotfile_strips_leading_dot(self):
        assert _service_name(Path("/home/user/.ai-assist")) == "ai-assist"

    def test_dotfile_iris(self):
        assert _service_name(Path("/home/user/.iris")) == "iris"

    def test_no_leading_dot(self):
        assert _service_name(Path("/tmp/test")) == "test"


class TestServiceFile:
    def test_service_file_path(self):
        config_dir = Path("/home/user/.ai-assist")
        result = _service_file(config_dir)
        assert result == Path.home() / ".config" / "systemd" / "user" / "ai-assist.service"

    def test_service_file_iris(self):
        config_dir = Path("/home/user/.iris")
        result = _service_file(config_dir)
        assert result == Path.home() / ".config" / "systemd" / "user" / "iris.service"


class TestResolveConfigDir:
    def test_explicit_arg_takes_priority(self, tmp_path):
        with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": "/from/env"}):
            result = _resolve_config_dir(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_env_var_fallback(self, tmp_path):
        with patch.dict(os.environ, {"AI_ASSIST_CONFIG_DIR": str(tmp_path)}):
            result = _resolve_config_dir(None)
        assert result == tmp_path.resolve()

    def test_default_fallback(self):
        env = {k: v for k, v in os.environ.items() if k != "AI_ASSIST_CONFIG_DIR"}
        with patch.dict(os.environ, env, clear=True):
            result = _resolve_config_dir(None)
        assert result == (Path.home() / ".ai-assist").resolve()

    def test_tilde_expansion(self):
        result = _resolve_config_dir("~/.ai-assist")
        assert result == (Path.home() / ".ai-assist").resolve()


class TestResolveReportsDir:
    def test_explicit_arg(self, tmp_path):
        result = _resolve_reports_dir(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_env_var_fallback(self, tmp_path):
        with patch.dict(os.environ, {"AI_ASSIST_REPORTS_DIR": str(tmp_path)}):
            result = _resolve_reports_dir(None)
        assert result == tmp_path.resolve()

    def test_none_when_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "AI_ASSIST_REPORTS_DIR"}
        with patch.dict(os.environ, env, clear=True):
            result = _resolve_reports_dir(None)
        assert result is None


class TestInstallService:
    def test_writes_service_file_and_enables(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        with patch("ai_assist.service.subprocess.run"), patch("ai_assist.service.sys.argv", ["/usr/bin/ai-assist"]):
            install_service(str(config_dir), None)
        service_file = Path.home() / ".config" / "systemd" / "user" / "ai-assist.service"
        assert service_file.exists()
        assert "ExecStart=/usr/bin/ai-assist /monitor" in service_file.read_text()
        service_file.unlink()

    def test_includes_reports_dir_when_provided(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        reports_dir = tmp_path / "reports"
        with patch("ai_assist.service.subprocess.run"), patch("ai_assist.service.sys.argv", ["/usr/bin/ai-assist"]):
            install_service(str(config_dir), str(reports_dir))
        service_file = Path.home() / ".config" / "systemd" / "user" / "ai-assist.service"
        content = service_file.read_text()
        assert f"AI_ASSIST_REPORTS_DIR={reports_dir.resolve()}" in content
        service_file.unlink()


class TestRemoveService:
    def test_removes_service_file(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        service_file = Path.home() / ".config" / "systemd" / "user" / "ai-assist.service"
        service_file.parent.mkdir(parents=True, exist_ok=True)
        service_file.write_text("[Unit]\n")
        with patch("ai_assist.service.subprocess.run"):
            remove_service(str(config_dir))
        assert not service_file.exists()

    def test_remove_succeeds_without_service_file(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        with patch("ai_assist.service.subprocess.run"):
            remove_service(str(config_dir))  # should not raise


class TestSubcommands:
    def test_expected_subcommands_present(self):
        assert SUBCOMMANDS >= {"install", "remove", "start", "stop", "restart", "enable", "disable", "status", "logs"}


class TestServiceSystemctl:
    def test_delegates_action_to_systemctl(self, tmp_path):
        with patch("ai_assist.service.subprocess.run") as mock_run:
            service_systemctl("restart", str(tmp_path))
        mock_run.assert_called_once_with(["systemctl", "--user", "restart", tmp_path.name], check=True)

    def test_uses_service_name_from_config_dir(self, tmp_path):
        dotdir = tmp_path / ".iris"
        dotdir.mkdir()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            service_systemctl("stop", str(dotdir))
        mock_run.assert_called_once_with(["systemctl", "--user", "stop", "iris"], check=True)


class TestServiceStatus:
    def test_calls_systemctl_status(self, tmp_path):
        with patch("ai_assist.service.subprocess.run") as mock_run:
            service_status(str(tmp_path))
        mock_run.assert_called_once_with(["systemctl", "--user", "status", tmp_path.name], check=False)


class TestServiceLogs:
    def test_calls_journalctl_no_extra_args(self, tmp_path):
        with patch("ai_assist.service.subprocess.run") as mock_run:
            service_logs(str(tmp_path))
        mock_run.assert_called_once_with(["journalctl", "--user", "-u", tmp_path.name], check=False)

    def test_passes_extra_args(self, tmp_path):
        with patch("ai_assist.service.subprocess.run") as mock_run:
            service_logs(str(tmp_path), ["-f"])
        mock_run.assert_called_once_with(["journalctl", "--user", "-u", tmp_path.name, "-f"], check=False)


class TestServiceContent:
    def test_contains_config_dir(self, tmp_path):
        content = _service_content(tmp_path, None, "/usr/bin/ai-assist")
        assert str(tmp_path) in content

    def test_contains_exec_start_with_binary(self, tmp_path):
        content = _service_content(tmp_path, None, "/home/user/.local/bin/ai-assist")
        assert "ExecStart=/home/user/.local/bin/ai-assist /monitor" in content

    def test_contains_restart_policy(self, tmp_path):
        content = _service_content(tmp_path, None, "/usr/bin/ai-assist")
        assert "Restart=on-failure" in content

    def test_reports_dir_included_when_set(self, tmp_path):
        reports = tmp_path / "reports"
        content = _service_content(tmp_path, reports, "/usr/bin/ai-assist")
        assert f"AI_ASSIST_REPORTS_DIR={reports}" in content

    def test_reports_dir_absent_when_none(self, tmp_path):
        content = _service_content(tmp_path, None, "/usr/bin/ai-assist")
        assert "AI_ASSIST_REPORTS_DIR" not in content

    def test_network_dependency(self, tmp_path):
        content = _service_content(tmp_path, None, "/usr/bin/ai-assist")
        assert "After=network-online.target" in content
