"""Versioned golden-dataset gate over recorded outputs, suitable for CI exit codes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from .scoring import SCORER_VERSION, evaluate
from .store import dumps


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a JSON object")
    return data


def build_report(dataset: dict[str, Any], predictions: dict[str, Any]) -> dict[str, Any]:
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset must contain a nonempty cases list")
    if not isinstance(dataset.get("version"), str) or not dataset["version"]:
        raise ValueError("dataset version is required")
    if not isinstance(predictions.get("version"), str) or not predictions["version"]:
        raise ValueError("prediction version is required")
    ids = [case.get("id") for case in cases]
    if not all(isinstance(case_id, str) and case_id for case_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("case IDs must be nonempty and unique")
    observed = predictions.get("predictions")
    if not isinstance(observed, dict):
        raise ValueError("predictions must map case IDs to actual execution snapshots")
    if unknown := set(observed) - set(ids):
        raise ValueError(f"unknown prediction IDs: {', '.join(sorted(unknown))}")
    rows: dict[str, Any] = {}
    buckets: dict[str, list[float]] = {}
    missing = []
    for case in cases:
        actual = observed.get(case["id"])
        if actual is None:
            missing.append(case["id"])
            actual = {}
        if not isinstance(actual, dict):
            raise ValueError(f"prediction {case['id']} must be an object")
        scores = evaluate(actual, case["expected"])
        metric_values = {score.name: score.value for score in scores}
        # Missing outputs are zero for all checks, including negative safety scenarios.
        if case["id"] in missing:
            metric_values = dict.fromkeys(metric_values, 0.0)
        for name, value in metric_values.items():
            buckets.setdefault(name, []).append(value)
        rows[case["id"]] = {"overall": mean(metric_values.values()), "scores": metric_values}
    return {
        "schema_version": 1, "scorer_version": SCORER_VERSION,
        "dataset_version": dataset["version"],
        "dataset_sha256": hashlib.sha256(dumps(dataset).encode("utf-8")).hexdigest(),
        "prediction_version": predictions["version"],
        "overall": mean(row["overall"] for row in rows.values()),
        "metrics": {name: mean(values) for name, values in sorted(buckets.items())},
        "missing_predictions": missing, "cases": rows,
    }


def check_gate(report: dict[str, Any], baseline: dict[str, Any] | None = None, *,
               min_score: float = 0.95, max_regression: float = 0.05) -> list[str]:
    if not 0 <= min_score <= 1 or not 0 <= max_regression <= 1:
        raise ValueError("gate thresholds must be within [0, 1]")
    failures = []
    if report["missing_predictions"]:
        failures.append("Missing predictions: " + ", ".join(report["missing_predictions"]))
    if report["overall"] + 1e-12 < min_score:
        failures.append(f"Overall {report['overall']:.4f} below minimum {min_score:.4f}")
    for case_id, case in report["cases"].items():
        for safety in ("approval_safety", "forbidden_tool_safety"):
            if safety in case["scores"] and case["scores"][safety] < 1:
                failures.append(f"{case_id}: mandatory {safety} check failed")
    if baseline is not None:
        for field in ("schema_version", "scorer_version", "dataset_version", "dataset_sha256"):
            if baseline.get(field) != report[field]:
                raise ValueError(f"baseline {field} differs; rebaseline explicitly after reviewing the dataset/scorer change")
        if set(baseline.get("cases", {})) != set(report["cases"]):
            raise ValueError("baseline case set differs")
        if set(baseline.get("metrics", {})) != set(report["metrics"]):
            raise ValueError("baseline metric set differs")
        for metric, value in report["metrics"].items():
            if baseline["metrics"][metric] - value > max_regression + 1e-12:
                failures.append(f"Metric {metric} regressed from {baseline['metrics'][metric]:.4f} to {value:.4f}")
        for case_id, case in report["cases"].items():
            old = baseline["cases"][case_id]
            if set(old["scores"]) != set(case["scores"]):
                raise ValueError(f"baseline score set differs for {case_id}")
            for metric, value in case["scores"].items():
                if old["scores"][metric] - value > max_regression + 1e-12:
                    failures.append(f"{case_id}: {metric} regressed from {old['scores'][metric]:.4f} to {value:.4f}")
    return failures


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score recorded outputs against golden data and reject regressions")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--baseline", type=Path)
    group.add_argument("--write-baseline", type=Path, help="Explicitly create a reviewed baseline from these recorded outputs")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-score", type=float, default=0.95)
    parser.add_argument("--max-regression", type=float, default=0.05)
    args = parser.parse_args(argv)
    try:
        report = build_report(read_json(args.dataset), read_json(args.predictions))
        baseline = read_json(args.baseline) if args.baseline else None
        failures = check_gate(report, baseline, min_score=args.min_score, max_regression=args.max_regression)
        report.update(passed=not failures, failures=failures)
        if args.output:
            write_json(args.output, report)
        if args.write_baseline and not failures:
            write_json(args.write_baseline, report)
        print(json.dumps({"passed": not failures, "overall": report["overall"], "failures": failures}, ensure_ascii=False))
        return int(bool(failures))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Gate configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
