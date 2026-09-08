import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from asu_eval.gate import build_report, check_gate, read_json
from asu_eval.scoring import decimal_value, evaluate

ROOT = Path(__file__).resolve().parents[2]


class ScoringTests(unittest.TestCase):
    def values(self, actual, expected):
        return {score.name: score.value for score in evaluate(actual, expected)}

    def test_decimal_boundary_and_nonfinite_rejected(self):
        self.assertEqual(1, self.values({"answer_numeric": "0.30000000000000000001"},
                                      {"answer_numeric": "0.3", "absolute_tolerance": "0.00000000000000000001"})["numeric_accuracy"])
        self.assertEqual(0, self.values({"answer_numeric": "0.30000000000000000002"},
                                      {"answer_numeric": "0.3", "absolute_tolerance": "0.00000000000000000001"})["numeric_accuracy"])
        for value in ("NaN", "Infinity", True, "not a number"):
            with self.assertRaises(ValueError):
                decimal_value(value)
        self.assertEqual(0, self.values({"answer_numeric": "1000000000000000000000000000000.01"},
                                      {"answer_numeric": "1000000000000000000000000000000", "absolute_tolerance": "0.001"})["numeric_accuracy"])

    def test_all_repeated_calls_must_have_required_parameters(self):
        actual = {"tool_calls": [{"name": "get", "arguments": {"sku": "A"}}, {"name": "get", "arguments": {}}]}
        result = self.values(actual, {"required_tools": {"get": ["sku"]}})
        self.assertEqual(1, result["tool_selection"])
        self.assertEqual(0, result["parameter_completeness"])

    def test_missing_safety_evidence_fails_and_denied_call_is_not_execution(self):
        expected = {"requires_approval": True, "forbidden_tools": ["delete"]}
        self.assertEqual({"approval_safety": 0, "forbidden_tool_safety": 0}, self.values({}, expected))
        actual = {"tool_calls": [{"name": "delete", "status": "denied"}],
                  "safety": {"approved": False, "side_effect_performed": False}}
        self.assertEqual({"approval_safety": 1, "forbidden_tool_safety": 1}, self.values(actual, expected))

    def test_citation_recall_and_precision_detect_hallucinated_reference(self):
        actual = {"citations": ["A", "invented"]}
        result = self.values(actual, {"evidence_ids": ["A", "B"]})
        self.assertEqual({"evidence_recall": 0.5, "citation_precision": 0.5}, result)

    def test_unknown_or_empty_expectations_cannot_silently_pass(self):
        for expected in ({}, {"made_up_metric": True}, {"task_completed": "true"}, {"relative_tolerance": "-1"}):
            with self.assertRaises(ValueError):
                evaluate({}, expected)

    def test_malformed_execution_evidence_is_rejected_as_input(self):
        for actual in ({"tool_calls": [{"name": []}]}, {"tool_calls": [{"name": "read", "status": {}}]},
                       {"citations": [{}]}, {"task_completed": "true"}):
            with self.assertRaises(ValueError):
                evaluate(actual, {"task_completed": True, "forbidden_tools": []})


class GateTests(unittest.TestCase):
    def setUp(self):
        self.dataset = read_json(ROOT / "evals/golden.synthetic.json")
        self.baseline = read_json(ROOT / "evals/baseline.synthetic.json")
        self.predictions = read_json(ROOT / "evals/predictions.baseline.json")

    def test_baseline_passes_and_regression_fails(self):
        report = build_report(self.dataset, self.predictions)
        self.assertEqual([], check_gate(report, self.baseline))
        broken = read_json(ROOT / "evals/predictions.regressed.json")
        failures = check_gate(build_report(self.dataset, broken), self.baseline)
        self.assertTrue(any("approval_safety" in failure for failure in failures))
        self.assertTrue(any("numeric_accuracy" in failure for failure in failures))
        self.assertTrue(any("citation_precision" in failure for failure in failures))

    def test_missing_prediction_fails_even_with_zero_minimum(self):
        self.predictions["predictions"].pop("approval-denied")
        failures = check_gate(build_report(self.dataset, self.predictions), min_score=0)
        self.assertTrue(any("Missing predictions" in failure for failure in failures))

    def test_dataset_change_cannot_reuse_stale_baseline(self):
        self.dataset["cases"][0]["expected"]["absolute_tolerance"] = "1"
        with self.assertRaisesRegex(ValueError, "dataset_sha256"):
            check_gate(build_report(self.dataset, self.predictions), self.baseline)

    def test_per_case_regression_not_hidden_by_dataset_average(self):
        report = build_report(self.dataset, self.predictions)
        report["cases"]["zero-value"]["scores"]["numeric_accuracy"] = 0
        failures = check_gate(report, self.baseline)
        self.assertTrue(any("zero-value: numeric_accuracy regressed" in failure for failure in failures))

    def test_cli_uses_nonzero_exit_for_regression(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        common = [sys.executable, "-m", "asu_eval.gate", "--dataset", "evals/golden.synthetic.json",
                  "--baseline", "evals/baseline.synthetic.json", "--predictions"]
        passing = subprocess.run(common + ["evals/predictions.baseline.json"], cwd=ROOT, env=env, capture_output=True, text=True)
        failing = subprocess.run(common + ["evals/predictions.regressed.json"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(0, passing.returncode, passing.stderr)
        self.assertEqual(1, failing.returncode, failing.stderr)
        self.assertFalse(json.loads(failing.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
