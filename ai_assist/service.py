"""Cross-platform service management for ai-assist instances

Supports:
- Linux: systemd user services
- macOS: launchd user agents
"""

import os
import platform
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

SUBCOMMANDS = {"install", "remove", "start", "stop", "restart", "enable", "disable", "status", "logs"}


# =============================================================================
# Common Utilities
# =============================================================================


def _resolve_config_dir(config_dir: str | None) -> Path:
    path = config_dir or os.environ.get("AI_ASSIST_CONFIG_DIR") or str(Path.home() / ".ai-assist")
    return Path(path).expanduser().resolve()


def _resolve_reports_dir(reports_dir: str | None) -> Path | None:
    path = reports_dir or os.environ.get("AI_ASSIST_REPORTS_DIR")
    return Path(path).expanduser().resolve() if path else None


def _service_name(config_dir: Path) -> str:
    return config_dir.name.lstrip(".")


# =============================================================================
# Abstract Backend Interface
# =============================================================================


class ServiceBackend(ABC):
    """Abstract base class for platform-specific service management"""

    @abstractmethod
    def service_file_path(self, config_dir: Path) -> Path:
        """Return path where service file should be stored"""

    @abstractmethod
    def service_content(self, config_dir: Path, reports_dir: Path | None, binary: str, service_name: str) -> str:
        """Generate service file content"""

    @abstractmethod
    def install(self, service_file: Path, service_name: str) -> None:
        """Install and start the service"""

    @abstractmethod
    def remove(self, service_file: Path, service_name: str) -> None:
        """Stop and remove the service"""

    @abstractmethod
    def action(self, action: str, service_name: str, service_file: Path | None = None) -> None:
        """Perform service action: start, stop, restart, enable, disable"""

    @abstractmethod
    def status(self, service_name: str) -> None:
        """Display service status"""

    @abstractmethod
    def logs(self, service_name: str, config_dir: Path, extra_args: list[str] | None) -> None:
        """Display service logs"""


# =============================================================================
# Linux Systemd Backend
# =============================================================================


class LinuxSystemdBackend(ServiceBackend):
    """Linux systemd user service management"""

    def service_file_path(self, config_dir: Path) -> Path:
        return Path.home() / ".config" / "systemd" / "user" / f"{_service_name(config_dir)}.service"

    def service_content(self, config_dir: Path, reports_dir: Path | None, binary: str, service_name: str) -> str:
        # Capture current PATH to preserve user's environment (including ~/.local/bin)
        current_path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")

        lines = [
            "[Unit]",
            f"Description=ai-assist monitor ({config_dir})",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"Environment=PATH={current_path}",
            "Environment=PYTHONUNBUFFERED=1",
            f"Environment=AI_ASSIST_CONFIG_DIR={config_dir}",
        ]
        if reports_dir:
            lines.append(f"Environment=AI_ASSIST_REPORTS_DIR={reports_dir}")
        lines += [
            f"ExecStart={binary} /monitor",
            "Restart=on-failure",
            "RestartSec=10s",
            "",
            "[Install]",
            "WantedBy=default.target",
        ]
        return "\n".join(lines) + "\n"

    def install(self, service_file: Path, service_name: str) -> None:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", service_name], check=True)

    def remove(self, service_file: Path, service_name: str) -> None:
        subprocess.run(["systemctl", "--user", "disable", "--now", service_name], check=False)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

    def action(self, action: str, service_name: str, service_file: Path | None = None) -> None:
        subprocess.run(["systemctl", "--user", action, service_name], check=True)

    def status(self, service_name: str) -> None:
        subprocess.run(["systemctl", "--user", "status", service_name], check=False)

    def logs(self, service_name: str, config_dir: Path, extra_args: list[str] | None) -> None:
        subprocess.run(["journalctl", "--user", "-u", service_name] + (extra_args or []), check=False)


# =============================================================================
# macOS Launchd Backend
# =============================================================================


class MacOSLaunchdBackend(ServiceBackend):
    """macOS launchd user agent management"""

    def service_file_path(self, config_dir: Path) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{_service_name(config_dir)}.plist"

    def service_content(self, config_dir: Path, reports_dir: Path | None, binary: str, service_name: str) -> str:
        # Capture current PATH to preserve user's environment
        current_path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")

        # Build environment variables dict
        env_vars = [
            "    <key>PATH</key>",
            f"    <string>{current_path}</string>",
            "    <key>PYTHONUNBUFFERED</key>",
            "    <string>1</string>",
            "    <key>AI_ASSIST_CONFIG_DIR</key>",
            f"    <string>{config_dir}</string>",
        ]
        if reports_dir:
            env_vars += [
                "    <key>AI_ASSIST_REPORTS_DIR</key>",
                f"    <string>{reports_dir}</string>",
            ]

        # Create plist content
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{service_name}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{binary}</string>
    <string>/monitor</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>EnvironmentVariables</key>
  <dict>
{chr(10).join(env_vars)}
  </dict>
  <key>StandardOutPath</key>
  <string>{Path.home()}/Library/Logs/{service_name}.log</string>
  <key>StandardErrorPath</key>
  <string>{Path.home()}/Library/Logs/{service_name}.err</string>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
"""
        return plist

    def install(self, service_file: Path, service_name: str) -> None:
        # Load and enable the service (-w writes the disabled override)
        subprocess.run(["launchctl", "load", "-w", str(service_file)], check=True)

    def remove(self, service_file: Path, service_name: str) -> None:
        # Unload and disable the service (-w writes the disabled override)
        subprocess.run(["launchctl", "unload", "-w", str(service_file)], check=False)

    def action(self, action: str, service_name: str, service_file: Path | None = None) -> None:
        # For stop/start/restart, use unload/load without -w to preserve enabled state
        if action == "start":
            if service_file:
                subprocess.run(["launchctl", "load", str(service_file)], check=True)
            else:
                raise ValueError("start requires service_file path")
        elif action == "stop":
            if service_file:
                subprocess.run(["launchctl", "unload", str(service_file)], check=True)
            else:
                raise ValueError("stop requires service_file path")
        elif action == "restart":
            if service_file:
                # Unload then reload
                subprocess.run(["launchctl", "unload", str(service_file)], check=False)
                subprocess.run(["launchctl", "load", str(service_file)], check=True)
            else:
                raise ValueError("restart requires service_file path")
        elif action == "enable":
            # Load with -w flag to enable permanently
            if service_file:
                subprocess.run(["launchctl", "load", "-w", str(service_file)], check=True)
            else:
                raise ValueError("enable requires service_file path")
        elif action == "disable":
            # Unload with -w flag to disable permanently
            if service_file:
                subprocess.run(["launchctl", "unload", "-w", str(service_file)], check=True)
            else:
                raise ValueError("disable requires service_file path")
        else:
            raise ValueError(f"Unknown action: {action}")

    def status(self, service_name: str) -> None:
        # Use list to show service status
        subprocess.run(["launchctl", "list", service_name], check=False)

    def logs(self, service_name: str, config_dir: Path, extra_args: list[str] | None) -> None:
        log_file = Path.home() / "Library" / "Logs" / f"{service_name}.log"
        # Use tail to view logs, supporting -f and other flags
        subprocess.run(["tail"] + (extra_args or []) + [str(log_file)], check=False)


# =============================================================================
# Backend Factory
# =============================================================================


_backend_cache: ServiceBackend | None = None


def _get_backend() -> ServiceBackend:
    """Get appropriate backend for current platform"""
    global _backend_cache
    if _backend_cache is not None:
        return _backend_cache

    system = platform.system()
    if system == "Linux":
        _backend_cache = LinuxSystemdBackend()
    elif system == "Darwin":
        _backend_cache = MacOSLaunchdBackend()
    else:
        raise RuntimeError(f"Service management not supported on {system}")

    return _backend_cache


# =============================================================================
# Public API Functions
# =============================================================================


def install_service(config_dir_arg: str | None, reports_dir_arg: str | None) -> None:
    backend = _get_backend()
    config_dir = _resolve_config_dir(config_dir_arg)
    reports_dir = _resolve_reports_dir(reports_dir_arg)
    service_file = backend.service_file_path(config_dir)
    name = _service_name(config_dir)

    service_file.parent.mkdir(parents=True, exist_ok=True)
    service_file.write_text(backend.service_content(config_dir, reports_dir, sys.argv[0], name))
    print(f"Written {service_file}")

    backend.install(service_file, name)
    print(f"Enabled and started {name}")
    print(f"Config dir: {config_dir}")
    if reports_dir:
        print(f"Reports dir: {reports_dir}")
    print(f"\nTo follow logs: ai-assist /service logs {config_dir}")


def remove_service(config_dir_arg: str | None) -> None:
    backend = _get_backend()
    config_dir = _resolve_config_dir(config_dir_arg)
    service_file = backend.service_file_path(config_dir)
    name = _service_name(config_dir)

    backend.remove(service_file, name)
    if service_file.exists():
        service_file.unlink()
        print(f"Removed {service_file}")
    print(f"Removed service for {config_dir}")


def service_systemctl(action: str, config_dir_arg: str | None) -> None:
    backend = _get_backend()
    config_dir = _resolve_config_dir(config_dir_arg)
    name = _service_name(config_dir)
    service_file = backend.service_file_path(config_dir)
    backend.action(action, name, service_file)


def service_status(config_dir_arg: str | None) -> None:
    backend = _get_backend()
    config_dir = _resolve_config_dir(config_dir_arg)
    name = _service_name(config_dir)
    backend.status(name)


def service_logs(config_dir_arg: str | None, extra_args: list[str] | None = None) -> None:
    backend = _get_backend()
    config_dir = _resolve_config_dir(config_dir_arg)
    name = _service_name(config_dir)
    backend.logs(name, config_dir, extra_args)


# Legacy compatibility - keep old function names
def _service_file(config_dir: Path) -> Path:
    """Legacy function for backward compatibility in tests"""
    backend = _get_backend()
    return backend.service_file_path(config_dir)


def _service_content(config_dir: Path, reports_dir: Path | None, binary: str) -> str:
    """Legacy function for backward compatibility in tests"""
    backend = _get_backend()
    name = _service_name(config_dir)
    return backend.service_content(config_dir, reports_dir, binary, name)
