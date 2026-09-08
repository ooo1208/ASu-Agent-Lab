"""Deterministic claim checks. Passing is not a financial conclusion or credit rating."""

import re

from .calculator import CalculationError, calculate, decimal_value
from .evidence import EvidenceStore


def verify_claim(store: EvidenceStore, user_id: str, *, operation: str, values: dict,
                 reported_value: str, citation_ids: list[str], namespace: str = "default",
                 tolerance: str = "0.000001") -> dict:
    """Check scoped citations, arithmetic and literal input-number coverage.

    This does not prove unit/period/entity alignment, document authenticity, or
    semantic support. A reviewer must check those before making any conclusion.
    """
    if not citation_ids or len(citation_ids) > 20:
        raise CalculationError("A claim requires 1–20 citation ids.")
    allowed_error = decimal_value(tolerance)
    if not 0 <= allowed_error <= 1:
        raise CalculationError("Absolute tolerance must be between 0 and 1.")
    calculation = calculate(operation, values)
    reported = decimal_value(reported_value)
    citations, unavailable = [], []
    for citation_id in dict.fromkeys(citation_ids):
        item = store.get_citation(user_id, citation_id, namespace=namespace)
        if item:
            citations.append(item)
        else:
            # Deliberately same response for another user's id and a missing id.
            unavailable.append(citation_id)
    evidence_numbers = set()
    for item in citations:
        for token in re.findall(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?(?![\w.])", item["text"]):
            try:
                evidence_numbers.add(decimal_value(token.replace(",", "")))
            except CalculationError:
                pass
    absent = [key for key, value in calculation["inputs"].items() if decimal_value(value) not in evidence_numbers]
    arithmetic_matches = abs(reported - decimal_value(calculation["result"])) <= allowed_error
    return {"checks_passed": not unavailable and not absent and arithmetic_matches,
            "arithmetic_matches": arithmetic_matches, "unavailable_citations": unavailable,
            "inputs_not_found_in_evidence": absent, "calculation": calculation,
            "citations": citations, "requires_semantic_review": True,
            "scope": "Citation access, literal number coverage and arithmetic only; no credit decision."}
