from decimal import Decimal

import pytest

from asu_finance.calculator import CalculationError, calculate, evaluate_program


def test_decimal_precision_and_formula_units():
    assert calculate("add", {"a": "0.1", "b": "0.2"})["result"] == "0.3"
    assert calculate("subtract", {"a": "10000000000000000000.01", "b": "10000000000000000000"})["result"] == "0.01"
    result = calculate("change_rate", {"old": "100", "new": "120"})
    assert result["result"] == "20"
    assert result["unit"] == "percent"
    assert calculate("gross_margin", {"revenue": "120", "cost": "72"})["result"] == "40"
    assert calculate("current_ratio", {"current_assets": "90", "current_liabilities": "45"})["result"] == "2"
    assert calculate("debt_ratio", {"liabilities": "80", "assets": "200"})["result"] == "40"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "1+2", "__import__('os')", "1e999", 0.1, True])
def test_rejects_unsafe_or_inexact_inputs(bad):
    with pytest.raises(CalculationError):
        calculate("add", {"a": bad, "b": "1"})


def test_division_by_zero_and_missing_fields_are_explicit():
    with pytest.raises(CalculationError, match="undefined"):
        calculate("divide", {"a": "1", "b": "0"})
    with pytest.raises(CalculationError, match="exactly"):
        calculate("ratio", {"numerator": "1"})
    with pytest.raises(CalculationError, match="Unsupported"):
        calculate("eval", {"a": "1", "b": "1"})


def test_finqa_arithmetic_references_and_constants():
    assert evaluate_program("subtract(120, 100), divide(#0, 100), multiply(#1, const_100)")["result"] == "20"
    assert evaluate_program("multiply(2, const_m1), add(#0, 5), EOF")["result"] == "3"
    assert Decimal(evaluate_program("divide(1, 3)")["result"]) > Decimal("0.3333333333333333333333333333")


@pytest.mark.parametrize("program", ["__import__('os').system('echo bad')", "add(add(1,2),3)",
    "multiply(#0,100)", "table_sum(revenue,none)", "add(1,2);print(1)", "", "add(1,2),", "divide(1,0)"])
def test_program_is_a_closed_language(program):
    with pytest.raises(CalculationError):
        evaluate_program(program)
