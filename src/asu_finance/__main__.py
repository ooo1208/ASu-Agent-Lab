"""Local CLI: python -m asu_finance --help."""

import argparse
import json
import sys
from pathlib import Path

from .calculator import CalculationError, calculate, evaluate_program
from .evidence import EvidenceError, EvidenceStore
from .finqa import import_finqa, load_finqa


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Local financial evidence and Decimal tools (demo; no credit decisions).")
    parser.add_argument("--db", default=".data/finance.sqlite3")
    parser.add_argument("--user", default="demo", help="Trusted local owner id. HTTP obtains this from authentication.")
    parser.add_argument("--namespace", default="default")
    actions = parser.add_subparsers(dest="action", required=True)
    ingest = actions.add_parser("ingest", help="Import a UTF-8 txt/md/csv file or text PDF")
    ingest.add_argument("path", type=Path)
    search = actions.add_parser("search", help="Lexical FTS5 search in one owner/namespace")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    citation = actions.add_parser("citation")
    citation.add_argument("citation_id")
    calc = actions.add_parser("calculate")
    calc.add_argument("operation")
    calc.add_argument("values", help='JSON object of decimal strings, e.g. {"a":"0.1","b":"0.2"}')
    program = actions.add_parser("program")
    program.add_argument("source", help='e.g. "subtract(120, 100), divide(#0, 100)"')
    finqa = actions.add_parser("import-finqa", help="Import locally obtained FinQA evidence; never downloads datasets")
    finqa.add_argument("path", type=Path)
    finqa.add_argument("--split", choices=["train", "dev", "test", "private_test"])
    args = parser.parse_args(argv)
    try:
        if args.action == "calculate":
            values = json.loads(args.values)
            if not isinstance(values, dict):
                raise CalculationError("Values must be a JSON object.")
            result = calculate(args.operation, values)
        elif args.action == "program":
            result = evaluate_program(args.source)
        else:
            store = EvidenceStore(args.db)
            if args.action == "ingest":
                result = store.ingest(args.user, args.path.name, args.path.read_bytes(), namespace=args.namespace)
            elif args.action == "search":
                result = store.search(args.user, args.query, namespace=args.namespace, limit=args.limit)
            elif args.action == "citation":
                result = store.get_citation(args.user, args.citation_id, namespace=args.namespace)
                if result is None:
                    raise EvidenceError("Citation unavailable in this namespace.")
            else:
                imported = import_finqa(store, args.user, load_finqa(args.path, split=args.split), namespace=args.namespace)
                result = {"imported": len(imported), "documents": imported,
                          "note": "Only source evidence was indexed. Namespace has :split appended; labels remain outside retrieval."}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (EvidenceError, CalculationError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
