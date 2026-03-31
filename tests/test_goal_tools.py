"""Tests for AWL-based goal management tools"""

from unittest.mock import MagicMock

import pytest

from ai_assist.goal_state import GoalStateManager
from ai_assist.goal_tools import GoalTools, _slugify


def test_slugify():
    assert _slugify("Track OCP 4.19 failures") == "track_ocp_4_19_failures"
    assert _slugify("Simple") == "simple"
    assert _slugify("A--B  C") == "a_b_c"


class TestGoalTools:
    def test_get_tool_definitions(self, tmp_path):
        mock_agent = MagicMock()
        # Override goals_dir for testing
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()

        defs = tools.get_tool_definitions()
        assert len(defs) >= 3
        names = {d["name"] for d in defs}
        assert "goal__create" in names
        assert "goal__list" in names
        assert "goal__update" in names

    @pytest.mark.asyncio
    async def test_create_goal_generates_awl(self, tmp_path):
        mock_agent = MagicMock()
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()
        tools.state_manager = GoalStateManager(tmp_path / "state")

        result = await tools.execute_tool(
            "goal__create",
            {
                "title": "Track DCI failures",
                "description": "Monitor DCI test failures for OCP 4.19",
                "success_criteria": "Success rate above 90%",
            },
        )

        assert "created" in result.lower()

        # Verify AWL file was created
        awl_path = tools.goals_dir / "track_dci_failures.awl"
        assert awl_path.exists()

        content = awl_path.read_text()
        assert "@goal track_dci_failures" in content
        assert "Success: Success rate above 90%" in content
        assert "Monitor DCI test failures" in content

    @pytest.mark.asyncio
    async def test_create_goal_no_overwrite(self, tmp_path):
        mock_agent = MagicMock()
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()
        tools.state_manager = GoalStateManager(tmp_path / "state")

        # Create once
        await tools.execute_tool(
            "goal__create",
            {
                "title": "My goal",
                "description": "Test",
                "success_criteria": "Done",
            },
        )

        # Create again with same title
        result = await tools.execute_tool(
            "goal__create",
            {
                "title": "My goal",
                "description": "Different",
                "success_criteria": "Done",
            },
        )
        assert "already exists" in result.lower()

    @pytest.mark.asyncio
    async def test_list_goals_empty(self, tmp_path):
        mock_agent = MagicMock()
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()
        tools.state_manager = GoalStateManager(tmp_path / "state")

        result = await tools.execute_tool("goal__list", {})
        assert "no" in result.lower()

    @pytest.mark.asyncio
    async def test_list_goals_with_data(self, tmp_path):
        mock_agent = MagicMock()
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()
        tools.state_manager = GoalStateManager(tmp_path / "state")

        # Create goals
        await tools.execute_tool(
            "goal__create",
            {
                "title": "Goal A",
                "description": "First",
                "success_criteria": "Done A",
            },
        )
        await tools.execute_tool(
            "goal__create",
            {
                "title": "Goal B",
                "description": "Second",
                "success_criteria": "Done B",
            },
        )

        result = await tools.execute_tool("goal__list", {})
        assert "goal_a" in result
        assert "goal_b" in result

    @pytest.mark.asyncio
    async def test_update_goal_status(self, tmp_path):
        mock_agent = MagicMock()
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()
        tools.state_manager = GoalStateManager(tmp_path / "state")

        await tools.execute_tool(
            "goal__create",
            {
                "title": "To pause",
                "description": "Will be paused",
                "success_criteria": "Done",
            },
        )

        result = await tools.execute_tool(
            "goal__update",
            {"goal_id": "to_pause", "status": "paused"},
        )
        assert "paused" in result.lower()

        # Verify state
        state = tools.state_manager.load("to_pause")
        assert state.status == "paused"

    @pytest.mark.asyncio
    async def test_update_nonexistent_goal(self, tmp_path):
        mock_agent = MagicMock()
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()
        tools.state_manager = GoalStateManager(tmp_path / "state")

        result = await tools.execute_tool(
            "goal__update",
            {"goal_id": "nonexistent", "status": "paused"},
        )
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_create_goal_with_max_actions(self, tmp_path):
        mock_agent = MagicMock()
        tools = GoalTools(mock_agent)
        tools.goals_dir = tmp_path / "goals"
        tools.goals_dir.mkdir()
        tools.state_manager = GoalStateManager(tmp_path / "state")

        await tools.execute_tool(
            "goal__create",
            {
                "title": "Limited goal",
                "description": "Test max actions",
                "success_criteria": "Done",
                "max_actions": 3,
            },
        )

        content = (tools.goals_dir / "limited_goal.awl").read_text()
        assert "max_actions=3" in content
