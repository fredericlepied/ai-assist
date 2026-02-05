"""Tests for condition evaluation"""

import pytest
from ai_assist.conditions import ConditionEvaluator


def test_extract_metadata_found_pattern():
    """Test extracting 'Found X items' pattern"""
    output = "Found 5 failures in the last hour"
    evaluator = ConditionEvaluator()
    metadata = evaluator.extract_metadata(output)

    assert metadata["failures"] == 5
    assert metadata["count"] == 5


def test_extract_metadata_multiple_found():
    """Test extracting multiple found patterns"""
    output = "Found 10 jobs and Found 3 failures"
    evaluator = ConditionEvaluator()
    metadata = evaluator.extract_metadata(output)

    assert metadata["jobs"] == 10
    assert metadata["failures"] == 3
    assert metadata["count"] == 10  # First found value


def test_extract_metadata_success_rate():
    """Test extracting success rate"""
    output = "Success rate: 85.5%"
    evaluator = ConditionEvaluator()
    metadata = evaluator.extract_metadata(output)

    assert metadata["success_rate"] == 85.5


def test_extract_metadata_status():
    """Test extracting status"""
    output = "Status: failed"
    evaluator = ConditionEvaluator()
    metadata = evaluator.extract_metadata(output)

    assert metadata["status"] == "failed"


def test_extract_metadata_updated_count():
    """Test extracting updated count"""
    output = "3 updated tickets found"
    evaluator = ConditionEvaluator()
    metadata = evaluator.extract_metadata(output)

    assert metadata["updated_count"] == 3


def test_extract_metadata_complex():
    """Test extracting from complex output"""
    output = """
    Found 15 jobs in the last hour.
    Success rate: 92.3%
    Status: completed
    5 failures detected
    """
    evaluator = ConditionEvaluator()
    metadata = evaluator.extract_metadata(output)

    assert metadata["jobs"] == 15
    assert metadata["success_rate"] == 92.3
    assert metadata["status"] == "completed"
    assert metadata["failures"] == 5


def test_evaluate_greater_than():
    """Test > operator"""
    evaluator = ConditionEvaluator()
    metadata = {"count": 10}

    assert evaluator.evaluate("count > 5", metadata) is True
    assert evaluator.evaluate("count > 10", metadata) is False
    assert evaluator.evaluate("count > 15", metadata) is False


def test_evaluate_less_than():
    """Test < operator"""
    evaluator = ConditionEvaluator()
    metadata = {"count": 10}

    assert evaluator.evaluate("count < 15", metadata) is True
    assert evaluator.evaluate("count < 10", metadata) is False
    assert evaluator.evaluate("count < 5", metadata) is False


def test_evaluate_greater_equal():
    """Test >= operator"""
    evaluator = ConditionEvaluator()
    metadata = {"count": 10}

    assert evaluator.evaluate("count >= 10", metadata) is True
    assert evaluator.evaluate("count >= 5", metadata) is True
    assert evaluator.evaluate("count >= 15", metadata) is False


def test_evaluate_less_equal():
    """Test <= operator"""
    evaluator = ConditionEvaluator()
    metadata = {"count": 10}

    assert evaluator.evaluate("count <= 10", metadata) is True
    assert evaluator.evaluate("count <= 15", metadata) is True
    assert evaluator.evaluate("count <= 5", metadata) is False


def test_evaluate_equals():
    """Test == operator"""
    evaluator = ConditionEvaluator()

    # Numeric equality
    assert evaluator.evaluate("count == 10", {"count": 10}) is True
    assert evaluator.evaluate("count == 5", {"count": 10}) is False

    # String equality
    assert evaluator.evaluate("status == 'failed'", {"status": "failed"}) is True
    assert evaluator.evaluate("status == 'success'", {"status": "failed"}) is False


def test_evaluate_not_equals():
    """Test != operator"""
    evaluator = ConditionEvaluator()

    assert evaluator.evaluate("count != 5", {"count": 10}) is True
    assert evaluator.evaluate("count != 10", {"count": 10}) is False


def test_evaluate_contains():
    """Test contains operator"""
    evaluator = ConditionEvaluator()
    metadata = {"message": "This is a critical error"}

    assert evaluator.evaluate("message contains 'critical'", metadata) is True
    assert evaluator.evaluate("message contains 'warning'", metadata) is False


def test_evaluate_not_contains():
    """Test not_contains operator"""
    evaluator = ConditionEvaluator()
    metadata = {"message": "This is a critical error"}

    assert evaluator.evaluate("message not_contains 'warning'", metadata) is True
    assert evaluator.evaluate("message not_contains 'critical'", metadata) is False


def test_evaluate_missing_field():
    """Test evaluation when field is missing from metadata"""
    evaluator = ConditionEvaluator()
    metadata = {"count": 10}

    # Should return False when field doesn't exist
    assert evaluator.evaluate("failures > 5", metadata) is False


def test_evaluate_float_comparison():
    """Test comparison with float values"""
    evaluator = ConditionEvaluator()
    metadata = {"success_rate": 85.5}

    assert evaluator.evaluate("success_rate > 80", metadata) is True
    assert evaluator.evaluate("success_rate < 90", metadata) is True
    assert evaluator.evaluate("success_rate >= 85.5", metadata) is True
