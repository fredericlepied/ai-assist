"""Tests for GoalState persistence"""

from ai_assist.goal_state import GoalState, GoalStateManager


class TestGoalState:
    def test_default_state(self):
        state = GoalState()
        assert state.status == "active"
        assert state.variables == {}
        assert state.last_run is None
        assert state.cycle_count == 0
        assert state.success_reason is None


class TestGoalStateManager:
    def test_save_and_load(self, tmp_path):
        manager = GoalStateManager(tmp_path)
        state = GoalState(
            status="active",
            variables={"failure_rate": 15, "items": ["a", "b"]},
            last_run="2026-03-31T10:00:00",
            cycle_count=3,
        )
        manager.save("test_goal", state)

        loaded = manager.load("test_goal")
        assert loaded.status == "active"
        assert loaded.variables["failure_rate"] == 15
        assert loaded.variables["items"] == ["a", "b"]
        assert loaded.last_run == "2026-03-31T10:00:00"
        assert loaded.cycle_count == 3

    def test_load_nonexistent(self, tmp_path):
        manager = GoalStateManager(tmp_path)
        state = manager.load("nonexistent")
        assert state.status == "active"
        assert state.cycle_count == 0

    def test_load_invalid_json(self, tmp_path):
        manager = GoalStateManager(tmp_path)
        (tmp_path / "goal_bad.json").write_text("not json")
        state = manager.load("bad")
        assert state.status == "active"

    def test_list_all(self, tmp_path):
        manager = GoalStateManager(tmp_path)
        manager.save("goal_a", GoalState(status="active", cycle_count=5))
        manager.save("goal_b", GoalState(status="completed", cycle_count=10))

        all_states = manager.list_all()
        assert len(all_states) == 2
        ids = [goal_id for goal_id, _ in all_states]
        assert "goal_a" in ids
        assert "goal_b" in ids

    def test_update_state(self, tmp_path):
        manager = GoalStateManager(tmp_path)
        manager.save("upd", GoalState(status="active", cycle_count=0))

        state = manager.load("upd")
        state.cycle_count = 5
        state.status = "completed"
        state.success_reason = "All criteria met"
        manager.save("upd", state)

        reloaded = manager.load("upd")
        assert reloaded.cycle_count == 5
        assert reloaded.status == "completed"
        assert reloaded.success_reason == "All criteria met"
