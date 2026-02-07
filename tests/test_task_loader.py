"""Tests for task definition loading"""

from pathlib import Path

import pytest

from ai_assist.tasks import TaskDefinition, TaskLoader


def test_parse_interval_seconds():
    """Test parsing seconds"""
    loader = TaskLoader()
    assert loader.parse_interval("30s") == 30
    assert loader.parse_interval("60s") == 60


def test_parse_interval_minutes():
    """Test parsing minutes"""
    loader = TaskLoader()
    assert loader.parse_interval("5m") == 300
    assert loader.parse_interval("10m") == 600


def test_parse_interval_hours():
    """Test parsing hours"""
    loader = TaskLoader()
    assert loader.parse_interval("1h") == 3600
    assert loader.parse_interval("2h") == 7200


def test_parse_interval_combined():
    """Test parsing combined intervals"""
    loader = TaskLoader()
    assert loader.parse_interval("1h30m") == 5400
    assert loader.parse_interval("2h30m") == 9000
    assert loader.parse_interval("1h5m30s") == 3930


def test_parse_interval_case_insensitive():
    """Test that interval parsing is case insensitive"""
    loader = TaskLoader()
    assert loader.parse_interval("5M") == 300
    assert loader.parse_interval("1H") == 3600


def test_parse_interval_invalid():
    """Test invalid interval formats"""
    loader = TaskLoader()

    with pytest.raises(ValueError, match="Invalid interval format"):
        loader.parse_interval("invalid")

    with pytest.raises(ValueError, match="Invalid interval format"):
        loader.parse_interval("abc")

    with pytest.raises(ValueError, match="Interval cannot be empty"):
        loader.parse_interval("")


def test_load_yaml_basic():
    """Test loading basic YAML task definition"""
    yaml_content = """
tasks:
  - name: "Test Task"
    interval: 5m
    prompt: "Test prompt"
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert len(tasks) == 1
    assert tasks[0].name == "Test Task"
    assert tasks[0].interval == "5m"
    assert tasks[0].interval_seconds == 300
    assert tasks[0].prompt == "Test prompt"
    assert tasks[0].enabled is True
    assert tasks[0].description is None


def test_load_yaml_full_definition():
    """Test loading full task definition with all fields"""
    yaml_content = """
tasks:
  - name: "Full Task"
    description: "A full test task"
    interval: 10m
    enabled: true
    prompt: |
      Multi-line prompt
      with multiple lines
    conditions:
      - if: "count > 5"
        then:
          action: notify
          message: "Found {count} items"
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.name == "Full Task"
    assert task.description == "A full test task"
    assert task.interval_seconds == 600
    assert "Multi-line prompt" in task.prompt
    assert task.enabled is True
    assert len(task.conditions) == 1
    assert task.conditions[0]["if"] == "count > 5"


def test_load_yaml_multiple_tasks():
    """Test loading multiple tasks"""
    yaml_content = """
tasks:
  - name: "Task 1"
    interval: 5m
    prompt: "First task"

  - name: "Task 2"
    interval: 10m
    prompt: "Second task"
    enabled: false
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert len(tasks) == 2
    assert tasks[0].name == "Task 1"
    assert tasks[0].enabled is True
    assert tasks[1].name == "Task 2"
    assert tasks[1].enabled is False


def test_load_yaml_disabled_task():
    """Test that disabled tasks are loaded but marked as disabled"""
    yaml_content = """
tasks:
  - name: "Disabled Task"
    interval: 5m
    prompt: "This task is disabled"
    enabled: false
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert len(tasks) == 1
    assert tasks[0].enabled is False


def test_load_yaml_missing_required_field():
    """Test error handling for missing required fields"""
    yaml_content = """
tasks:
  - name: "Incomplete Task"
    interval: 5m
"""
    loader = TaskLoader()

    with pytest.raises(ValueError, match="Missing required field"):
        loader.load_from_yaml_string(yaml_content)


def test_load_yaml_invalid_interval():
    """Test error handling for invalid interval"""
    yaml_content = """
tasks:
  - name: "Bad Interval Task"
    interval: "invalid"
    prompt: "Test prompt"
"""
    loader = TaskLoader()

    with pytest.raises(ValueError, match="Invalid interval"):
        loader.load_from_yaml_string(yaml_content)


def test_load_yaml_empty_file():
    """Test loading empty YAML file"""
    yaml_content = ""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert tasks == []


def test_load_yaml_no_tasks_key():
    """Test loading YAML without tasks key"""
    yaml_content = """
other_data:
  - some: value
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert tasks == []


def test_load_from_file_not_exists():
    """Test loading from non-existent file"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml(Path("/nonexistent/path.yaml"))

    assert tasks == []


def test_task_definition_validation():
    """Test task definition validation"""
    # Valid task
    task = TaskDefinition(name="Valid Task", prompt="Test prompt", interval="5m")
    task.validate()  # Should not raise

    # Invalid: no name
    with pytest.raises(ValueError, match="Task name is required"):
        task = TaskDefinition(name="", prompt="Test", interval="5m")
        task.validate()

    # Invalid: no prompt
    with pytest.raises(ValueError, match="Task prompt is required"):
        task = TaskDefinition(name="Test", prompt="", interval="5m")
        task.validate()

    # Invalid: no interval
    with pytest.raises(ValueError, match="Task interval is required"):
        task = TaskDefinition(name="Test", prompt="Test", interval="")
        task.validate()


# Phase 1: MCP Prompt Schema Tests


def test_is_mcp_prompt_true():
    """Test detection of MCP prompt references"""
    task = TaskDefinition(name="Test", prompt="mcp://dci/rca", interval="5m")
    assert task.is_mcp_prompt is True


def test_is_mcp_prompt_false():
    """Test detection of natural language prompts"""
    task = TaskDefinition(name="Test", prompt="Find failures in the system", interval="5m")
    assert task.is_mcp_prompt is False


def test_parse_mcp_prompt_valid():
    """Test parsing valid MCP prompt reference"""
    task = TaskDefinition(name="Test", prompt="mcp://dci/rca", interval="5m")
    server, prompt = task.parse_mcp_prompt()
    assert server == "dci"
    assert prompt == "rca"


def test_parse_mcp_prompt_invalid_no_slash():
    """Test rejection of MCP prompt without slash"""
    task = TaskDefinition(name="Test", prompt="mcp://dci", interval="5m")
    with pytest.raises(ValueError, match="must be 'mcp://server/prompt'"):
        task.parse_mcp_prompt()


def test_parse_mcp_prompt_invalid_empty_parts():
    """Test rejection of MCP prompt with empty parts"""
    task1 = TaskDefinition(name="Test", prompt="mcp:///prompt", interval="5m")
    with pytest.raises(ValueError, match="must be 'mcp://server/prompt'"):
        task1.parse_mcp_prompt()

    task2 = TaskDefinition(name="Test", prompt="mcp://server/", interval="5m")
    with pytest.raises(ValueError, match="must be 'mcp://server/prompt'"):
        task2.parse_mcp_prompt()


def test_parse_mcp_prompt_natural_language_raises():
    """Test that parsing natural language prompt raises error"""
    task = TaskDefinition(name="Test", prompt="Find failures", interval="5m")
    with pytest.raises(ValueError, match="Not an MCP prompt reference"):
        task.parse_mcp_prompt()


def test_validate_mcp_prompt_format():
    """Test validation catches malformed MCP prompts"""
    # Invalid format should fail validation
    task = TaskDefinition(name="Test", prompt="mcp://invalid", interval="5m")
    with pytest.raises(ValueError, match="Invalid MCP prompt reference"):
        task.validate()


def test_backward_compatibility_natural_language():
    """Test that existing natural language prompts still work"""
    task = TaskDefinition(name="Legacy Task", prompt="Find system failures in the last 24 hours", interval="1h")
    task.validate()  # Should not raise
    assert task.is_mcp_prompt is False


def test_load_task_with_prompt_arguments():
    """Test loading task with prompt_arguments from YAML"""
    yaml_content = """
tasks:
  - name: "MCP Task"
    prompt: "mcp://dci/rca"
    interval: "8:00 on weekdays"
    prompt_arguments:
      days: "1"
      status: "failure"
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.name == "MCP Task"
    assert task.prompt == "mcp://dci/rca"
    assert task.prompt_arguments == {"days": "1", "status": "failure"}


def test_load_task_without_prompt_arguments():
    """Test that prompt_arguments defaults to None when not specified"""
    yaml_content = """
tasks:
  - name: "Regular Task"
    prompt: "Find failures"
    interval: "1h"
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert len(tasks) == 1
    assert tasks[0].prompt_arguments is None


def test_mcp_prompt_with_nested_path():
    """Test MCP prompts with paths containing slashes"""
    task = TaskDefinition(name="Test", prompt="mcp://server/category/subcategory/prompt", interval="5m")
    server, prompt = task.parse_mcp_prompt()
    assert server == "server"
    assert prompt == "category/subcategory/prompt"
