"""Tests for unified OutputRenderer"""

from ai_assist.output import PlainRenderer


class TestPlainRenderer:
    def test_show_tool_call(self, capsys):
        renderer = PlainRenderer()
        renderer.show_tool_call("redhat__search_dci_jobs", {"query": "status=failure", "limit": 10})
        captured = capsys.readouterr()
        assert "redhat → search dci jobs" in captured.out
        assert "query=status=failure" in captured.out

    def test_show_tool_call_with_think(self, capsys):
        renderer = PlainRenderer()
        renderer.show_tool_call("internal__think", {"thought": "Let me plan.\nStep 1: check logs."})
        captured = capsys.readouterr()
        assert "internal → think" in captured.out
        assert "Let me plan." in captured.out
        assert "Step 1: check logs." in captured.out

    def test_show_inner_tool_call(self, capsys):
        renderer = PlainRenderer()
        renderer.show_inner_tool_call("internal__read_file", {"path": "/tmp/log.txt"})
        captured = capsys.readouterr()
        assert "internal → read file" in captured.out
        assert "path=/tmp/log.txt" in captured.out
        # Inner calls should be indented more than outer calls
        assert "  " in captured.out

    def test_show_progress(self):
        renderer = PlainRenderer()
        renderer.show_progress("thinking", "turn 1/10")
        # PlainRenderer progress is minimal -- should not crash

    def test_show_text_delta(self, capsys):
        renderer = PlainRenderer()
        renderer.show_text_delta("Hello ")
        renderer.show_text_delta("world")
        captured = capsys.readouterr()
        # PlainRenderer doesn't print streaming text (it comes from agent.query result)
        assert captured.out == ""

    def test_show_text_done(self, capsys):
        renderer = PlainRenderer()
        renderer.show_text_done()
        # Should not crash

    def test_show_warning(self, capsys):
        renderer = PlainRenderer()
        renderer.show_warning("Missing variable: x")
        captured = capsys.readouterr()
        assert "Missing variable: x" in captured.out

    def test_show_error(self, capsys):
        renderer = PlainRenderer()
        renderer.show_error("Connection failed")
        captured = capsys.readouterr()
        assert "Connection failed" in captured.out

    def test_show_tool_call_long_args_truncated(self, capsys):
        renderer = PlainRenderer()
        renderer.show_tool_call(
            "internal__execute_command",
            {"command": "x" * 200},
        )
        captured = capsys.readouterr()
        assert "..." in captured.out

    def test_on_inner_execution_text_ignored(self):
        """Inner execution text chunks should be silently ignored"""
        renderer = PlainRenderer()
        renderer.on_inner_execution("some text")  # Should not crash or print

    def test_on_inner_execution_tool_use(self, capsys):
        """Inner execution tool_use dicts should be displayed"""
        renderer = PlainRenderer()
        renderer.on_inner_execution({"type": "tool_use", "name": "redhat__search_dci_jobs", "input": {"query": "test"}})
        captured = capsys.readouterr()
        assert "redhat → search dci jobs" in captured.out

    def test_on_inner_execution_error(self, capsys):
        renderer = PlainRenderer()
        renderer.on_inner_execution({"type": "error", "message": "Something broke"})
        captured = capsys.readouterr()
        assert "Something broke" in captured.out

    def test_format_tool_args_plain(self):
        """Plain format should not use Rich markup escaping"""
        renderer = PlainRenderer()
        result = renderer._format_args({"path": "/tmp/[test].log"})
        assert "path=/tmp/[test].log" in result
