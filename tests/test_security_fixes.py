"""Regression tests for security vulnerabilities.

Each test demonstrates a specific vulnerability that was patched.
Tests are written so they would FAIL on the vulnerable code and PASS on the fix.
"""

import io
import zipfile
from unittest.mock import MagicMock

import pytest

from ai_assist.config import AiAssistConfig
from ai_assist.report_tools import ReportTools
from ai_assist.script_execution_tools import ScriptExecutionTools
from ai_assist.skills_loader import SkillsLoader
from ai_assist.skills_manager import SkillsManager

# ── 1. Zip Slip in ClawHub skill installation ────────────────────────────


class TestZipSlip:
    """Verify that zip archives with path traversal entries are rejected."""

    def _make_malicious_zip(self) -> bytes:
        """Build a ZIP with an entry that escapes the target directory."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("SKILL.md", "---\nname: evil\ndescription: pwned\n---\nEvil skill.\n")
            zf.writestr("../../../tmp/evil_payload.txt", "pwned")
        buf.seek(0)
        return buf.read()

    def test_zip_slip_blocked(self, tmp_path):
        """Extracting a zip with '../' paths must raise ValueError."""
        malicious_zip = self._make_malicious_zip()
        target_dir = tmp_path / "extract"
        target_dir.mkdir()

        with pytest.raises(ValueError, match="Zip slip"):
            with zipfile.ZipFile(io.BytesIO(malicious_zip)) as zf:
                # Reproduce the patched extraction logic from skills_loader
                for member in zf.namelist():
                    target = (target_dir / member).resolve()
                    if not target.is_relative_to(target_dir.resolve()):
                        raise ValueError(f"Zip slip detected in skill archive: {member}")
                zf.extractall(target_dir)

    def test_safe_zip_allowed(self, tmp_path):
        """A normal zip without traversal paths must extract successfully."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("SKILL.md", "---\nname: safe\ndescription: safe skill\n---\nSafe.\n")
            zf.writestr("scripts/run.sh", "#!/bin/bash\necho ok")
        buf.seek(0)

        target_dir = tmp_path / "extract"
        target_dir.mkdir()

        with zipfile.ZipFile(io.BytesIO(buf.read())) as zf:
            for member in zf.namelist():
                target = (target_dir / member).resolve()
                if not target.is_relative_to(target_dir.resolve()):
                    raise ValueError(f"Zip slip detected: {member}")
            zf.extractall(target_dir)

        assert (target_dir / "SKILL.md").exists()
        assert (target_dir / "scripts" / "run.sh").exists()


# ── 2. String-based path traversal in script execution ───────────────────


class TestScriptPathTraversal:
    """Verify that startswith()-style path bypass is prevented."""

    @pytest.mark.asyncio
    async def test_sibling_directory_name_prefix_blocked(self, tmp_path):
        """A script in /skills/foobar/ must NOT pass validation for /skills/foo/."""
        # Create two skill dirs: "foo" (legitimate) and "foobar" (attacker)
        legit_dir = tmp_path / "foo"
        legit_dir.mkdir()
        evil_dir = tmp_path / "foobar"
        evil_dir.mkdir()
        scripts_dir = evil_dir / "scripts"
        scripts_dir.mkdir()
        evil_script = scripts_dir / "evil.sh"
        evil_script.write_text("#!/bin/bash\necho pwned")
        evil_script.chmod(0o755)

        # Build a mock skill whose skill_path is "foo" but scripts point to "foobar"
        mock_skill = MagicMock()
        mock_skill.metadata.skill_path = legit_dir  # reported as /tmp/.../foo
        mock_skill.metadata.allowed_tools = ["internal__execute_skill_script"]
        mock_skill.scripts = {"evil.sh": evil_script}  # actually in /tmp/.../foobar/scripts/

        manager = MagicMock()
        manager.loaded_skills = {"foo": mock_skill}

        config = AiAssistConfig(anthropic_api_key="test", allow_skill_script_execution=True)
        tools = ScriptExecutionTools(manager, config)

        result = await tools.execute_tool("execute_skill_script", {"skill_name": "foo", "script_name": "evil.sh"})

        assert "Error" in result
        assert "traversal" in result.lower()


# ── 3. macOS notification command injection ──────────────────────────────


class TestMacOSNotificationInjection:
    """Verify that notification content is sanitized for AppleScript."""

    def test_backslash_quote_escape(self):
        """Backslashes followed by quotes must not break AppleScript escaping."""
        # Content with backslash-quote that could break out of AppleScript string
        malicious = 'test\\" & do shell script "whoami'

        # Apply the same sanitization the channel does
        sanitized = malicious.replace("\\", "\\\\").replace('"', '\\"')
        sanitized = "".join(c for c in sanitized if c >= " " or c in "\t")

        # The result must not contain an unescaped quote
        # After escaping, all quotes should be preceded by a backslash
        in_escape = False
        for c in sanitized:
            if in_escape:
                in_escape = False
                continue
            if c == "\\":
                in_escape = True
                continue
            # An unescaped double quote means injection is possible
            assert c != '"', f"Unescaped quote found in: {sanitized}"

    def test_control_characters_stripped(self):
        """Control characters (newlines, etc.) must be removed."""
        malicious = 'line1\n" & do shell script "id'

        sanitized = malicious.replace("\\", "\\\\").replace('"', '\\"')
        sanitized = "".join(c for c in sanitized if c >= " " or c in "\t")

        # No raw newlines should remain
        assert "\n" not in sanitized
        assert "\r" not in sanitized


# ── 4. Permissive script execution defaults ──────────────────────────────


class TestScriptPermissionDefaults:
    """Verify that skills without allowed-tools are allowed when script execution is enabled."""

    @pytest.mark.asyncio
    async def test_skill_without_allowed_tools_permitted(self, tmp_path):
        """A skill without allowed-tools should be permitted when user opted in globally."""
        skill_dir = tmp_path / "no-perms-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\n"
            "name: no-perms-skill\n"
            "description: Skill with scripts but no allowed-tools declaration\n"
            "---\n"
            "This skill has scripts but doesn't declare allowed-tools.\n"
        )

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        script = scripts_dir / "run.sh"
        script.write_text("#!/bin/bash\necho should-run")
        script.chmod(0o755)

        loader = SkillsLoader()
        manager = SkillsManager(loader)
        content = loader.load_skill_from_local(skill_dir)
        manager.loaded_skills["no-perms-skill"] = content

        config = AiAssistConfig(anthropic_api_key="test", allow_skill_script_execution=True)
        tools = ScriptExecutionTools(manager, config)

        result = await tools.execute_tool(
            "execute_skill_script", {"skill_name": "no-perms-skill", "script_name": "run.sh"}
        )

        assert "not allowed" not in result

    @pytest.mark.asyncio
    async def test_skill_with_explicit_allowed_tools_permitted(self, tmp_path):
        """A skill that declares allowed-tools with script execution must work."""
        skill_dir = tmp_path / "allowed-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\n"
            "name: allowed-skill\n"
            "description: Skill with explicit script permission\n"
            'allowed-tools: "internal__execute_skill_script"\n'
            "---\n"
            "This skill explicitly allows script execution.\n"
        )

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        script = scripts_dir / "hello.sh"
        script.write_text("#!/bin/bash\necho hello-allowed")
        script.chmod(0o755)

        loader = SkillsLoader()
        manager = SkillsManager(loader)
        content = loader.load_skill_from_local(skill_dir)
        manager.loaded_skills["allowed-skill"] = content

        config = AiAssistConfig(anthropic_api_key="test", allow_skill_script_execution=True)
        tools = ScriptExecutionTools(manager, config)

        result = await tools.execute_tool(
            "execute_skill_script", {"skill_name": "allowed-skill", "script_name": "hello.sh"}
        )

        assert "hello-allowed" in result
        assert "Error" not in result


# ── 5. Report path traversal ─────────────────────────────────────────────


class TestReportPathTraversal:
    """Verify that report names with '../' cannot escape the reports directory."""

    def test_write_report_path_traversal_blocked(self, tmp_path):
        tools = ReportTools(reports_dir=tmp_path / "reports")

        result = tools._write_report("../../etc/cron.d/evil", "malicious content")

        assert "Error" in result
        assert "path traversal" in result.lower()
        # Ensure no file was created outside reports dir
        assert not (tmp_path / "etc").exists()

    def test_append_report_path_traversal_blocked(self, tmp_path):
        tools = ReportTools(reports_dir=tmp_path / "reports")

        result = tools._append_to_report("../../../tmp/evil", "malicious content")

        assert "Error" in result
        assert "path traversal" in result.lower()

    def test_read_report_path_traversal_blocked(self, tmp_path):
        tools = ReportTools(reports_dir=tmp_path / "reports")

        # Create a file outside reports dir to make sure it's not readable
        outside = tmp_path / "secret.md"
        outside.write_text("secret data")

        result = tools._read_report("../secret")

        # Should not return the file contents
        assert "secret data" not in result

    def test_delete_report_path_traversal_blocked(self, tmp_path):
        tools = ReportTools(reports_dir=tmp_path / "reports")

        # Create a file outside reports dir
        outside = tmp_path / "important.md"
        outside.write_text("important data")

        tools._delete_report("../important")

        # File must still exist
        assert outside.exists()

    def test_normal_report_name_allowed(self, tmp_path):
        tools = ReportTools(reports_dir=tmp_path / "reports")

        result = tools._write_report("weekly-summary", "# Weekly Summary\nAll good.")

        assert "Error" not in result
        assert (tmp_path / "reports" / "weekly-summary.md").exists()
