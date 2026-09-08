"""Per-request tools bound to a trusted authenticated owner, never a model-supplied id."""

from .calculator import CalculationError, calculate, evaluate_program
from .evidence import EvidenceError, EvidenceStore, _scope
from .review import verify_claim


def finance_functions(store: EvidenceStore, user_id: str, namespace: str = "default") -> dict:
    """Pure callable adapters; no LangChain dependency required."""
    _scope(user_id, namespace)

    def search_financial_evidence(query: str, limit: int = 5) -> dict:
        """Search the authenticated user's financial documents. Cite returned citation_id values."""
        try:
            return {"results": store.search(user_id, query, namespace=namespace, limit=limit), "retrieval": "SQLite FTS5 lexical"}
        except EvidenceError as exc:
            return {"error": str(exc)}

    def get_financial_citation(citation_id: str) -> dict:
        """Read an evidence fragment by citation id within the authenticated user's namespace."""
        result = store.get_citation(user_id, citation_id, namespace=namespace)
        return result if result else {"error": "Citation unavailable in this namespace."}

    def calculate_financial_metric(operation: str, values: dict[str, str]) -> dict:
        """Decimal calculator. add/subtract/multiply/divide use a,b; ratio uses numerator,denominator;
        change_rate uses old,new; debt_ratio uses liabilities,assets; current_ratio uses
        current_assets,current_liabilities; gross_margin uses revenue,cost; net_margin uses
        net_profit,revenue; return_on_equity uses net_profit,equity. Pass decimal strings.
        Inputs must share currency, scale and reporting period. Percent unit means 25 = 25%.
        """
        try:
            return calculate(operation, values)
        except CalculationError as exc:
            return {"error": str(exc)}

    def run_financial_arithmetic(program: str) -> dict:
        """Execute only flat add/subtract/multiply/divide FinQA-style calls; #0 references prior results.
        No Python, nested calls, table operations, attributes, imports or arbitrary code are accepted.
        """
        try:
            return evaluate_program(program)
        except CalculationError as exc:
            return {"error": str(exc)}

    def review_financial_claim(operation: str, values: dict[str, str], reported_value: str,
                               citation_ids: list[str]) -> dict:
        """Check citation access, literal input numbers and arithmetic. Still requires unit, period and
        semantic review. This check never issues a credit rating or lending decision.
        """
        try:
            return verify_claim(store, user_id, operation=operation, values=values, reported_value=reported_value,
                                citation_ids=citation_ids, namespace=namespace)
        except (CalculationError, EvidenceError) as exc:
            return {"error": str(exc)}

    return {fn.__name__: fn for fn in (search_financial_evidence, get_financial_citation,
        calculate_financial_metric, run_financial_arithmetic, review_financial_claim)}


def create_finance_tools(store: EvidenceStore, user_id: str, namespace: str = "default") -> list:
    """Build LangChain tools after authentication; recreate for each user/request."""
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise ImportError("LangChain adapters require langchain-core; use finance_functions for plain Python.") from exc
    return [tool(fn) for fn in finance_functions(store, user_id, namespace).values()]
