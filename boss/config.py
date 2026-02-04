"""Configuration management for BOSS"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class MCPServerConfig(BaseModel):
    """MCP Server configuration"""
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class MonitoringConfig(BaseModel):
    """Monitoring configuration"""
    jira_check_interval: int = Field(default=300, description="Jira check interval in seconds")
    dci_check_interval: int = Field(default=300, description="DCI check interval in seconds")
    jira_projects: list[str] = Field(default_factory=list, description="Jira projects to monitor")
    dci_queries: list[str] = Field(default_factory=list, description="DCI queries to monitor")


class BossConfig(BaseModel):
    """Main BOSS configuration"""
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # Vertex AI configuration (alternative to direct API key)
    vertex_project_id: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_VERTEX_PROJECT_ID"))
    vertex_region: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_VERTEX_REGION"))

    model: str = Field(default="claude-sonnet-4-5@20250929")

    @property
    def use_vertex(self) -> bool:
        """Check if using Vertex AI instead of direct API"""
        return bool(self.vertex_project_id and not self.anthropic_api_key)

    # MCP servers configuration
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    # Monitoring configuration
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    # Notification settings
    enable_notifications: bool = Field(default=True)
    notification_channel: str = Field(default="console", description="console, email, slack, etc.")

    @classmethod
    def from_env(cls) -> "BossConfig":
        """Load configuration from environment variables"""
        # Configure dci MCP server - use local development version if path is set
        dci_server_path = os.getenv("DCI_MCP_SERVER_PATH")

        if dci_server_path:
            # Local development version - let it load credentials from its own .env file
            # Only pass MCP_SHOW_BANNER to control output
            dci_env = {"MCP_SHOW_BANNER": "false"}
            dci_config = MCPServerConfig(
                command=f"{dci_server_path}/.venv/bin/python",
                args=[f"{dci_server_path}/main.py"],
                env=dci_env
            )
        else:
            # Production version from PyPI - pass credentials from BOSS environment
            dci_env = {
                "DCI_CLIENT_ID": os.getenv("DCI_CLIENT_ID", ""),
                "DCI_API_SECRET": os.getenv("DCI_API_SECRET", ""),
                "DCI_CS_URL": os.getenv("DCI_CS_URL", "https://api.distributed-ci.io"),
                "MCP_SHOW_BANNER": "false",
            }

            # Add Jira credentials if available (dci-mcp-server provides Jira tools)
            if os.getenv("JIRA_API_TOKEN"):
                dci_env["JIRA_API_TOKEN"] = os.getenv("JIRA_API_TOKEN")
            if os.getenv("JIRA_URL"):
                dci_env["JIRA_URL"] = os.getenv("JIRA_URL")

            # Add Google credentials if available (dci-mcp-server provides Google Docs tools)
            if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                dci_env["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

            dci_config = MCPServerConfig(
                command="uvx",
                args=["--from", "dci-mcp-server", "dci-mcp-server"],
                env=dci_env
            )

        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            vertex_project_id=os.getenv("ANTHROPIC_VERTEX_PROJECT_ID"),
            vertex_region=os.getenv("ANTHROPIC_VERTEX_REGION"),  # No default - let Anthropic SDK choose
            model=os.getenv("BOSS_MODEL", "claude-sonnet-4-5@20250929"),
            mcp_servers={
                "dci": dci_config,
            },
            monitoring=MonitoringConfig(
                jira_check_interval=int(os.getenv("JIRA_CHECK_INTERVAL", "300")),
                dci_check_interval=int(os.getenv("DCI_CHECK_INTERVAL", "300")),
                jira_projects=os.getenv("JIRA_PROJECTS", "").split(",") if os.getenv("JIRA_PROJECTS") else [],
                dci_queries=os.getenv("DCI_QUERIES", "").split("|") if os.getenv("DCI_QUERIES") else [],
            )
        )


def get_config() -> BossConfig:
    """Get the current configuration"""
    return BossConfig.from_env()
