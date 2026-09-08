"""Decimal-only arithmetic with a closed, explicitly documented operation set."""

from __future__ import annotations

import re
from decimal import Decimal, DecimalException, localcontext
from typing import Mapping


class CalculationError(ValueError):
    """Invalid numeric input, undefined division, or unsupported operation."""


NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,3})?\Z")


def decimal_value(value: str | int | Decimal) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise CalculationError("Numbers must be decimal strings or integers; binary floats are rejected.")
    text = str(value).strip()
    if len(text) > 120 or not NUMBER.fullmatch(text):
        raise CalculationError("Invalid decimal number; expressions, NaN and Infinity are not accepted.")
    try:
        number = Decimal(text)
        if not number.is_finite() or (number and abs(number.adjusted()) > 100):
            raise CalculationError("Number magnitude must be between 1e-100 and 1e100.")
        return number
    except DecimalException as exc:
        raise CalculationError("Invalid decimal number.") from exc


def decimal_string(value: Decimal) -> str:
    if not value:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


OPERATIONS = {
    "add": (("a", "b"), "a + b", "number"),
    "subtract": (("a", "b"), "a - b", "number"),
    "multiply": (("a", "b"), "a * b", "number"),
    "divide": (("a", "b"), "a / b", "ratio"),
    "ratio": (("numerator", "denominator"), "numerator / denominator", "ratio"),
    "change_rate": (("old", "new"), "(new - old) / abs(old) * 100", "percent"),
    "debt_ratio": (("liabilities", "assets"), "liabilities / assets * 100", "percent"),
    "current_ratio": (("current_assets", "current_liabilities"), "current_assets / current_liabilities", "ratio"),
    "gross_margin": (("revenue", "cost"), "(revenue - cost) / revenue * 100", "percent"),
    "net_margin": (("net_profit", "revenue"), "net_profit / revenue * 100", "percent"),
    "return_on_equity": (("net_profit", "equity"), "net_profit / equity * 100", "percent"),
}


def calculate(operation: str, values: Mapping[str, str | int | Decimal]) -> dict:
    """Return decimal strings with formula and unit. Division uses 50-digit precision.

    All monetary inputs must have a consistent currency, scale, and reporting period.
    Percent results are percentage points of 100 (e.g. 25 means 25%, not 0.25).
    """
    if operation not in OPERATIONS:
        raise CalculationError(f"Unsupported operation {operation!r}; allowed: {', '.join(OPERATIONS)}")
    keys, formula, unit = OPERATIONS[operation]
    if set(values) != set(keys):
        raise CalculationError(f"{operation} requires exactly these inputs: {', '.join(keys)}")
    v = {key: decimal_value(values[key]) for key in keys}
    try:
        with localcontext() as ctx:
            ctx.prec = 50
            if operation == "add":
                result = v["a"] + v["b"]
            elif operation == "subtract":
                result = v["a"] - v["b"]
            elif operation == "multiply":
                result = v["a"] * v["b"]
            elif operation == "divide":
                result = v["a"] / v["b"]
            elif operation == "ratio":
                result = v["numerator"] / v["denominator"]
            elif operation == "change_rate":
                result = (v["new"] - v["old"]) / abs(v["old"]) * 100
            elif operation == "debt_ratio":
                result = v["liabilities"] / v["assets"] * 100
            elif operation == "current_ratio":
                result = v["current_assets"] / v["current_liabilities"]
            elif operation == "gross_margin":
                result = (v["revenue"] - v["cost"]) / v["revenue"] * 100
            elif operation == "net_margin":
                result = v["net_profit"] / v["revenue"] * 100
            else:
                result = v["net_profit"] / v["equity"] * 100
    except DecimalException as exc:
        raise CalculationError("Calculation is undefined (for example, division by zero).") from exc
    return {
        "operation": operation, "inputs": {k: decimal_string(n) for k, n in v.items()},
        "result": decimal_string(result), "unit": unit, "formula": formula,
        "precision": 50,
    }


CALL = re.compile(r"(add|subtract|multiply|divide)\(\s*([^(),]+?)\s*,\s*([^(),]+?)\s*\)")


def evaluate_program(program: str) -> dict:
    """Interpret only a FinQA-style arithmetic subset; never Python/eval.

    Accepted: add/subtract/multiply/divide(number|const_number|#previous, ...).
    Table operations, exponentiation, nested calls and arbitrary names are rejected.
    """
    if not isinstance(program, str) or len(program) > 4096:
        raise CalculationError("Program must be a string of at most 4096 characters.")
    source = program.strip()
    source = re.sub(r",\s*EOF\s*$", "", source)
    steps, cursor = [], 0

    def resolve(token: str) -> str:
        token = token.strip()
        if re.fullmatch(r"#\d+", token):
            index = int(token[1:])
            if index >= len(steps):
                raise CalculationError("Program references a result that does not exist yet.")
            return steps[index]["result"]
        if token.startswith("const_"):
            token = token[6:]
            if token.startswith("m"):
                token = "-" + token[1:]
        return decimal_string(decimal_value(token))

    while cursor < len(source):
        match = CALL.match(source, cursor)
        if not match:
            raise CalculationError("Only flat add/subtract/multiply/divide calls are supported.")
        name, left, right = match.groups()
        steps.append(calculate(name, {"a": resolve(left), "b": resolve(right)}))
        if len(steps) > 64:
            raise CalculationError("Program exceeds 64 steps.")
        cursor = match.end()
        if cursor < len(source):
            separator = re.match(r"\s*,\s*", source[cursor:])
            if not separator:
                raise CalculationError("Program calls must be separated by commas.")
            cursor += separator.end()
            if cursor == len(source):
                raise CalculationError("Trailing comma is not accepted.")
    if not steps:
        raise CalculationError("Program must contain at least one operation.")
    return {"result": steps[-1]["result"], "steps": steps, "supported_subset": True}
