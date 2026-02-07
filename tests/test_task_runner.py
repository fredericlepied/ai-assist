"""Tests for task runner"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.state import StateManager
from ai_assist.task_runner import TaskResult, TaskRunner
from ai_assist.tasks import TaskDefinition


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
def sample_task():
    """Create sample task definition"""
    return TaskDefinition(
        name="Test Task", prompt="Find failures in the system", interval="5m", description="A test task"
    )


@pytest.mark.asyncio
async def test_task_runner_success(mock_agent, state_manager, sample_task):
    """Test successful task execution"""
    mock_agent.query.return_value = "Found 5 failures in the last hour"

    runner = TaskRunner(sample_task, mock_agent, state_manager)
    result = await runner.run()

    assert result.success is True
    assert result.task_name == "Test Task"
    assert result.output == "Found 5 failures in the last hour"
    assert result.timestamp is not None
    assert mock_agent.query.called
    assert mock_agent.query.call_args[0][0] == "Find failures in the system"


@pytest.mark.asyncio
async def test_task_runner_failure(mock_agent, state_manager, sample_task):
    """Test task execution with error"""
    mock_agent.query.side_effect = Exception("API Error")

    runner = TaskRunner(sample_task, mock_agent, state_manager)
    result = await runner.run()

    assert result.success is False
    assert result.task_name == "Test Task"
    assert "API Error" in result.output
    assert result.timestamp is not None


@pytest.mark.asyncio
async def test_task_runner_state_tracking(mock_agent, state_manager, sample_task):
    """Test that task execution is tracked in state"""
    mock_agent.query.return_value = "Task completed successfully"

    runner = TaskRunner(sample_task, mock_agent, state_manager)
    await runner.run()

    # Check state was updated
    state = state_manager.get_monitor_state(runner.state_key)
    assert state.last_check is not None
    assert state.last_results["task_name"] == "Test Task"
    assert state.last_results["last_success"] is True


@pytest.mark.asyncio
async def test_task_runner_history(mock_agent, state_manager, sample_task):
    """Test that task execution is saved to history"""
    mock_agent.query.return_value = "Result 1"

    runner = TaskRunner(sample_task, mock_agent, state_manager)

    # Run task multiple times
    await runner.run()
    mock_agent.query.return_value = "Result 2"
    await runner.run()

    # Check history
    history = runner.get_history(limit=10)
    assert len(history) == 2
    assert history[0]["result"]["task_name"] == "Test Task"
    assert history[0]["result"]["success"] is True


@pytest.mark.asyncio
async def test_task_runner_state_key_sanitization(mock_agent, state_manager):
    """Test that task names are sanitized for state keys"""
    task = TaskDefinition(name="Test Task / With Special! Chars", prompt="Test", interval="5m")

    runner = TaskRunner(task, mock_agent, state_manager)
    state_key = runner._get_state_key()

    # Should only contain alphanumeric, dash, and underscore
    assert state_key == "task_Test_Task___With_Special__Chars"
    assert all(c.isalnum() or c in "-_" for c in state_key)


@pytest.mark.asyncio
async def test_task_runner_get_last_run(mock_agent, state_manager, sample_task):
    """Test getting last run timestamp"""
    mock_agent.query.return_value = "Test output"

    runner = TaskRunner(sample_task, mock_agent, state_manager)

    # Initially no last run
    assert runner.get_last_run() is None

    # After running, should have last run time
    await runner.run()
    last_run = runner.get_last_run()
    assert last_run is not None


@pytest.mark.asyncio
async def test_task_result_creation():
    """Test TaskResult dataclass creation"""
    from datetime import datetime

    result = TaskResult(
        task_name="Test", success=True, output="Test output", timestamp=datetime.now(), metadata={"count": 5}
    )

    assert result.task_name == "Test"
    assert result.success is True
    assert result.output == "Test output"
    assert result.metadata["count"] == 5


# Phase 4: MCP Prompt Task Execution Tests


@pytest.mark.asyncio
async def test_run_mcp_prompt_task(mock_agent, state_manager):
    """Test executing task with MCP prompt"""
    task = TaskDefinition(
        name="DCI RCA", prompt="mcp://dci/rca", interval="8:00 on weekdays", prompt_arguments={"days": "1"}
    )

    # Mock execute_mcp_prompt instead of query
    mock_agent.execute_mcp_prompt = AsyncMock(return_value="RCA analysis completed")

    runner = TaskRunner(task, mock_agent, state_manager)
    result = await runner.run()

    assert result.success is True
    assert result.output == "RCA analysis completed"
    mock_agent.execute_mcp_prompt.assert_called_once_with("dci", "rca", {"days": "1"})
    mock_agent.query.assert_not_called()


@pytest.mark.asyncio
async def test_run_mcp_prompt_without_arguments(mock_agent, state_manager):
    """Test executing MCP prompt task without arguments"""
    task = TaskDefinition(name="Simple Prompt", prompt="mcp://server/prompt", interval="1h")

    mock_agent.execute_mcp_prompt = AsyncMock(return_value="Prompt result")

    runner = TaskRunner(task, mock_agent, state_manager)
    result = await runner.run()

    assert result.success is True
    mock_agent.execute_mcp_prompt.assert_called_once_with("server", "prompt", None)


@pytest.mark.asyncio
async def test_run_natural_language_task_unchanged(mock_agent, state_manager):
    """Test that natural language tasks still work after MCP changes"""
    task = TaskDefinition(name="Natural Task", prompt="Find failures in the system", interval="1h")

    mock_agent.query.return_value = "Found 3 failures"

    runner = TaskRunner(task, mock_agent, state_manager)
    result = await runner.run()

    assert result.success is True
    assert result.output == "Found 3 failures"
    mock_agent.query.assert_called_once_with("Find failures in the system")


@pytest.mark.asyncio
async def test_run_mcp_prompt_invalid_server(mock_agent, state_manager):
    """Test handling of invalid MCP server"""
    task = TaskDefinition(name="Bad Server", prompt="mcp://invalid/prompt", interval="1h")

    mock_agent.execute_mcp_prompt = AsyncMock(side_effect=ValueError("MCP server 'invalid' not connected"))

    runner = TaskRunner(task, mock_agent, state_manager)
    result = await runner.run()

    assert result.success is False
    assert "MCP server 'invalid' not connected" in result.output


@pytest.mark.asyncio
async def test_run_mcp_prompt_invalid_arguments(mock_agent, state_manager):
    """Test handling of invalid MCP prompt arguments"""
    task = TaskDefinition(
        name="Bad Args", prompt="mcp://dci/rca", interval="1h", prompt_arguments={}  # Missing required args
    )

    mock_agent.execute_mcp_prompt = AsyncMock(side_effect=ValueError("Required argument 'days' missing"))

    runner = TaskRunner(task, mock_agent, state_manager)
    result = await runner.run()

    assert result.success is False
    assert "Required argument 'days' missing" in result.output
