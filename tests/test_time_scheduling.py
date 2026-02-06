"""Tests for time-based task scheduling"""

from datetime import datetime, timedelta
from datetime import time as dt_time

import pytest

from ai_assist.tasks import TaskDefinition, TaskLoader


def test_parse_morning_on_weekdays():
    """Test parsing 'morning on weekdays'"""
    schedule = TaskLoader.parse_time_schedule("morning on weekdays")

    assert schedule["time"] == dt_time(9, 0)
    assert schedule["days"] == [0, 1, 2, 3, 4]  # Monday-Friday


def test_parse_afternoon_on_weekends():
    """Test parsing 'afternoon on weekends'"""
    schedule = TaskLoader.parse_time_schedule("afternoon on weekends")

    assert schedule["time"] == dt_time(14, 0)
    assert schedule["days"] == [5, 6]  # Saturday-Sunday


def test_parse_specific_time_on_weekdays():
    """Test parsing '9:30 on weekdays'"""
    schedule = TaskLoader.parse_time_schedule("9:30 on weekdays")

    assert schedule["time"] == dt_time(9, 30)
    assert schedule["days"] == [0, 1, 2, 3, 4]


def test_parse_specific_days():
    """Test parsing '14:00 on monday,wednesday,friday'"""
    schedule = TaskLoader.parse_time_schedule("14:00 on monday,wednesday,friday")

    assert schedule["time"] == dt_time(14, 0)
    assert schedule["days"] == [0, 2, 4]  # Mon, Wed, Fri


def test_parse_short_day_names():
    """Test parsing with short day names"""
    schedule = TaskLoader.parse_time_schedule("10:00 on mon,wed,fri")

    assert schedule["time"] == dt_time(10, 0)
    assert schedule["days"] == [0, 2, 4]


def test_parse_case_insensitive():
    """Test that parsing is case insensitive"""
    schedule = TaskLoader.parse_time_schedule("MORNING ON WEEKDAYS")

    assert schedule["time"] == dt_time(9, 0)
    assert schedule["days"] == [0, 1, 2, 3, 4]


def test_parse_invalid_time_format():
    """Test error handling for invalid time format"""
    with pytest.raises(ValueError, match="Invalid time format"):
        TaskLoader.parse_time_schedule("25:00 on weekdays")

    with pytest.raises(ValueError, match="Invalid time format"):
        TaskLoader.parse_time_schedule("invalid on weekdays")


def test_parse_invalid_day():
    """Test error handling for invalid day name"""
    with pytest.raises(ValueError, match="Invalid day"):
        TaskLoader.parse_time_schedule("9:00 on funday")


def test_parse_missing_on():
    """Test error handling when 'on' is missing"""
    with pytest.raises(ValueError, match="must include 'on'"):
        TaskLoader.parse_time_schedule("morning weekdays")


def test_calculate_next_run_same_day():
    """Test next run calculation when time hasn't passed today"""
    schedule = {"time": dt_time(15, 0), "days": [0, 1, 2, 3, 4]}  # Weekdays at 3 PM

    # Monday at 10 AM
    from_time = datetime(2024, 1, 1, 10, 0)  # Monday
    next_run = TaskLoader.calculate_next_run(schedule, from_time)

    # Should be today at 3 PM
    assert next_run.date() == from_time.date()
    assert next_run.time() == dt_time(15, 0)


def test_calculate_next_run_next_day():
    """Test next run calculation when time has passed today"""
    schedule = {"time": dt_time(9, 0), "days": [0, 1, 2, 3, 4]}  # Weekdays at 9 AM

    # Monday at 10 AM (time has passed)
    from_time = datetime(2024, 1, 1, 10, 0)  # Monday
    next_run = TaskLoader.calculate_next_run(schedule, from_time)

    # Should be tomorrow (Tuesday) at 9 AM
    assert next_run.date() == (from_time + timedelta(days=1)).date()
    assert next_run.time() == dt_time(9, 0)


def test_calculate_next_run_skip_weekend():
    """Test next run calculation skipping weekend"""
    schedule = {"time": dt_time(9, 0), "days": [0, 1, 2, 3, 4]}  # Weekdays only

    # Friday at 10 AM (time has passed)
    from_time = datetime(2024, 1, 5, 10, 0)  # Friday
    next_run = TaskLoader.calculate_next_run(schedule, from_time)

    # Should be Monday at 9 AM (skip weekend)
    assert next_run.weekday() == 0  # Monday
    assert next_run.time() == dt_time(9, 0)


def test_calculate_next_run_weekend_only():
    """Test next run for weekend-only schedule"""
    schedule = {"time": dt_time(10, 0), "days": [5, 6]}  # Weekends only

    # Monday
    from_time = datetime(2024, 1, 1, 12, 0)  # Monday
    next_run = TaskLoader.calculate_next_run(schedule, from_time)

    # Should be Saturday at 10 AM
    assert next_run.weekday() == 5  # Saturday
    assert next_run.time() == dt_time(10, 0)


def test_task_definition_is_time_based():
    """Test detecting time-based schedules"""
    time_task = TaskDefinition(name="Morning Task", prompt="Check status", interval="morning on weekdays")

    interval_task = TaskDefinition(name="Interval Task", prompt="Check status", interval="5m")

    assert time_task.is_time_based is True
    assert interval_task.is_time_based is False


def test_task_definition_validates_time_schedule():
    """Test that time-based schedules are validated"""
    # Valid time schedule
    task = TaskDefinition(name="Test", prompt="Test", interval="morning on weekdays")
    task.validate()  # Should not raise

    # Invalid time schedule
    with pytest.raises(ValueError, match="Invalid interval"):
        task = TaskDefinition(name="Test", prompt="Test", interval="invalid on weekdays")
        task.validate()


def test_time_presets():
    """Test all time presets"""
    presets = {
        "morning": dt_time(9, 0),
        "afternoon": dt_time(14, 0),
        "evening": dt_time(18, 0),
        "night": dt_time(22, 0),
    }

    for preset, expected_time in presets.items():
        schedule = TaskLoader.parse_time_schedule(f"{preset} on weekdays")
        assert schedule["time"] == expected_time


def test_load_yaml_with_time_schedule():
    """Test loading YAML with time-based schedule"""
    yaml_content = """
tasks:
  - name: "Morning Standup"
    interval: "morning on weekdays"
    prompt: "Check for updates"
"""
    loader = TaskLoader()
    tasks = loader.load_from_yaml_string(yaml_content)

    assert len(tasks) == 1
    assert tasks[0].interval == "morning on weekdays"
    assert tasks[0].is_time_based is True
