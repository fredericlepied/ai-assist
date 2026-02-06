"""Internal report management tools for ai-assist"""

import json
import os
from datetime import datetime
from pathlib import Path


class ReportTools:
    """Internal tools for managing markdown reports"""

    def __init__(self, reports_dir: Path = None):
        """Initialize report tools

        Args:
            reports_dir: Directory to store reports (defaults to ~/ai-assist/reports)
        """
        if reports_dir is None:
            env_dir = os.getenv("AI_ASSIST_REPORTS_DIR")
            if env_dir:
                # Expand ~ in the path from environment variable
                reports_dir = Path(os.path.expanduser(env_dir))
            else:
                reports_dir = Path.home() / "ai-assist" / "reports"

        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def get_tool_definitions(self) -> list[dict]:
        """Get tool definitions for the AI agent"""
        return [
            {
                "name": "internal__write_report",
                "description": "Write or overwrite a markdown report file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Report name (without .md extension)",
                        },
                        "content": {
                            "type": "string",
                            "description": "Markdown content to write",
                        },
                    },
                    "required": ["name", "content"],
                },
                "_server": "internal",
            },
            {
                "name": "internal__append_to_report",
                "description": "Append content to existing report (creates if doesn't exist)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Report name (without .md extension)",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to append",
                        },
                        "section": {
                            "type": "string",
                            "description": "Optional section header (without ##)",
                        },
                    },
                    "required": ["name", "content"],
                },
                "_server": "internal",
            },
            {
                "name": "internal__read_report",
                "description": "Read a report's current content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Report name (without .md extension)",
                        }
                    },
                    "required": ["name"],
                },
                "_server": "internal",
            },
            {
                "name": "internal__list_reports",
                "description": "List all available reports with metadata",
                "input_schema": {"type": "object", "properties": {}},
                "_server": "internal",
            },
            {
                "name": "internal__delete_report",
                "description": "Delete a report file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Report name (without .md extension)",
                        }
                    },
                    "required": ["name"],
                },
                "_server": "internal",
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a report tool

        Args:
            tool_name: Name of the tool (without internal__ prefix)
            arguments: Tool arguments

        Returns:
            str: Tool result as text
        """
        if tool_name == "write_report":
            return self._write_report(arguments["name"], arguments["content"])

        elif tool_name == "append_to_report":
            return self._append_to_report(arguments["name"], arguments["content"], arguments.get("section"))

        elif tool_name == "read_report":
            return self._read_report(arguments["name"])

        elif tool_name == "list_reports":
            return self._list_reports()

        elif tool_name == "delete_report":
            return self._delete_report(arguments["name"])

        else:
            raise ValueError(f"Unknown report tool: {tool_name}")

    def _write_report(self, name: str, content: str) -> str:
        """Write or overwrite a report file"""
        report_file = self.reports_dir / f"{name}.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"<!-- Generated by AI Assistant on {timestamp} -->\n\n"

        report_file.write_text(header + content)

        return f"Report '{name}' written to {report_file}"

    def _append_to_report(self, name: str, content: str, section: str = None) -> str:
        """Append content to a report (creates if doesn't exist)"""
        report_file = self.reports_dir / f"{name}.md"

        if not report_file.exists():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header = f"<!-- Generated by AI Assistant on {timestamp} -->\n\n"
            report_file.write_text(header)

        if section:
            content = f"\n## {section}\n\n{content}\n"
        else:
            content = f"\n{content}\n"

        with open(report_file, "a") as f:
            f.write(content)

        return f"Content appended to '{name}'"

    def _read_report(self, name: str) -> str:
        """Read a report's content"""
        report_file = self.reports_dir / f"{name}.md"

        if report_file.exists():
            return report_file.read_text()
        else:
            return f"Report '{name}' not found"

    def _list_reports(self) -> str:
        """List all available reports with metadata"""
        reports = []
        for report_file in sorted(self.reports_dir.glob("*.md")):
            stat = report_file.stat()
            reports.append(
                {
                    "name": report_file.stem,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

        return json.dumps(reports, indent=2)

    def _delete_report(self, name: str) -> str:
        """Delete a report file"""
        report_file = self.reports_dir / f"{name}.md"

        if report_file.exists():
            report_file.unlink()
            return f"Report '{name}' deleted"
        else:
            return f"Report '{name}' not found"
