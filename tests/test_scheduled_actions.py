"""Tests for scheduled actions system"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.config import get_config_dir
from ai_assist.schedule_action_tools import ScheduleActionTools, parse_time_spec
from ai_assist.scheduled_actions import ScheduledAction, ScheduledActionManager


@pytest.mark.asyncio
async def test_save_and_load_scheduled_action(tmp_path):
    """Test saving and loading scheduled actions"""
    action_file = tmp_path / "scheduled-actions.json"

    action = ScheduledAction(
        id="test-123",
        prompt="Check DCI job status for job-456",
        scheduled_at=datetime.now() + timedelta(hours=2),
        created_at=datetime.now(),
        created_by="agent",
        description="Follow up on DCI job",
        notification_channels=["console"],
        status="pending",
    )

    # Create mock agent
    mock_agent = MagicMock()

    manager = ScheduledActionManager(action_file, mock_agent)
    await manager.save_action(action)

    # Verify file exists
    assert action_file.exists()

    # Load actions
    loaded = await manager.load_actions()
    assert len(loaded) == 1
    assert loaded[0].id == "test-123"
    assert loaded[0].status == "pending"
    assert loaded[0].prompt == "Check DCI job status for job-456"


@pytest.mark.asyncio
async def test_multiple_actions(tmp_path):
    """Test saving multiple actions"""
    action_file = tmp_path / "scheduled-actions.json"
    mock_agent = MagicMock()

    manager = ScheduledActionManager(action_file, mock_agent)

    # Create multiple actions
    action1 = ScheduledAction(
        id="test-1",
        prompt="Action 1",
        scheduled_at=datetime.now() + timedelta(hours=1),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
    )

    action2 = ScheduledAction(
        id="test-2",
        prompt="Action 2",
        scheduled_at=datetime.now() + timedelta(hours=2),
        created_at=datetime.now(),
        created_by="agent",
        notification_channels=["desktop"],
        status="pending",
    )

    await manager.save_action(action1)
    await manager.save_action(action2)

    # Load and verify
    loaded = await manager.load_actions()
    assert len(loaded) == 2
    assert {a.id for a in loaded} == {"test-1", "test-2"}


@pytest.mark.asyncio
async def test_get_action_by_id(tmp_path):
    """Test retrieving a specific action by ID"""
    action_file = tmp_path / "scheduled-actions.json"
    mock_agent = MagicMock()

    manager = ScheduledActionManager(action_file, mock_agent)

    action = ScheduledAction(
        id="test-456",
        prompt="Test action",
        scheduled_at=datetime.now() + timedelta(hours=1),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
    )

    await manager.save_action(action)

    # Get by ID
    retrieved = await manager.get_action("test-456")
    assert retrieved is not None
    assert retrieved.id == "test-456"
    assert retrieved.prompt == "Test action"

    # Get non-existent
    not_found = await manager.get_action("non-existent")
    assert not_found is None


@pytest.mark.asyncio
async def test_execute_due_action(tmp_path):
    """Test that due actions are executed"""
    action_file = tmp_path / "scheduled-actions.json"

    action = ScheduledAction(
        id="test-exec",
        prompt="What are the latest DCI jobs?",
        scheduled_at=datetime.now() - timedelta(seconds=5),  # Past due
        created_at=datetime.now() - timedelta(minutes=10),
        created_by="agent",
        notification_channels=["console"],
        status="pending",
        execute_query=True,  # Execute via agent
        notify=False,  # Disable notifications for test
    )

    # Create mock agent
    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="Result: 3 jobs found")

    manager = ScheduledActionManager(action_file, mock_agent)
    await manager.save_action(action)

    # Run executor once
    await manager.execute_due_actions()

    # Verify action executed
    executed = await manager.get_action("test-exec")
    assert executed.status == "completed"
    assert "3 jobs found" in executed.result
    mock_agent.query.assert_called_once_with("What are the latest DCI jobs?")
    assert executed.executed_at is not None


@pytest.mark.asyncio
async def test_execute_not_due_action(tmp_path):
    """Test that future actions are not executed"""
    action_file = tmp_path / "scheduled-actions.json"

    action = ScheduledAction(
        id="test-future",
        prompt="Future action",
        scheduled_at=datetime.now() + timedelta(hours=1),  # Future
        created_at=datetime.now(),
        created_by="agent",
        notification_channels=["console"],
        status="pending",
    )

    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="Should not be called")

    manager = ScheduledActionManager(action_file, mock_agent)
    await manager.save_action(action)

    # Run executor once
    await manager.execute_due_actions()

    # Verify action NOT executed
    not_executed = await manager.get_action("test-future")
    assert not_executed.status == "pending"
    assert not_executed.result is None
    mock_agent.query.assert_not_called()


@pytest.mark.asyncio
async def test_action_execution_failure(tmp_path):
    """Test that failed actions are marked as failed"""
    action_file = tmp_path / "scheduled-actions.json"

    action = ScheduledAction(
        id="test-fail",
        prompt="Failing action",
        scheduled_at=datetime.now() - timedelta(seconds=5),  # Past due
        created_at=datetime.now(),
        created_by="agent",
        notification_channels=["console"],
        status="pending",
        execute_query=True,  # Execute via agent (which will fail)
        notify=False,  # Disable notifications for test
    )

    # Create mock agent that raises exception
    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(side_effect=Exception("Test error"))

    manager = ScheduledActionManager(action_file, mock_agent)
    await manager.save_action(action)

    # Run executor once
    await manager.execute_due_actions()

    # Verify action marked as failed
    failed = await manager.get_action("test-fail")
    assert failed.status == "failed"
    assert "Test error" in failed.result
    assert failed.executed_at is not None


@pytest.mark.asyncio
async def test_reminder_only_action_no_agent_call(tmp_path):
    """Test that reminder-only actions don't call the agent"""
    action_file = tmp_path / "scheduled-actions.json"

    action = ScheduledAction(
        id="test-reminder",
        prompt="Time to watch TV! 📺",
        scheduled_at=datetime.now() - timedelta(seconds=5),  # Past due
        created_at=datetime.now(),
        created_by="agent",
        description="TV reminder",
        notification_channels=["console"],
        status="pending",
        execute_query=False,  # Simple reminder, no agent query
        notify=True,
        create_report=False,
    )

    # Create mock agent
    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="Should not be called")

    manager = ScheduledActionManager(action_file, mock_agent)
    await manager.save_action(action)

    # Run executor once
    await manager.execute_due_actions()

    # Verify action completed WITHOUT calling agent
    executed = await manager.get_action("test-reminder")
    assert executed.status == "completed"
    assert executed.result == "Time to watch TV! 📺"  # Prompt used as result
    mock_agent.query.assert_not_called()  # Agent should NOT be called for reminders
    assert executed.executed_at is not None


@pytest.mark.asyncio
async def test_query_action_calls_agent(tmp_path):
    """Test that query actions DO call the agent"""
    action_file = tmp_path / "scheduled-actions.json"

    action = ScheduledAction(
        id="test-query",
        prompt="Search for unread emails in Gmail",
        scheduled_at=datetime.now() - timedelta(seconds=5),  # Past due
        created_at=datetime.now(),
        created_by="agent",
        description="Check Gmail",
        notification_channels=["console"],
        status="pending",
        execute_query=True,  # Execute via agent
        notify=True,
        create_report=False,
    )

    # Create mock agent
    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="Found 3 unread emails")

    manager = ScheduledActionManager(action_file, mock_agent)
    await manager.save_action(action)

    # Run executor once
    await manager.execute_due_actions()

    # Verify action executed VIA agent
    executed = await manager.get_action("test-query")
    assert executed.status == "completed"
    assert executed.result == "Found 3 unread emails"  # Agent result
    mock_agent.query.assert_called_once_with("Search for unread emails in Gmail")
    assert executed.executed_at is not None


def test_parse_time_spec():
    """Test natural language time parsing"""
    now = datetime.now()

    # Test "in X hours"
    result = parse_time_spec("in 2 hours")
    assert result is not None
    diff = (result - now).total_seconds()
    assert 7190 < diff < 7210  # ~2 hours (allowing small drift)

    # Test "in X minutes"
    result = parse_time_spec("in 30 minutes")
    assert result is not None
    diff = (result - now).total_seconds()
    assert 1790 < diff < 1810  # ~30 minutes

    # Test "in X days"
    result = parse_time_spec("in 1 day")
    assert result is not None
    diff = (result - now).total_seconds()
    assert 86390 < diff < 86410  # ~24 hours

    # Test short forms
    result = parse_time_spec("in 3h")
    assert result is not None

    result = parse_time_spec("in 15m")
    assert result is not None

    result = parse_time_spec("in 2d")
    assert result is not None

    # Test "tomorrow at HH:MM"
    result = parse_time_spec("tomorrow at 9:00")
    assert result is not None
    assert result.hour == 9
    assert result.minute == 0
    assert result.day == (now + timedelta(days=1)).day

    # Test invalid
    result = parse_time_spec("invalid time spec")
    assert result is None


@pytest.mark.asyncio
async def test_schedule_action_tool(tmp_path):
    """Test that agent can schedule action via internal tool"""
    # Override config dir for test
    import ai_assist.schedule_action_tools

    original_action_file = ai_assist.schedule_action_tools.get_config_dir

    def mock_config_dir():
        return tmp_path

    ai_assist.schedule_action_tools.get_config_dir = mock_config_dir

    try:
        mock_agent = MagicMock()
        tools = ScheduleActionTools(mock_agent)

        # Agent calls tool (with explicit parameters)
        result = await tools.schedule_action(
            prompt="Check DCI job status for job-789",
            time_spec="in 2 hours",
            description="Follow up on DCI job",
            execute_query=True,  # Agent decides to query
            notify=True,
            create_report=False,
        )

        assert "scheduled" in result.lower()
        # Should show time (might be 1h 59m due to execution timing)
        assert "1h" in result or "2h" in result or "2 hours" in result

        # Verify action was created
        action_file = tmp_path / "scheduled-actions.json"
        assert action_file.exists()

        # Load and verify
        manager = ScheduledActionManager(action_file, mock_agent)
        actions = await manager.load_actions()
        assert len(actions) == 1
        assert actions[0].prompt == "Check DCI job status for job-789"
        assert actions[0].status == "pending"

    finally:
        # Restore
        ai_assist.schedule_action_tools.get_config_dir = original_action_file


@pytest.mark.asyncio
async def test_schedule_action_agent_parameters(tmp_path):
    """Test that schedule action tool respects agent's parameter choices"""
    import ai_assist.schedule_action_tools

    def mock_config_dir():
        return tmp_path

    ai_assist.schedule_action_tools.get_config_dir = mock_config_dir

    try:
        mock_agent = MagicMock()
        tools = ScheduleActionTools(mock_agent)
        manager = ScheduledActionManager(tmp_path / "scheduled-actions.json", mock_agent)

        # Test: Simple reminder (agent decides execute_query=False)
        await tools.schedule_action(
            prompt="Time to watch TV",
            time_spec="in 1 hour",
            execute_query=False,
            notify=True,
            create_report=False,
        )
        actions = await manager.load_actions()
        assert actions[-1].execute_query is False
        assert actions[-1].notify is True
        assert actions[-1].create_report is False

        # Test: Query with notification (agent decides execute_query=True)
        await tools.schedule_action(
            prompt="Check unread Gmail emails",
            time_spec="in 1 hour",
            execute_query=True,
            notify=True,
            create_report=False,
        )
        actions = await manager.load_actions()
        assert actions[-1].execute_query is True
        assert actions[-1].notify is True
        assert actions[-1].create_report is False

        # Test: Query with report (agent decides create_report=True)
        await tools.schedule_action(
            prompt="Analyze DCI failures",
            time_spec="in 1 hour",
            execute_query=True,
            notify=False,
            create_report=True,
        )
        actions = await manager.load_actions()
        assert actions[-1].execute_query is True
        assert actions[-1].notify is False
        assert actions[-1].create_report is True

    finally:
        ai_assist.schedule_action_tools.get_config_dir = get_config_dir


@pytest.mark.asyncio
async def test_cleanup_old_actions(tmp_path):
    """Test that old completed actions are archived"""
    action_file = tmp_path / "scheduled-actions.json"
    archive_file = tmp_path / "scheduled-actions-archive.jsonl"

    # Create actions: 1 old completed, 1 recent completed, 1 pending
    old_completed = ScheduledAction(
        id="old-1",
        prompt="Old action",
        scheduled_at=datetime.now() - timedelta(days=10),
        created_at=datetime.now() - timedelta(days=10),
        created_by="agent",
        execute_query=False,
        notify=False,
        status="completed",
        result="Done",
        executed_at=datetime.now() - timedelta(days=10),
    )

    recent_completed = ScheduledAction(
        id="recent-1",
        prompt="Recent action",
        scheduled_at=datetime.now() - timedelta(days=2),
        created_at=datetime.now() - timedelta(days=2),
        created_by="agent",
        execute_query=False,
        notify=False,
        status="completed",
        result="Done",
        executed_at=datetime.now() - timedelta(days=2),
    )

    pending = ScheduledAction(
        id="pending-1",
        prompt="Pending action",
        scheduled_at=datetime.now() + timedelta(hours=1),
        created_at=datetime.now() - timedelta(days=15),  # Old but pending
        created_by="agent",
        execute_query=False,
        notify=False,
        status="pending",
    )

    mock_agent = MagicMock()
    manager = ScheduledActionManager(action_file, mock_agent)
    manager.actions = [old_completed, recent_completed, pending]
    await manager._persist()

    # Run cleanup (max_age_days=7)
    archived_count = await manager.cleanup_old_actions(max_age_days=7)

    # Verify results
    assert archived_count == 1  # Only old_completed was archived
    assert len(manager.actions) == 2  # recent_completed + pending
    assert {a.id for a in manager.actions} == {"recent-1", "pending-1"}

    # Verify archive file exists with correct format
    assert archive_file.exists()

    with open(archive_file) as f:
        lines = f.readlines()
        assert len(lines) == 1

        archived_action = json.loads(lines[0])
        assert archived_action["id"] == "old-1"
        assert archived_action["status"] == "completed"


@pytest.mark.asyncio
async def test_cleanup_never_archives_pending(tmp_path):
    """Test that pending actions are never archived regardless of age"""
    action_file = tmp_path / "scheduled-actions.json"

    # Old pending action (created 30 days ago)
    old_pending = ScheduledAction(
        id="old-pending",
        prompt="Very old pending action",
        scheduled_at=datetime.now() + timedelta(hours=1),
        created_at=datetime.now() - timedelta(days=30),
        created_by="agent",
        execute_query=False,
        notify=False,
        status="pending",
    )

    mock_agent = MagicMock()
    manager = ScheduledActionManager(action_file, mock_agent)
    manager.actions = [old_pending]
    await manager._persist()

    # Run cleanup
    archived_count = await manager.cleanup_old_actions(max_age_days=7)

    # Verify pending action was NOT archived
    assert archived_count == 0
    assert len(manager.actions) == 1
    assert manager.actions[0].id == "old-pending"


@pytest.mark.asyncio
async def test_cleanup_appends_to_existing_archive(tmp_path):
    """Test that cleanup appends to existing archive file (JSONL)"""
    action_file = tmp_path / "scheduled-actions.json"
    archive_file = tmp_path / "scheduled-actions-archive.jsonl"

    # Create existing archive with one entry
    existing_entry = {"id": "existing-1", "prompt": "Old entry", "status": "completed"}
    with open(archive_file, "w") as f:
        f.write(json.dumps(existing_entry) + "\n")

    # Add new old action to archive
    old_action = ScheduledAction(
        id="old-2",
        prompt="Another old action",
        scheduled_at=datetime.now() - timedelta(days=10),
        created_at=datetime.now() - timedelta(days=10),
        created_by="agent",
        execute_query=False,
        notify=False,
        status="completed",
        result="Done",
        executed_at=datetime.now() - timedelta(days=10),
    )

    mock_agent = MagicMock()
    manager = ScheduledActionManager(action_file, mock_agent)
    manager.actions = [old_action]
    await manager._persist()

    # Run cleanup
    await manager.cleanup_old_actions(max_age_days=7)

    # Verify both entries in archive
    with open(archive_file) as f:
        lines = f.readlines()
        assert len(lines) == 2

        # First line: existing entry
        assert json.loads(lines[0])["id"] == "existing-1"

        # Second line: newly archived
        assert json.loads(lines[1])["id"] == "old-2"


@pytest.mark.asyncio
async def test_cleanup_no_actions_to_archive(tmp_path):
    """Test cleanup when no actions need archiving"""
    action_file = tmp_path / "scheduled-actions.json"
    archive_file = tmp_path / "scheduled-actions-archive.jsonl"

    # Only recent completed actions
    recent = ScheduledAction(
        id="recent-1",
        prompt="Recent action",
        scheduled_at=datetime.now() - timedelta(days=2),
        created_at=datetime.now() - timedelta(days=2),
        created_by="agent",
        execute_query=False,
        notify=False,
        status="completed",
        result="Done",
        executed_at=datetime.now() - timedelta(days=2),
    )

    mock_agent = MagicMock()
    manager = ScheduledActionManager(action_file, mock_agent)
    manager.actions = [recent]
    await manager._persist()

    # Run cleanup
    archived_count = await manager.cleanup_old_actions(max_age_days=7)

    # Verify nothing archived
    assert archived_count == 0
    assert len(manager.actions) == 1
    assert not archive_file.exists()  # No archive file created


@pytest.mark.asyncio
async def test_cleanup_runs_after_action_execution(tmp_path):
    """Test that cleanup runs automatically after action execution"""
    action_file = tmp_path / "scheduled-actions.json"
    archive_file = tmp_path / "scheduled-actions-archive.jsonl"

    # Create one old completed action and one due action
    old_completed = ScheduledAction(
        id="old-1",
        prompt="Old completed action",
        scheduled_at=datetime.now() - timedelta(days=10),
        created_at=datetime.now() - timedelta(days=10),
        created_by="agent",
        execute_query=False,
        notify=False,
        status="completed",
        result="Done",
        executed_at=datetime.now() - timedelta(days=10),
    )

    due_action = ScheduledAction(
        id="due-1",
        prompt="Due action",
        scheduled_at=datetime.now() - timedelta(seconds=5),  # Past due
        created_at=datetime.now(),
        created_by="agent",
        execute_query=False,
        notify=False,
        status="pending",
    )

    mock_agent = MagicMock()
    manager = ScheduledActionManager(action_file, mock_agent)
    manager.actions = [old_completed, due_action]
    await manager._persist()

    # Execute due actions (which should trigger cleanup)
    await manager.execute_due_actions()

    # Verify:
    # 1. Due action was executed
    executed = await manager.get_action("due-1")
    assert executed.status == "completed"

    # 2. Old action was archived
    assert archive_file.exists()
    with open(archive_file) as f:
        lines = f.readlines()
        assert len(lines) == 1
        archived = json.loads(lines[0])
        assert archived["id"] == "old-1"

    # 3. Only recent completed action remains in main file
    assert len(manager.actions) == 1
    assert manager.actions[0].id == "due-1"
