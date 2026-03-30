"""Systemd user service management for ai-assist instances"""

import os
import subprocess
import sys
from pathlib import Path

SUBCOMMANDS = {"install", "remove", "start", "stop", "restart", "enable", "disable", "status", "logs"}


def _resolve_config_dir(config_dir: str | None) -> Path:
    path = config_dir or os.environ.get("AI_ASSIST_CONFIG_DIR") or str(Path.home() / ".ai-assist")
    return Path(path).expanduser().resolve()


def _resolve_reports_dir(reports_dir: str | None) -> Path | None:
    path = reports_dir or os.environ.get("AI_ASSIST_REPORTS_DIR")
    return Path(path).expanduser().resolve() if path else None


def _service_name(config_dir: Path) -> str:
    return config_dir.name.lstrip(".")


def _service_file(config_dir: Path) -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{_service_name(config_dir)}.service"


def _service_content(config_dir: Path, reports_dir: Path | None, binary: str) -> str:
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


def install_service(config_dir_arg: str | None, reports_dir_arg: str | None) -> None:
    config_dir = _resolve_config_dir(config_dir_arg)
    reports_dir = _resolve_reports_dir(reports_dir_arg)
    service_file = _service_file(config_dir)
    name = _service_name(config_dir)

    service_file.parent.mkdir(parents=True, exist_ok=True)
    service_file.write_text(_service_content(config_dir, reports_dir, sys.argv[0]))
    print(f"Written {service_file}")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", name], check=True)
    print(f"Enabled and started {name}")
    print(f"Config dir: {config_dir}")
    if reports_dir:
        print(f"Reports dir: {reports_dir}")
    print(f"\nTo follow logs: ai-assist /service logs {config_dir}")


def remove_service(config_dir_arg: str | None) -> None:
    config_dir = _resolve_config_dir(config_dir_arg)
    service_file = _service_file(config_dir)
    name = _service_name(config_dir)

    subprocess.run(["systemctl", "--user", "disable", "--now", name], check=False)
    if service_file.exists():
        service_file.unlink()
        print(f"Removed {service_file}")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    print(f"Removed service for {config_dir}")


def service_systemctl(action: str, config_dir_arg: str | None) -> None:
    config_dir = _resolve_config_dir(config_dir_arg)
    name = _service_name(config_dir)
    subprocess.run(["systemctl", "--user", action, name], check=True)


def service_status(config_dir_arg: str | None) -> None:
    config_dir = _resolve_config_dir(config_dir_arg)
    name = _service_name(config_dir)
    subprocess.run(["systemctl", "--user", "status", name], check=False)


def service_logs(config_dir_arg: str | None, extra_args: list[str] | None = None) -> None:
    config_dir = _resolve_config_dir(config_dir_arg)
    name = _service_name(config_dir)
    subprocess.run(["journalctl", "--user", "-u", name] + (extra_args or []), check=False)
