"""Tests for scheduler integration with user-defined tasks"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from ai_assist.monitors import MonitoringScheduler
from ai_assist.state import StateManager


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create temporary state directory"""
    return tmp_path / "state"


@pytest.fixture
def state_manager(temp_state_dir):
    """Create state manager with temp directory"""
    return StateManager(state_dir=temp_state_dir)


@pytest.fixture
def mock_agent():
    """Create mock agent"""
    agent = MagicMock()
    agent.query = AsyncMock()
    return agent


@pytest.fixture
def mock_config():
    """Create mock config"""
    config = MagicMock()
    config.monitoring.jira_projects = []
    config.monitoring.dci_queries = []
    config.monitoring.jira_check_interval = 300
    config.monitoring.dci_check_interval = 300
    return config


@pytest.fixture
def sample_tasks_yaml(tmp_path):
    """Create sample tasks.yaml file"""
    yaml_content = """
tasks:
  - name: "Test Task 1"
    interval: 1m
    prompt: "Check for failures"
    enabled: true

  - name: "Test Task 2"
    interval: 5m
    prompt: "Generate summary"
    enabled: true

  - name: "Disabled Task"
    interval: 1m
    prompt: "This should not run"
    enabled: false
"""
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text(yaml_content)
    return tasks_file


def test_load_user_tasks(mock_agent, mock_config, state_manager, sample_tasks_yaml):
    """Test loading user tasks from YAML"""
    scheduler = MonitoringScheduler(
        mock_agent,
        mock_config,
        state_manager,
        knowledge_graph=None,
        task_file=sample_tasks_yaml
    )

    # Should load 2 enabled tasks
    assert len(scheduler.user_tasks) == 2
    assert scheduler.user_tasks[0].task_def.name == "Test Task 1"
    assert scheduler.user_tasks[1].task_def.name == "Test Task 2"


def test_load_user_tasks_nonexistent_file(mock_agent, mock_config, state_manager):
    """Test loading tasks from non-existent file"""
    scheduler = MonitoringScheduler(
        mock_agent,
        mock_config,
        state_manager,
        knowledge_graph=None,
        task_file=Path("/nonexistent/tasks.yaml")
    )

    # Should handle gracefully with no tasks
    assert len(scheduler.user_tasks) == 0


def test_load_user_tasks_no_file(mock_agent, mock_config, state_manager):
    """Test scheduler without task file"""
    scheduler = MonitoringScheduler(
        mock_agent,
        mock_config,
        state_manager,
        knowledge_graph=None,
        task_file=None
    )

    # Should work without user tasks
    assert len(scheduler.user_tasks) == 0


def test_load_user_tasks_invalid_yaml(mock_agent, mock_config, state_manager, tmp_path):
    """Test loading invalid YAML"""
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text("invalid: yaml: content:")

    scheduler = MonitoringScheduler(
        mock_agent,
        mock_config,
        state_manager,
        knowledge_graph=None,
        task_file=invalid_file
    )

    # Should handle error gracefully
    assert len(scheduler.user_tasks) == 0


def test_task_intervals_converted_correctly(mock_agent, mock_config, state_manager, tmp_path):
    """Test that task intervals are converted to seconds correctly"""
    yaml_content = """
tasks:
  - name: "30 Second Task"
    interval: 30s
    prompt: "Quick check"

  - name: "5 Minute Task"
    interval: 5m
    prompt: "Regular check"

  - name: "1 Hour Task"
    interval: 1h
    prompt: "Hourly check"
"""
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text(yaml_content)

    scheduler = MonitoringScheduler(
        mock_agent,
        mock_config,
        state_manager,
        knowledge_graph=None,
        task_file=tasks_file
    )

    assert len(scheduler.user_tasks) == 3
    assert scheduler.user_tasks[0].task_def.interval_seconds == 30
    assert scheduler.user_tasks[1].task_def.interval_seconds == 300
    assert scheduler.user_tasks[2].task_def.interval_seconds == 3600
