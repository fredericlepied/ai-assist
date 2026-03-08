"""Tests for AWL expression evaluator"""

import pytest

from ai_assist.awl_expressions import AWLExpressionEvaluator


@pytest.fixture
def evaluator():
    return AWLExpressionEvaluator()


class TestIsTruthy:
    def test_none_is_falsy(self, evaluator):
        assert evaluator.is_truthy(None) is False

    def test_empty_string_is_falsy(self, evaluator):
        assert evaluator.is_truthy("") is False

    def test_empty_list_is_falsy(self, evaluator):
        assert evaluator.is_truthy([]) is False

    def test_zero_is_falsy(self, evaluator):
        assert evaluator.is_truthy(0) is False

    def test_non_empty_string_is_truthy(self, evaluator):
        assert evaluator.is_truthy("hello") is True

    def test_non_empty_list_is_truthy(self, evaluator):
        assert evaluator.is_truthy(["a"]) is True

    def test_non_zero_is_truthy(self, evaluator):
        assert evaluator.is_truthy(42) is True

    def test_dict_is_truthy(self, evaluator):
        assert evaluator.is_truthy({"key": "val"}) is True

    def test_empty_dict_is_falsy(self, evaluator):
        assert evaluator.is_truthy({}) is False


class TestEvaluate:
    def test_simple_variable_lookup(self, evaluator):
        result = evaluator.evaluate("handlers", {"handlers": ["a", "b"]})
        assert result == ["a", "b"]

    def test_missing_variable_returns_none(self, evaluator):
        result = evaluator.evaluate("missing", {})
        assert result is None

    def test_len_function(self, evaluator):
        result = evaluator.evaluate("len(handlers)", {"handlers": ["a", "b", "c"]})
        assert result == 3

    def test_len_empty(self, evaluator):
        result = evaluator.evaluate("len(items)", {"items": []})
        assert result == 0

    def test_comparison_greater(self, evaluator):
        result = evaluator.evaluate("len(handlers) > 0", {"handlers": ["a"]})
        assert result is True

    def test_comparison_greater_false(self, evaluator):
        result = evaluator.evaluate("len(handlers) > 0", {"handlers": []})
        assert result is False

    def test_comparison_equals(self, evaluator):
        result = evaluator.evaluate("count == 5", {"count": 5})
        assert result is True

    def test_comparison_not_equals(self, evaluator):
        result = evaluator.evaluate("status != failed", {"status": "ok"})
        assert result is True

    def test_comparison_less_than(self, evaluator):
        result = evaluator.evaluate("count < 10", {"count": 3})
        assert result is True

    def test_comparison_greater_equal(self, evaluator):
        result = evaluator.evaluate("count >= 5", {"count": 5})
        assert result is True

    def test_comparison_less_equal(self, evaluator):
        result = evaluator.evaluate("count <= 5", {"count": 5})
        assert result is True

    def test_not_variable_true(self, evaluator):
        result = evaluator.evaluate("not report_exists", {"report_exists": True})
        assert result is False

    def test_not_variable_false(self, evaluator):
        result = evaluator.evaluate("not report_exists", {"report_exists": False})
        assert result is True

    def test_not_missing_variable(self, evaluator):
        result = evaluator.evaluate("not report_exists", {})
        assert result is True

    def test_not_empty_list(self, evaluator):
        result = evaluator.evaluate("not items", {"items": []})
        assert result is True

    def test_not_non_empty_list(self, evaluator):
        result = evaluator.evaluate("not items", {"items": ["a"]})
        assert result is False

    def test_property_access(self, evaluator):
        result = evaluator.evaluate("config.entrypoint", {"config": {"entrypoint": "main.go"}})
        assert result == "main.go"

    def test_index_access(self, evaluator):
        result = evaluator.evaluate("handlers[0]", {"handlers": ["first", "second"]})
        assert result == "first"

    def test_comparison_with_none_left(self, evaluator):
        """None > 0 should not crash, should return False."""
        result = evaluator.evaluate("count > 0", {})
        assert result is False

    def test_comparison_with_none_right(self, evaluator):
        result = evaluator.evaluate("0 > count", {})
        assert result is False

    def test_index_out_of_range(self, evaluator):
        result = evaluator.evaluate("items[99]", {"items": ["a"]})
        assert result is None


class TestInterpolate:
    def test_simple_variable(self, evaluator):
        result = evaluator.interpolate("Find ${target}.", {"target": "HTTP server"})
        assert result == "Find HTTP server."

    def test_multiple_variables(self, evaluator):
        result = evaluator.interpolate("${a} and ${b}", {"a": "foo", "b": "bar"})
        assert result == "foo and bar"

    def test_no_variables(self, evaluator):
        result = evaluator.interpolate("No variables here.", {})
        assert result == "No variables here."

    def test_missing_variable_left_as_is(self, evaluator):
        result = evaluator.interpolate("Find ${missing}.", {})
        assert result == "Find ${missing}."

    def test_property_interpolation(self, evaluator):
        result = evaluator.interpolate("File: ${config.file}", {"config": {"file": "main.go"}})
        assert result == "File: main.go"


class TestValidateExpression:
    def test_valid_variable(self, evaluator):
        evaluator.validate_expression("handlers")

    def test_valid_len(self, evaluator):
        evaluator.validate_expression("len(handlers)")

    def test_valid_comparison(self, evaluator):
        evaluator.validate_expression("len(handlers) > 0")

    def test_valid_not(self, evaluator):
        evaluator.validate_expression("not report_exists")

    def test_valid_property_access(self, evaluator):
        evaluator.validate_expression("config.key")

    def test_valid_index_access(self, evaluator):
        evaluator.validate_expression("handlers[0]")

    def test_invalid_special_chars(self, evaluator):
        with pytest.raises(ValueError):
            evaluator.validate_expression("!!!")

    def test_invalid_unclosed_len(self, evaluator):
        with pytest.raises(ValueError):
            evaluator.validate_expression("len(")

    def test_invalid_empty(self, evaluator):
        with pytest.raises(ValueError):
            evaluator.validate_expression("")

    def test_invalid_comparison_missing_right(self, evaluator):
        with pytest.raises(ValueError):
            evaluator.validate_expression("handlers >")

    def test_invalid_comparison_missing_left(self, evaluator):
        with pytest.raises(ValueError):
            evaluator.validate_expression("> 0")
