"""AWL expression evaluator and variable interpolation"""

import ast
import json
import re
from typing import Any


def _parse_str_to_collection(val: str) -> Any:
    """Try to parse a string as a JSON or Python collection."""
    try:
        parsed = json.loads(val)
        if isinstance(parsed, list | dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        parsed = ast.literal_eval(val)
        if isinstance(parsed, list | dict):
            return parsed
    except (ValueError, SyntaxError):
        pass
    return val


class AWLExpressionEvaluator:
    def is_truthy(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            # Treat agent-produced boolean strings as their boolean equivalents
            if value.strip().lower() in ("false", "0", "null", "none", ""):
                return False
            return True
        if isinstance(value, list | dict):
            return len(value) > 0
        if isinstance(value, int | float):
            return value != 0
        return bool(value)

    _OPS: dict[str, Any] = {
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }

    def evaluate(self, expression: str, variables: dict[str, Any]) -> Any:
        expression = expression.strip()

        if expression.startswith("not "):
            inner = expression[4:].strip()
            return not self.is_truthy(self.evaluate(inner, variables))

        for op in [">=", "<=", "!=", "==", ">", "<"]:
            if op in expression:
                left_str, right_str = expression.split(op, 1)
                left_val = self._resolve_value(left_str.strip(), variables)
                right_val = self._resolve_value(right_str.strip(), variables)

                if isinstance(left_val, int | float) and isinstance(right_val, str):
                    try:
                        right_val = type(left_val)(right_val)
                    except (ValueError, TypeError):
                        pass
                elif isinstance(right_val, int | float) and isinstance(left_val, str):
                    try:
                        left_val = type(right_val)(left_val)
                    except (ValueError, TypeError):
                        pass

                if left_val is None or right_val is None:
                    if op in ("==", "!="):
                        return self._OPS[op](left_val, right_val)
                    return False

                return self._OPS[op](left_val, right_val)

        return self._resolve_value(expression, variables)

    def _resolve_value(self, expr: str, variables: dict[str, Any]) -> Any:
        expr = expr.strip()

        len_match = re.match(r"len\((\w+)\)", expr)
        if len_match:
            var_name = len_match.group(1)
            val = variables.get(var_name)
            if val is None:
                return 0
            # Parse JSON or Python-repr strings that are actually arrays/objects
            if isinstance(val, str):
                val = _parse_str_to_collection(val)
            return len(val)

        for num_type in (int, float):
            try:
                return num_type(expr)
            except ValueError:
                pass

        index_match = re.match(r"(\w+)\[(\d+)\]", expr)
        if index_match:
            var_name = index_match.group(1)
            index = int(index_match.group(2))
            val = variables.get(var_name)
            if val is not None and isinstance(val, list | tuple):
                if index < len(val):
                    return val[index]
            return None

        if "." in expr:
            parts = expr.split(".", 1)
            val = variables.get(parts[0])
            if isinstance(val, dict):
                return val.get(parts[1])
            return None

        return variables.get(expr)

    # Valid token: variable, len(var), var[N], var.prop, or numeric literal
    _TOKEN_RE = re.compile(r"^(len\(\w+\)|\w+\[\d+\]|\w+\.\w+|\w+|\d+(\.\d+)?)$")

    def _validate_token(self, token: str) -> None:
        if not self._TOKEN_RE.match(token):
            raise ValueError(f"Invalid expression token: '{token}'")

    def validate_expression(self, expression: str) -> None:
        expression = expression.strip()
        if not expression:
            raise ValueError("Empty expression")

        if expression.startswith("not "):
            inner = expression[4:].strip()
            self.validate_expression(inner)
            return

        for op in [">=", "<=", "!=", "==", ">", "<"]:
            if op in expression:
                left, right = expression.split(op, 1)
                left, right = left.strip(), right.strip()
                if not left:
                    raise ValueError(f"Missing left operand before '{op}'")
                if not right:
                    raise ValueError(f"Missing right operand after '{op}'")
                self._validate_token(left)
                self._validate_token(right)
                return

        self._validate_token(expression)

    def interpolate(self, text: str, variables: dict[str, Any]) -> str:
        def replacer(match: re.Match) -> str:
            expr = match.group(1)
            val = self._resolve_value(expr, variables)
            if val is None:
                return match.group(0)
            return str(val)

        return re.sub(r"\$\{([^}]+)\}", replacer, text)
