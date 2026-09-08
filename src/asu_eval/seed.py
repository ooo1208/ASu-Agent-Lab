"""Import explicit, recorded fixture outputs into the local durable queue."""

import argparse
import json
from pathlib import Path

from .gate import build_report, read_json
from .store import EvaluationStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enqueue supplied recorded outputs; does not call a model")
    parser.add_argument("--db", type=Path, default=Path("data/evaluation.sqlite3"))
    parser.add_argument("--dataset", type=Path, default=Path("evals/golden.synthetic.json"))
    parser.add_argument("--predictions", type=Path, default=Path("evals/predictions.baseline.json"))
    parser.add_argument("--user-id", default="synthetic-demo")
    args = parser.parse_args(argv)
    dataset, predictions = read_json(args.dataset), read_json(args.predictions)
    report = build_report(dataset, predictions)
    if report["missing_predictions"]:
        parser.error("cannot enqueue missing predictions")
    store = EvaluationStore(args.db)
    ids = []
    for case in dataset["cases"]:
        identity = f"{dataset['version']}:{predictions['version']}:{case['id']}"
        ids.append(store.enqueue(user_id=args.user_id, trace_id=case["id"], session_id="synthetic-demo",
                                 actual=predictions["predictions"][case["id"]], expected=case["expected"],
                                 version=predictions["version"], run_id=identity, input_data=case.get("input")))
    print(json.dumps({"enqueued": len(ids), "job_ids": ids, "source": "supplied recorded outputs; no model executed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
