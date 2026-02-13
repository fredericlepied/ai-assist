"""Configuration management for ai-assist"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


def get_config_dir(override: str | None = None) -> Path:
    """Get the ai-assist configuration directory

    Priority (highest to lowest):
    1. override parameter
    2. AI_ASSIST_CONFIG_DIR environment variable
    3. Default: ~/.ai-assist

    Args:
        override: Optional path to override config directory

    Returns:
        Path to configuration directory (created if it doesn't exist)
    """
    if override:
        config_dir = Path(os.path.expanduser(override))
    else:
        config_dir_str = os.getenv("AI_ASSIST_CONFIG_DIR")
        if config_dir_str:
            config_dir = Path(os.path.expanduser(config_dir_str))
        else:
            config_dir = Path.home() / ".ai-assist"

    # Create directory if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)

    return config_dir


class MCPServerConfig(BaseModel):
    """MCP Server configuration"""

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class AiAssistConfig(BaseModel):
    """Main ai-assist configuration"""

    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # Vertex AI configuration (alternative to direct API key)
    vertex_project_id: str | None = Field(default_factory=lambda: os.getenv("ANTHROPIC_VERTEX_PROJECT_ID"))
    vertex_region: str | None = Field(default_factory=lambda: os.getenv("ANTHROPIC_VERTEX_REGION"))

    model: str = Field(default="claude-sonnet-4-5@20250929")

    @property
    def use_vertex(self) -> bool:
        """Check if using Vertex AI instead of direct API"""
        return bool(self.vertex_project_id and not self.anthropic_api_key)

    # MCP servers configuration
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    # Notification settings
    enable_notifications: bool = Field(default=True)
    notification_channel: str = Field(default="console", description="console, email, slack, etc.")

    # Script execution security (disabled by default)
    allow_skill_script_execution: bool = Field(
        default_factory=lambda: os.getenv("AI_ASSIST_ALLOW_SCRIPT_EXECUTION", "false").lower() == "true",
        description="Enable script execution from Agent Skills (security risk if enabled)",
    )

    # Command execution allowlist (Phase 1 security)
    allowed_commands: list[str] = Field(
        default_factory=lambda: ["grep", "find", "wc", "sort", "head", "tail", "ls", "cat", "diff", "file", "stat"],
    )

    # Filesystem path restrictions (Phase 2 security)
    allowed_paths: list[str] = Field(
        default_factory=lambda: ["~/.ai-assist", "/tmp/ai-assist"],
    )

    # Tools requiring user confirmation (Phase 4 security)
    confirm_tools: list[str] = Field(
        default_factory=lambda: ["internal__create_directory"],
    )

    @classmethod
    def from_env(cls, mcp_servers_file: Path | None = None, config_dir: Path | None = None) -> "AiAssistConfig":
        """Load configuration from environment variables and YAML files

        Args:
            mcp_servers_file: Optional path to MCP servers config file
            config_dir: Optional config directory (defaults to get_config_dir())
        """
        if config_dir is None:
            config_dir = get_config_dir()

        if mcp_servers_file is None:
            mcp_servers_file = config_dir / "mcp_servers.yaml"

        mcp_servers = load_mcp_servers_from_yaml(mcp_servers_file)

        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            vertex_project_id=os.getenv("ANTHROPIC_VERTEX_PROJECT_ID"),
            vertex_region=os.getenv("ANTHROPIC_VERTEX_REGION"),
            model=os.getenv("AI_ASSIST_MODEL", "claude-sonnet-4-5@20250929"),
            mcp_servers=mcp_servers,
        )


def load_mcp_servers_from_yaml(path: Path) -> dict[str, MCPServerConfig]:
    """Load MCP server configurations from YAML file

    Args:
        path: Path to mcp_servers.yaml file

    Returns:
        Dictionary of server name -> MCPServerConfig
    """
    if not path.exists():
        return {}

    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "servers" not in data:
            return {}

        servers = {}
        for name, config in data.get("servers", {}).items():
            if not config.get("enabled", True):
                continue

            env = {}
            for key, value in config.get("env", {}).items():
                env[key] = os.path.expandvars(value)

            servers[name] = MCPServerConfig(
                command=config["command"], args=config.get("args", []), env=env, enabled=config.get("enabled", True)
            )

        return servers

    except yaml.YAMLError as e:
        print(f"Error parsing MCP servers YAML: {e}")
        return {}
    except KeyError as e:
        print(f"Missing required field in MCP server config: {e}")
        return {}
    except Exception as e:
        print(f"Error loading MCP servers: {e}")
        return {}


def get_config() -> AiAssistConfig:
    """Get the current configuration"""
    return AiAssistConfig.from_env()
