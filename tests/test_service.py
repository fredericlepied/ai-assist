"""Tests for cross-platform service management"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_assist.service import (
    SUBCOMMANDS,
    LinuxSystemdBackend,
    MacOSLaunchdBackend,
    _get_backend,
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

# =============================================================================
# Common Utility Tests (Platform-agnostic)
# =============================================================================


class TestServiceName:
    def test_dotfile_strips_leading_dot(self):
        assert _service_name(Path("/home/user/.ai-assist")) == "ai-assist"

    def test_dotfile_iris(self):
        assert _service_name(Path("/home/user/.iris")) == "iris"

    def test_no_leading_dot(self):
        assert _service_name(Path("/tmp/test")) == "test"


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


class TestSubcommands:
    def test_expected_subcommands_present(self):
        assert SUBCOMMANDS >= {"install", "remove", "start", "stop", "restart", "enable", "disable", "status", "logs"}


# =============================================================================
# Backend Factory Tests
# =============================================================================


class TestBackendFactory:
    def test_linux_backend_selected(self):
        with patch("ai_assist.service.platform.system", return_value="Linux"):
            # Clear cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            backend = _get_backend()
        assert isinstance(backend, LinuxSystemdBackend)

    def test_macos_backend_selected(self):
        with patch("ai_assist.service.platform.system", return_value="Darwin"):
            # Clear cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            backend = _get_backend()
        assert isinstance(backend, MacOSLaunchdBackend)

    def test_unsupported_platform_raises(self):
        with patch("ai_assist.service.platform.system", return_value="Windows"):
            # Clear cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            with pytest.raises(RuntimeError, match="not supported"):
                _get_backend()


# =============================================================================
# Cross-Platform Backend Tests
# =============================================================================


@pytest.mark.parametrize(
    "platform_name,backend_class,service_path",
    [
        ("Linux", LinuxSystemdBackend, ".config/systemd/user/ai-assist.service"),
        ("Darwin", MacOSLaunchdBackend, "Library/LaunchAgents/ai-assist.plist"),
    ],
)
class TestServiceFilePath:
    def test_service_file_path(self, platform_name, backend_class, service_path):
        config_dir = Path("/home/user/.ai-assist")
        backend = backend_class()
        result = backend.service_file_path(config_dir)
        assert str(result).endswith(service_path)
        assert result.name == service_path.split("/")[-1]


@pytest.mark.parametrize(
    "platform_name,backend_class", [("Linux", LinuxSystemdBackend), ("Darwin", MacOSLaunchdBackend)]
)
class TestServiceContent:
    def test_contains_config_dir(self, platform_name, backend_class, tmp_path):
        backend = backend_class()
        content = backend.service_content(tmp_path, None, "/usr/bin/ai-assist", "ai-assist")
        assert str(tmp_path) in content

    def test_contains_monitor_command(self, platform_name, backend_class, tmp_path):
        backend = backend_class()
        content = backend.service_content(tmp_path, None, "/usr/bin/ai-assist", "ai-assist")
        assert "/monitor" in content

    def test_includes_reports_dir_when_set(self, platform_name, backend_class, tmp_path):
        backend = backend_class()
        reports = tmp_path / "reports"
        content = backend.service_content(tmp_path, reports, "/usr/bin/ai-assist", "ai-assist")
        assert str(reports) in content
        assert "AI_ASSIST_REPORTS_DIR" in content

    def test_excludes_reports_dir_when_none(self, platform_name, backend_class, tmp_path):
        backend = backend_class()
        content = backend.service_content(tmp_path, None, "/usr/bin/ai-assist", "ai-assist")
        # Should not have reports dir line when None
        lines = content.split("\n")
        reports_lines = [line for line in lines if "AI_ASSIST_REPORTS_DIR" in line]
        assert len(reports_lines) == 0


# =============================================================================
# Linux Systemd Backend Tests
# =============================================================================


class TestLinuxSystemdBackend:
    def test_service_file_location(self):
        backend = LinuxSystemdBackend()
        config_dir = Path("/home/user/.ai-assist")
        result = backend.service_file_path(config_dir)
        assert result == Path.home() / ".config" / "systemd" / "user" / "ai-assist.service"

    def test_service_file_iris(self):
        backend = LinuxSystemdBackend()
        config_dir = Path("/home/user/.iris")
        result = backend.service_file_path(config_dir)
        assert result == Path.home() / ".config" / "systemd" / "user" / "iris.service"

    def test_service_content_format(self, tmp_path):
        backend = LinuxSystemdBackend()
        content = backend.service_content(tmp_path, None, "/usr/bin/ai-assist", "ai-assist")
        assert "[Unit]" in content
        assert "[Service]" in content
        assert "[Install]" in content
        assert "ExecStart=/usr/bin/ai-assist /monitor" in content
        assert "Restart=on-failure" in content
        assert "After=network-online.target" in content

    def test_service_content_custom_binary(self, tmp_path):
        backend = LinuxSystemdBackend()
        content = backend.service_content(tmp_path, None, "/home/user/.local/bin/ai-assist", "ai-assist")
        assert "ExecStart=/home/user/.local/bin/ai-assist /monitor" in content

    def test_install_calls_systemctl(self, tmp_path):
        backend = LinuxSystemdBackend()
        service_file = tmp_path / "test.service"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.install(service_file, "ai-assist")

        assert mock_run.call_count == 2
        # Check daemon-reload
        mock_run.assert_any_call(["systemctl", "--user", "daemon-reload"], check=True)
        # Check enable --now
        mock_run.assert_any_call(["systemctl", "--user", "enable", "--now", "ai-assist"], check=True)

    def test_remove_calls_systemctl(self, tmp_path):
        backend = LinuxSystemdBackend()
        service_file = tmp_path / "test.service"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.remove(service_file, "ai-assist")

        assert mock_run.call_count == 2
        # Check disable --now (with check=False)
        mock_run.assert_any_call(["systemctl", "--user", "disable", "--now", "ai-assist"], check=False)
        # Check daemon-reload
        mock_run.assert_any_call(["systemctl", "--user", "daemon-reload"], check=True)

    def test_action_delegates_to_systemctl(self):
        backend = LinuxSystemdBackend()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.action("restart", "ai-assist")
        mock_run.assert_called_once_with(["systemctl", "--user", "restart", "ai-assist"], check=True)

    def test_status_calls_systemctl(self):
        backend = LinuxSystemdBackend()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.status("ai-assist")
        mock_run.assert_called_once_with(["systemctl", "--user", "status", "ai-assist"], check=False)

    def test_logs_calls_journalctl(self, tmp_path):
        backend = LinuxSystemdBackend()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.logs("ai-assist", tmp_path, None)
        mock_run.assert_called_once_with(["journalctl", "--user", "-u", "ai-assist"], check=False)

    def test_logs_passes_extra_args(self, tmp_path):
        backend = LinuxSystemdBackend()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.logs("ai-assist", tmp_path, ["-f", "-n", "100"])
        mock_run.assert_called_once_with(["journalctl", "--user", "-u", "ai-assist", "-f", "-n", "100"], check=False)


# =============================================================================
# macOS Launchd Backend Tests
# =============================================================================


class TestMacOSLaunchdBackend:
    def test_service_file_location(self):
        backend = MacOSLaunchdBackend()
        config_dir = Path("/Users/user/.ai-assist")
        result = backend.service_file_path(config_dir)
        assert result == Path.home() / "Library" / "LaunchAgents" / "ai-assist.plist"

    def test_service_file_iris(self):
        backend = MacOSLaunchdBackend()
        config_dir = Path("/Users/user/.iris")
        result = backend.service_file_path(config_dir)
        assert result == Path.home() / "Library" / "LaunchAgents" / "iris.plist"

    def test_plist_xml_structure(self, tmp_path):
        backend = MacOSLaunchdBackend()
        content = backend.service_content(tmp_path, None, "/usr/local/bin/ai-assist", "ai-assist")
        # Check XML structure
        assert '<?xml version="1.0" encoding="UTF-8"?>' in content
        assert "<!DOCTYPE plist" in content
        assert '<plist version="1.0">' in content
        assert "</plist>" in content

    def test_plist_required_keys(self, tmp_path):
        backend = MacOSLaunchdBackend()
        content = backend.service_content(tmp_path, None, "/usr/local/bin/ai-assist", "ai-assist")
        # Check required plist keys
        assert "<key>Label</key>" in content
        assert "<string>ai-assist</string>" in content
        assert "<key>ProgramArguments</key>" in content
        assert "<key>RunAtLoad</key>" in content
        assert "<key>KeepAlive</key>" in content
        assert "<key>EnvironmentVariables</key>" in content
        assert "<key>StandardOutPath</key>" in content
        assert "<key>StandardErrorPath</key>" in content

    def test_plist_program_arguments(self, tmp_path):
        backend = MacOSLaunchdBackend()
        content = backend.service_content(tmp_path, None, "/usr/local/bin/ai-assist", "ai-assist")
        assert "<string>/usr/local/bin/ai-assist</string>" in content
        assert "<string>/monitor</string>" in content

    def test_plist_environment_variables(self, tmp_path):
        backend = MacOSLaunchdBackend()
        content = backend.service_content(tmp_path, None, "/usr/local/bin/ai-assist", "ai-assist")
        assert "<key>PATH</key>" in content
        assert "<key>PYTHONUNBUFFERED</key>" in content
        assert "<key>AI_ASSIST_CONFIG_DIR</key>" in content
        assert str(tmp_path) in content

    def test_plist_log_files(self, tmp_path):
        backend = MacOSLaunchdBackend()
        content = backend.service_content(tmp_path, None, "/usr/local/bin/ai-assist", "ai-assist")
        assert f"{Path.home()}/Library/Logs/ai-assist.log" in content
        assert f"{Path.home()}/Library/Logs/ai-assist.err" in content

    def test_install_loads_service(self, tmp_path):
        backend = MacOSLaunchdBackend()
        service_file = tmp_path / "test.plist"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.install(service_file, "ai-assist")

        # Check load -w
        mock_run.assert_called_once_with(["launchctl", "load", "-w", str(service_file)], check=True)

    def test_remove_unloads_service(self, tmp_path):
        backend = MacOSLaunchdBackend()
        service_file = tmp_path / "test.plist"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.remove(service_file, "ai-assist")

        # Check unload -w
        mock_run.assert_called_once_with(["launchctl", "unload", "-w", str(service_file)], check=False)

    def test_action_start(self, tmp_path):
        backend = MacOSLaunchdBackend()
        service_file = tmp_path / "test.plist"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.action("start", "ai-assist", service_file)
        mock_run.assert_called_once_with(["launchctl", "load", str(service_file)], check=True)

    def test_action_stop(self, tmp_path):
        backend = MacOSLaunchdBackend()
        service_file = tmp_path / "test.plist"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.action("stop", "ai-assist", service_file)
        mock_run.assert_called_once_with(["launchctl", "unload", str(service_file)], check=True)

    def test_action_restart(self, tmp_path):
        backend = MacOSLaunchdBackend()
        service_file = tmp_path / "test.plist"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.action("restart", "ai-assist", service_file)
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["launchctl", "unload", str(service_file)], check=False)
        mock_run.assert_any_call(["launchctl", "load", str(service_file)], check=True)

    def test_action_enable(self, tmp_path):
        backend = MacOSLaunchdBackend()
        service_file = tmp_path / "test.plist"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.action("enable", "ai-assist", service_file)
        mock_run.assert_called_once_with(["launchctl", "load", "-w", str(service_file)], check=True)

    def test_action_disable(self, tmp_path):
        backend = MacOSLaunchdBackend()
        service_file = tmp_path / "test.plist"
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.action("disable", "ai-assist", service_file)
        mock_run.assert_called_once_with(["launchctl", "unload", "-w", str(service_file)], check=True)

    def test_action_unknown_raises(self):
        backend = MacOSLaunchdBackend()
        with pytest.raises(ValueError, match="Unknown action"):
            backend.action("invalid", "ai-assist")

    def test_status_calls_launchctl_list(self):
        backend = MacOSLaunchdBackend()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.status("ai-assist")
        mock_run.assert_called_once_with(["launchctl", "list", "ai-assist"], check=False)

    def test_logs_calls_tail(self, tmp_path):
        backend = MacOSLaunchdBackend()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.logs("ai-assist", tmp_path, None)
        expected_log = str(Path.home() / "Library" / "Logs" / "ai-assist.log")
        mock_run.assert_called_once_with(["tail", expected_log], check=False)

    def test_logs_passes_extra_args(self, tmp_path):
        backend = MacOSLaunchdBackend()
        with patch("ai_assist.service.subprocess.run") as mock_run:
            backend.logs("ai-assist", tmp_path, ["-f", "-n", "100"])
        expected_log = str(Path.home() / "Library" / "Logs" / "ai-assist.log")
        mock_run.assert_called_once_with(["tail", "-f", "-n", "100", expected_log], check=False)


# =============================================================================
# Public API Tests (Cross-Platform)
# =============================================================================


class TestInstallService:
    def test_writes_service_file_and_enables_linux(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        service_file = tmp_path / "systemd" / "user" / "ai-assist.service"
        service_file.parent.mkdir(parents=True)

        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run"),
            patch("ai_assist.service.sys.argv", ["/usr/bin/ai-assist"]),
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None

            with patch("ai_assist.service.LinuxSystemdBackend.service_file_path", return_value=service_file):
                install_service(str(config_dir), None)

        assert service_file.exists()
        assert "ExecStart=/usr/bin/ai-assist /monitor" in service_file.read_text()

    def test_includes_reports_dir_when_provided_linux(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        reports_dir = tmp_path / "reports"
        service_file = tmp_path / "systemd" / "user" / "ai-assist.service"
        service_file.parent.mkdir(parents=True)

        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run"),
            patch("ai_assist.service.sys.argv", ["/usr/bin/ai-assist"]),
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None

            with patch("ai_assist.service.LinuxSystemdBackend.service_file_path", return_value=service_file):
                install_service(str(config_dir), str(reports_dir))

        content = service_file.read_text()
        assert f"AI_ASSIST_REPORTS_DIR={reports_dir.resolve()}" in content


class TestRemoveService:
    def test_removes_service_file_linux(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        service_file = tmp_path / "systemd" / "user" / "ai-assist.service"
        service_file.parent.mkdir(parents=True, exist_ok=True)
        service_file.write_text("[Unit]\n")

        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run"),
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None

            with patch("ai_assist.service.LinuxSystemdBackend.service_file_path", return_value=service_file):
                remove_service(str(config_dir))

        assert not service_file.exists()

    def test_remove_succeeds_without_service_file_linux(self, tmp_path):
        config_dir = tmp_path / ".ai-assist"
        config_dir.mkdir()
        service_file = tmp_path / "systemd" / "user" / "ai-assist.service"

        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run"),
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None

            with patch("ai_assist.service.LinuxSystemdBackend.service_file_path", return_value=service_file):
                remove_service(str(config_dir))  # should not raise


class TestServiceSystemctl:
    def test_delegates_action_to_backend_linux(self, tmp_path):
        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run") as mock_run,
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            service_systemctl("restart", str(tmp_path))
        mock_run.assert_called_once_with(["systemctl", "--user", "restart", tmp_path.name], check=True)

    def test_uses_service_name_from_config_dir_linux(self, tmp_path):
        dotdir = tmp_path / ".iris"
        dotdir.mkdir()
        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run") as mock_run,
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            service_systemctl("stop", str(dotdir))
        mock_run.assert_called_once_with(["systemctl", "--user", "stop", "iris"], check=True)


class TestServiceStatus:
    def test_calls_backend_status_linux(self, tmp_path):
        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run") as mock_run,
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            service_status(str(tmp_path))
        mock_run.assert_called_once_with(["systemctl", "--user", "status", tmp_path.name], check=False)


class TestServiceLogs:
    def test_calls_backend_logs_no_extra_args_linux(self, tmp_path):
        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run") as mock_run,
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            service_logs(str(tmp_path))
        mock_run.assert_called_once_with(["journalctl", "--user", "-u", tmp_path.name], check=False)

    def test_passes_extra_args_linux(self, tmp_path):
        with (
            patch("ai_assist.service.platform.system", return_value="Linux"),
            patch("ai_assist.service.subprocess.run") as mock_run,
        ):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            service_logs(str(tmp_path), ["-f"])
        mock_run.assert_called_once_with(["journalctl", "--user", "-u", tmp_path.name, "-f"], check=False)


# =============================================================================
# Legacy Compatibility Tests
# =============================================================================


class TestLegacyFunctions:
    def test_service_file_compat_linux(self):
        with patch("ai_assist.service.platform.system", return_value="Linux"):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            config_dir = Path("/home/user/.ai-assist")
            result = _service_file(config_dir)
            assert result == Path.home() / ".config" / "systemd" / "user" / "ai-assist.service"

    def test_service_content_compat_linux(self, tmp_path):
        with patch("ai_assist.service.platform.system", return_value="Linux"):
            # Clear backend cache
            import ai_assist.service

            ai_assist.service._backend_cache = None
            content = _service_content(tmp_path, None, "/usr/bin/ai-assist")
            assert "ExecStart=/usr/bin/ai-assist /monitor" in content
            assert str(tmp_path) in content
