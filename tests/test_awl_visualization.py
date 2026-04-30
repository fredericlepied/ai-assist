"""Tests for AWL workflow visualization"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ai_assist.awl_ast import (
    FailNode,
    GoalNode,
    IfNode,
    LoopNode,
    NotifyNode,
    ReturnNode,
    SetNode,
    TaskNode,
    WaitNode,
    WhileNode,
    WorkflowNode,
)
from ai_assist.awl_visualization import (
    NODE_STYLES,
    discover_awl_scripts,
    generate_awl_html,
    open_awl_visualization,
)


@pytest.fixture
def simple_workflow():
    return WorkflowNode(
        body=[
            TaskNode(
                task_id="check_jobs",
                goal="Search for DCI jobs",
                hints=["no-history", "no-kg"],
                expose=["running_count"],
            ),
        ]
    )


@pytest.fixture
def complex_workflow():
    return WorkflowNode(
        max_steps=50,
        body=[
            SetNode(variable="prefix", value="Processing"),
            TaskNode(
                task_id="find_failures",
                goal="Search for failing jobs in the last 24 hours",
                hints=["no-history"],
                expose=["failed_jobs"],
                max_tool_calls=50,
            ),
            IfNode(
                expression="len(failed_jobs) > 0",
                then_body=[
                    LoopNode(
                        collection="failed_jobs",
                        item_var="job",
                        limit=5,
                        collect="analyses",
                        body=[
                            TaskNode(
                                task_id="analyze_failure",
                                goal="Classify the failure based on ${job}",
                                expose=["classification"],
                            ),
                        ],
                    ),
                    TaskNode(
                        task_id="write_report",
                        goal="Write a report from ${analyses}",
                    ),
                ],
                else_body=[
                    FailNode(message="No failures found"),
                ],
            ),
            ReturnNode(expression="analyses"),
        ],
    )


@pytest.fixture
def while_workflow():
    return WorkflowNode(
        body=[
            TaskNode(task_id="check", goal="Check status", expose=["count"]),
            WhileNode(
                expression="count > 0",
                max_iterations=24,
                body=[
                    NotifyNode(message="${count} jobs still running"),
                    WaitNode(duration_seconds=3600),
                    TaskNode(task_id="recheck", goal="Recheck status", expose=["count"]),
                ],
            ),
            NotifyNode(message="All jobs completed"),
        ],
    )


def test_generate_html_empty_workflow():
    workflow = WorkflowNode(body=[])
    html = generate_awl_html(workflow)
    assert "<html" in html
    assert "Empty Workflow" in html


def test_generate_html_simple(simple_workflow):
    html = generate_awl_html(simple_workflow, title="test.awl")
    assert "test.awl" in html
    assert "check_jobs" in html
    assert "no-history" in html
    assert "no-kg" in html
    assert "running_count" in html
    assert "1" in html  # 1 task


def test_generate_html_complex(complex_workflow):
    html = generate_awl_html(complex_workflow, title="complex.awl")
    assert "complex.awl" in html
    assert "find_failures" in html
    assert "analyze_failure" in html
    assert "write_report" in html
    assert "len(failed_jobs) &gt; 0" in html
    assert "then" in html
    assert "else" in html
    assert "loop" in html.lower()
    assert "failed_jobs" in html
    assert "limit=5" in html
    assert "collect=analyses" in html
    assert "return" in html
    assert "fail" in html.lower()
    assert "max_tool_calls=50" in html


def test_generate_html_while(while_workflow):
    html = generate_awl_html(while_workflow, title="monitor.awl")
    assert "while" in html.lower()
    assert "count &gt; 0" in html
    assert "max_iterations=24" in html
    assert "wait 1h" in html
    assert "notify" in html.lower()


def test_generate_html_goal_node():
    workflow = WorkflowNode(
        body=[
            GoalNode(
                goal_id="fix_issue",
                success_criteria="All tests pass",
                max_actions=10,
                body=[
                    TaskNode(task_id="diagnose", goal="Find the root cause"),
                    TaskNode(task_id="fix", goal="Apply the fix"),
                ],
            ),
        ]
    )
    html = generate_awl_html(workflow)
    assert "fix_issue" in html
    assert "All tests pass" in html
    assert "max_actions=10" in html


def test_generate_html_set_node():
    workflow = WorkflowNode(body=[SetNode(variable="x", value="hello")])
    html = generate_awl_html(workflow)
    assert "set x" in html
    assert "hello" in html


def test_generate_html_wait_formats():
    w_seconds = WorkflowNode(body=[WaitNode(duration_seconds=45)])
    assert "45s" in generate_awl_html(w_seconds)

    w_minutes = WorkflowNode(body=[WaitNode(duration_seconds=300)])
    assert "5m" in generate_awl_html(w_minutes)

    w_hours = WorkflowNode(body=[WaitNode(duration_seconds=7200)])
    assert "2h" in generate_awl_html(w_hours)


def test_generate_html_has_legend():
    workflow = WorkflowNode(body=[TaskNode(task_id="t", goal="g")])
    html = generate_awl_html(workflow)
    for style in NODE_STYLES.values():
        assert style["label"] in html


def test_generate_html_header_stats(complex_workflow):
    html = generate_awl_html(complex_workflow, title="stats.awl")
    assert "3" in html  # 3 tasks
    assert "Max steps" in html
    assert "50" in html


def test_generate_html_input_variables():
    workflow = WorkflowNode(
        body=[
            TaskNode(task_id="t", goal="Process ${quarter} of ${year}"),
        ]
    )
    html = generate_awl_html(workflow, title="vars.awl")
    assert "quarter" in html
    assert "year" in html


def test_task_details_toggle():
    workflow = WorkflowNode(
        body=[
            TaskNode(
                task_id="detailed",
                goal="The goal text",
                context="Some context",
                constraints="Some constraints",
                success="Success criteria",
            ),
        ]
    )
    html = generate_awl_html(workflow)
    assert "toggleDetails" in html
    assert "collapsed" in html
    assert "The goal text" in html
    assert "Some context" in html
    assert "Some constraints" in html
    assert "Success criteria" in html


def test_discover_awl_scripts(tmp_path):
    awl_dir = tmp_path / "workflows"
    awl_dir.mkdir()
    (awl_dir / "test1.awl").write_text("@start\n@end")
    (awl_dir / "test2.awl").write_text("@start\n@end")
    (awl_dir / "not_awl.txt").write_text("nope")

    nested = awl_dir / "sub"
    nested.mkdir()
    (nested / "test3.awl").write_text("@start\n@end")

    with patch("ai_assist.awl_visualization.Path") as mock_path_cls:

        class FakePath:
            def __init__(self, *a, **kw):
                pass

            @staticmethod
            def cwd():
                return tmp_path

        mock_path_cls.cwd.return_value = tmp_path

    with (
        patch("ai_assist.awl_visualization.Path.cwd", return_value=tmp_path),
        patch("ai_assist.awl_visualization.get_config_dir", return_value=tmp_path / "no-config"),
    ):
        scripts = discover_awl_scripts()

    assert len(scripts) == 3
    names = {s.name for s in scripts}
    assert names == {"test1.awl", "test2.awl", "test3.awl"}


def test_discover_awl_scripts_with_skills_cache(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    skills_cache = config_dir / "skills-cache"
    skill_dir = skills_cache / "my-skill" / "scripts"
    skill_dir.mkdir(parents=True)
    (skill_dir / "workflow.awl").write_text("@start\n@end")

    with (
        patch("ai_assist.awl_visualization.Path.cwd", return_value=tmp_path / "empty-cwd"),
        patch("ai_assist.awl_visualization.get_config_dir", return_value=config_dir),
    ):
        scripts = discover_awl_scripts()

    assert len(scripts) == 1
    assert scripts[0].name == "workflow.awl"


def test_discover_awl_scripts_deduplication(tmp_path):
    awl_file = tmp_path / "test.awl"
    awl_file.write_text("@start\n@end")

    with (
        patch("ai_assist.awl_visualization.Path.cwd", return_value=tmp_path),
        patch("ai_assist.awl_visualization.get_config_dir", return_value=tmp_path),
    ):
        scripts = discover_awl_scripts()

    assert len(scripts) == 1


@patch("webbrowser.open")
def test_open_awl_visualization(mock_open, tmp_path):
    awl_file = tmp_path / "test.awl"
    awl_file.write_text("@start\n@task hello\nGoal: Say hello\nExpose: greeting\n@end\n@end")

    with patch("ai_assist.awl_visualization.get_config_dir", return_value=tmp_path):
        filepath = open_awl_visualization(str(awl_file))

    assert filepath.endswith(".html")
    mock_open.assert_called_once()
    content = Path(filepath).read_text()
    assert "<html" in content
    assert "hello" in content
    assert "greeting" in content


@patch("webbrowser.open")
def test_open_awl_visualization_file_not_found(mock_open):
    with pytest.raises(FileNotFoundError):
        open_awl_visualization("/nonexistent/path/script.awl")
    mock_open.assert_not_called()


def test_node_styles_coverage():
    expected = ["task", "if", "loop", "while", "wait", "notify", "set", "return", "fail", "goal"]
    for node_type in expected:
        assert node_type in NODE_STYLES
        assert "color" in NODE_STYLES[node_type]
        assert "bg" in NODE_STYLES[node_type]
        assert "icon" in NODE_STYLES[node_type]
        assert "label" in NODE_STYLES[node_type]
