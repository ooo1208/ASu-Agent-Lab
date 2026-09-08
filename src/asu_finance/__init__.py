"""Local financial evidence and deterministic arithmetic; no credit decisions."""

from .calculator import CalculationError, calculate, evaluate_program
from .evidence import EvidenceError, EvidenceStore

__all__ = ["CalculationError", "EvidenceError", "EvidenceStore", "calculate", "evaluate_program"]


def create_finance_tools(*args, **kwargs):
    from .tools import create_finance_tools as factory
    return factory(*args, **kwargs)


def create_finance_router(*args, **kwargs):
    from .api import create_finance_router as factory
    return factory(*args, **kwargs)
