"""Tests for internal schedule management tools"""

import json
import tempfile
from pathlib import Path

import pytest

from ai_assist.schedule_tools import ScheduleTools


@pytest.fixture
def temp_schedules():
    """Create a temporary schedules file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "schedules.json"


@pytest.fixture
def schedule_tools(temp_schedules):
    """Create ScheduleTools instance with temp file"""
    return ScheduleTools(schedules_file=temp_schedules)


class TestScheduleTools:
    """Tests for ScheduleTools class"""

    def test_initialization(self, schedule_tools, temp_schedules):
        """Test that ScheduleTools initializes correctly"""
        assert schedule_tools.schedules_file == temp_schedules
        assert temp_schedules.parent.exists()

    def test_get_tool_definitions(self, schedule_tools):
        """Test that tool definitions are returned"""
        tools = schedule_tools.get_tool_definitions()
        assert len(tools) == 7
        assert all(tool["_server"] == "internal" for tool in tools)

        tool_names = [tool["name"] for tool in tools]
        assert "internal__create_monitor" in tool_names
        assert "internal__create_task" in tool_names
        assert "internal__list_schedules" in tool_names
        assert "internal__update_schedule" in tool_names
        assert "internal__delete_schedule" in tool_names
        assert "internal__enable_schedule" in tool_names
        assert "internal__get_schedule_status" in tool_names


class TestCreateMonitor:
    """Tests for create_monitor functionality"""

    @pytest.mark.asyncio
    async def test_create_monitor_success(self, schedule_tools, temp_schedules):
        """Test creating a monitor successfully"""
        result = await schedule_tools.execute_tool(
            "create_monitor",
            {
                "name": "Test Monitor",
                "prompt": "Check for failures",
                "interval": "5m",
                "description": "Test monitor",
                "enabled": True,
            },
        )

        assert "created successfully" in result
        assert "Test Monitor" in result

        # Verify JSON file
        data = json.loads(temp_schedules.read_text())
        assert len(data["monitors"]) == 1
        assert data["monitors"][0]["name"] == "Test Monitor"
        assert data["monitors"][0]["interval"] == "5m"

    @pytest.mark.asyncio
    async def test_create_monitor_with_knowledge_graph(self, schedule_tools, temp_schedules):
        """Test creating a monitor with knowledge graph config"""
        kg_config = {"enabled": True, "save_results": True}

        result = await schedule_tools.execute_tool(
            "create_monitor",
            {"name": "KG Monitor", "prompt": "Monitor with KG", "interval": "10m", "knowledge_graph": kg_config},
        )

        assert "created successfully" in result

        data = json.loads(temp_schedules.read_text())
        assert data["monitors"][0]["knowledge_graph"] == kg_config

    @pytest.mark.asyncio
    async def test_create_monitor_duplicate_name(self, schedule_tools):
        """Test that duplicate monitor names are rejected"""
        await schedule_tools.execute_tool("create_monitor", {"name": "Duplicate", "prompt": "Test", "interval": "5m"})

        result = await schedule_tools.execute_tool(
            "create_monitor", {"name": "Duplicate", "prompt": "Test2", "interval": "10m"}
        )

        assert "Error" in result
        assert "already exists" in result

    @pytest.mark.asyncio
    async def test_create_monitor_invalid_interval(self, schedule_tools):
        """Test that invalid interval format is rejected"""
        result = await schedule_tools.execute_tool(
            "create_monitor", {"name": "Invalid", "prompt": "Test", "interval": "invalid"}
        )

        assert "Error" in result
        assert "Invalid" in result


class TestCreateTask:
    """Tests for create_task functionality"""

    @pytest.mark.asyncio
    async def test_create_task_success(self, schedule_tools, temp_schedules):
        """Test creating a task successfully"""
        result = await schedule_tools.execute_tool(
            "create_task",
            {
                "name": "Daily Report",
                "prompt": "Generate daily report",
                "interval": "morning on weekdays",
                "description": "Daily summary",
            },
        )

        assert "created successfully" in result
        assert "Daily Report" in result

        # Verify JSON file
        data = json.loads(temp_schedules.read_text())
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["name"] == "Daily Report"
        assert data["tasks"][0]["interval"] == "morning on weekdays"

    @pytest.mark.asyncio
    async def test_create_task_with_time_schedule(self, schedule_tools):
        """Test creating a task with time-based schedule"""
        result = await schedule_tools.execute_tool(
            "create_task", {"name": "Time Task", "prompt": "Run at specific time", "interval": "9:00 on monday,friday"}
        )

        assert "created successfully" in result

    @pytest.mark.asyncio
    async def test_create_task_duplicate_name(self, schedule_tools):
        """Test that duplicate task names are rejected"""
        await schedule_tools.execute_tool("create_task", {"name": "Duplicate", "prompt": "Test", "interval": "1h"})

        result = await schedule_tools.execute_tool(
            "create_task", {"name": "Duplicate", "prompt": "Test2", "interval": "2h"}
        )

        assert "Error" in result
        assert "already exists" in result

    @pytest.mark.asyncio
    async def test_create_task_conflicts_with_monitor(self, schedule_tools):
        """Test that task name conflicting with monitor is rejected"""
        await schedule_tools.execute_tool("create_monitor", {"name": "Shared Name", "prompt": "Test", "interval": "5m"})

        result = await schedule_tools.execute_tool(
            "create_task", {"name": "Shared Name", "prompt": "Test", "interval": "1h"}
        )

        assert "Error" in result
        assert "already exists" in result


class TestListSchedules:
    """Tests for list_schedules functionality"""

    @pytest.mark.asyncio
    async def test_list_schedules_empty(self, schedule_tools):
        """Test listing schedules when none exist"""
        result = await schedule_tools.execute_tool("list_schedules", {})
        assert "No schedules found" in result

    @pytest.mark.asyncio
    async def test_list_schedules_with_data(self, schedule_tools):
        """Test listing schedules with monitors and tasks"""
        await schedule_tools.execute_tool("create_monitor", {"name": "Monitor 1", "prompt": "Test", "interval": "5m"})
        await schedule_tools.execute_tool("create_task", {"name": "Task 1", "prompt": "Test", "interval": "1h"})

        result = await schedule_tools.execute_tool("list_schedules", {})

        assert "Monitor 1" in result
        assert "Task 1" in result
        assert "## Monitors" in result
        assert "## Tasks" in result

    @pytest.mark.asyncio
    async def test_list_schedules_filter_monitors(self, schedule_tools):
        """Test listing only monitors"""
        await schedule_tools.execute_tool("create_monitor", {"name": "Monitor 1", "prompt": "Test", "interval": "5m"})
        await schedule_tools.execute_tool("create_task", {"name": "Task 1", "prompt": "Test", "interval": "1h"})

        result = await schedule_tools.execute_tool("list_schedules", {"filter_type": "monitor"})

        assert "Monitor 1" in result
        assert "Task 1" not in result

    @pytest.mark.asyncio
    async def test_list_schedules_filter_tasks(self, schedule_tools):
        """Test listing only tasks"""
        await schedule_tools.execute_tool("create_monitor", {"name": "Monitor 1", "prompt": "Test", "interval": "5m"})
        await schedule_tools.execute_tool("create_task", {"name": "Task 1", "prompt": "Test", "interval": "1h"})

        result = await schedule_tools.execute_tool("list_schedules", {"filter_type": "task"})

        assert "Monitor 1" not in result
        assert "Task 1" in result


class TestUpdateSchedule:
    """Tests for update_schedule functionality"""

    @pytest.mark.asyncio
    async def test_update_schedule_interval(self, schedule_tools, temp_schedules):
        """Test updating a schedule's interval"""
        await schedule_tools.execute_tool("create_task", {"name": "Update Test", "prompt": "Test", "interval": "5m"})

        result = await schedule_tools.execute_tool(
            "update_schedule", {"name": "Update Test", "schedule_type": "task", "interval": "10m"}
        )

        assert "updated successfully" in result

        data = json.loads(temp_schedules.read_text())
        assert data["tasks"][0]["interval"] == "10m"

    @pytest.mark.asyncio
    async def test_update_schedule_prompt(self, schedule_tools, temp_schedules):
        """Test updating a schedule's prompt"""
        await schedule_tools.execute_tool(
            "create_monitor", {"name": "Prompt Test", "prompt": "Old prompt", "interval": "5m"}
        )

        result = await schedule_tools.execute_tool(
            "update_schedule", {"name": "Prompt Test", "schedule_type": "monitor", "prompt": "New prompt"}
        )

        assert "updated successfully" in result

        data = json.loads(temp_schedules.read_text())
        assert data["monitors"][0]["prompt"] == "New prompt"

    @pytest.mark.asyncio
    async def test_update_schedule_not_found(self, schedule_tools):
        """Test updating a non-existent schedule"""
        result = await schedule_tools.execute_tool(
            "update_schedule", {"name": "Nonexistent", "schedule_type": "task", "interval": "1h"}
        )

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_update_schedule_invalid_interval(self, schedule_tools):
        """Test updating with invalid interval"""
        await schedule_tools.execute_tool("create_task", {"name": "Invalid Update", "prompt": "Test", "interval": "5m"})

        result = await schedule_tools.execute_tool(
            "update_schedule", {"name": "Invalid Update", "schedule_type": "task", "interval": "invalid"}
        )

        assert "Error" in result


class TestDeleteSchedule:
    """Tests for delete_schedule functionality"""

    @pytest.mark.asyncio
    async def test_delete_schedule_success(self, schedule_tools, temp_schedules):
        """Test deleting a schedule successfully"""
        await schedule_tools.execute_tool("create_task", {"name": "Delete Me", "prompt": "Test", "interval": "5m"})

        result = await schedule_tools.execute_tool("delete_schedule", {"name": "Delete Me", "schedule_type": "task"})

        assert "deleted successfully" in result

        data = json.loads(temp_schedules.read_text())
        assert len(data["tasks"]) == 0

    @pytest.mark.asyncio
    async def test_delete_schedule_not_found(self, schedule_tools):
        """Test deleting a non-existent schedule"""
        result = await schedule_tools.execute_tool("delete_schedule", {"name": "Nonexistent", "schedule_type": "task"})

        assert "Error" in result
        assert "not found" in result


class TestEnableSchedule:
    """Tests for enable_schedule functionality"""

    @pytest.mark.asyncio
    async def test_enable_schedule(self, schedule_tools, temp_schedules):
        """Test enabling a disabled schedule"""
        await schedule_tools.execute_tool(
            "create_task", {"name": "Enable Test", "prompt": "Test", "interval": "5m", "enabled": False}
        )

        result = await schedule_tools.execute_tool(
            "enable_schedule", {"name": "Enable Test", "schedule_type": "task", "enabled": True}
        )

        assert "enabled successfully" in result

        data = json.loads(temp_schedules.read_text())
        assert data["tasks"][0]["enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_schedule(self, schedule_tools, temp_schedules):
        """Test disabling an enabled schedule"""
        await schedule_tools.execute_tool(
            "create_monitor", {"name": "Disable Test", "prompt": "Test", "interval": "5m"}
        )

        result = await schedule_tools.execute_tool(
            "enable_schedule", {"name": "Disable Test", "schedule_type": "monitor", "enabled": False}
        )

        assert "disabled successfully" in result

        data = json.loads(temp_schedules.read_text())
        assert data["monitors"][0]["enabled"] is False


class TestGetScheduleStatus:
    """Tests for get_schedule_status functionality"""

    @pytest.mark.asyncio
    async def test_get_schedule_status(self, schedule_tools):
        """Test getting schedule status"""
        await schedule_tools.execute_tool(
            "create_task",
            {"name": "Status Test", "prompt": "Test prompt", "interval": "5m", "description": "Test description"},
        )

        result = await schedule_tools.execute_tool(
            "get_schedule_status", {"name": "Status Test", "schedule_type": "task"}
        )

        assert "Status Test" in result
        assert "enabled" in result
        assert "5m" in result
        assert "Test prompt" in result
        assert "Test description" in result

    @pytest.mark.asyncio
    async def test_get_schedule_status_not_found(self, schedule_tools):
        """Test getting status of non-existent schedule"""
        result = await schedule_tools.execute_tool(
            "get_schedule_status", {"name": "Nonexistent", "schedule_type": "task"}
        )

        assert "Error" in result
        assert "not found" in result


class TestJSONPersistence:
    """Tests for JSON file persistence"""

    @pytest.mark.asyncio
    async def test_schedules_persist_across_instances(self, temp_schedules):
        """Test that schedules persist when creating new ScheduleTools instance"""
        # Create schedules with first instance
        tools1 = ScheduleTools(schedules_file=temp_schedules)
        await tools1.execute_tool("create_monitor", {"name": "Persistent", "prompt": "Test", "interval": "5m"})

        # Create new instance and verify schedules are loaded
        tools2 = ScheduleTools(schedules_file=temp_schedules)
        result = await tools2.execute_tool("list_schedules", {})

        assert "Persistent" in result

    @pytest.mark.asyncio
    async def test_corrupted_json_recovery(self, temp_schedules):
        """Test recovery from corrupted JSON file"""
        # Create a corrupted JSON file
        temp_schedules.write_text("{invalid json")

        # Should recover gracefully
        tools = ScheduleTools(schedules_file=temp_schedules)
        result = await tools.execute_tool("list_schedules", {})

        assert "No schedules found" in result

        # Verify backup was created
        backup_file = temp_schedules.with_suffix(".json.backup")
        assert backup_file.exists()

    @pytest.mark.asyncio
    async def test_atomic_writes(self, temp_schedules):
        """Test that writes are atomic"""
        tools = ScheduleTools(schedules_file=temp_schedules)

        # Create a schedule
        await tools.execute_tool("create_task", {"name": "Atomic", "prompt": "Test", "interval": "5m"})

        # File should exist and be valid JSON
        assert temp_schedules.exists()
        data = json.loads(temp_schedules.read_text())
        assert "tasks" in data
        assert len(data["tasks"]) == 1
