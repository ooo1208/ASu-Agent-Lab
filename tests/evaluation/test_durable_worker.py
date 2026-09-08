import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from asu_eval.scoring import evaluate
from asu_eval.store import EvaluationStore, LeaseLost
from asu_eval.worker import EvaluationWorker


class RecordingSender:
    def __init__(self, *, fail_scores=0, fail_traces=0):
        self.fail_scores, self.fail_traces = fail_scores, fail_traces
        self.events = []

    def send_trace(self, payload):
        self.events.append(("trace", payload))
        if self.fail_traces:
            self.fail_traces -= 1
            raise OSError("simulated remote outage")

    def send(self, payload):
        self.events.append(("score", payload))
        if self.fail_scores:
            self.fail_scores -= 1
            raise OSError("simulated remote outage")


class DurableWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "evaluation.sqlite3"
        self.store = EvaluationStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def enqueue(self, **kwargs):
        data = dict(user_id="alice", trace_id="business-trace", session_id="session", version="v1",
                    actual={"answer_numeric": "0.30", "task_completed": True},
                    expected={"answer_numeric": "0.3", "task_completed": True}, now=100)
        data.update(kwargs)
        return self.store.enqueue(**data)

    def test_restart_recovers_expired_job_and_fences_old_worker(self):
        job_id = self.enqueue()
        old = self.store.claim_job(now=100, lease_seconds=10)
        restarted = EvaluationStore(self.path)
        self.assertIsNone(restarted.claim_job(now=109))
        new = restarted.claim_job(now=111)
        self.assertEqual(job_id, new["id"])
        self.assertNotEqual(old["lease_token"], new["lease_token"])
        scores = evaluate(new["payload"]["actual"], new["payload"]["expected"])
        with self.assertRaises(LeaseLost):
            self.store.complete_job(job_id, old["lease_token"], scores, now=111)
        restarted.complete_job(job_id, new["lease_token"], scores, now=112)
        result = restarted.get_job("alice", job_id)
        self.assertEqual("complete", result["status"])
        self.assertEqual(2, len(result["scores"]))
        self.assertEqual({"pending": 3}, result["delivery"])

    def test_two_simultaneous_claimers_get_one_job(self):
        self.enqueue()
        with ThreadPoolExecutor(max_workers=8) as executor:
            claims = list(executor.map(lambda _: self.store.claim_job(now=100), range(20)))
        self.assertEqual(1, sum(item is not None for item in claims))

    def test_same_run_reuses_job_but_conflicting_snapshot_is_rejected(self):
        one = self.enqueue(run_id="client-run")
        self.assertEqual(one, self.enqueue(run_id="client-run"))
        self.assertNotEqual(one, self.enqueue(run_id="client-run", user_id="bob"))
        with self.assertRaisesRegex(ValueError, "different snapshot"):
            self.enqueue(run_id="client-run", actual={"task_completed": False})

    def test_invalid_result_rolls_back_entire_transaction(self):
        from asu_eval.scoring import Score
        job_id = self.enqueue()
        claimed = self.store.claim_job(now=100)
        with self.assertRaises(ValueError):
            self.store.complete_job(job_id, claimed["lease_token"], [Score("ok", 1, "ok"), Score("bad", 3, "bad")], now=101)
        job = self.store.get_job("alice", job_id)
        self.assertEqual([], job["scores"])
        self.assertEqual({}, job["delivery"])

    def test_offline_results_are_durable_and_not_misreported_as_remote(self):
        job_id = self.enqueue()
        worker = EvaluationWorker(self.store, clock=lambda: 101)
        worker.drain()
        self.assertEqual({"pending": 3}, self.store.get_job("alice", job_id)["delivery"])
        self.assertEqual(0, EvaluationWorker(EvaluationStore(self.path), clock=lambda: 102).drain())

    def test_outbox_retries_backoff_same_score_id_and_only_after_trace(self):
        job_id = self.enqueue(expected={"task_completed": True})
        sender = RecordingSender(fail_scores=1)
        now = [100.0]
        worker = EvaluationWorker(self.store, sender, clock=lambda: now[0])
        worker.drain()
        self.assertEqual(["trace", "score"], [kind for kind, _ in sender.events])
        self.assertEqual({"sent": 1, "pending": 1}, self.store.get_job("alice", job_id)["delivery"])
        now[0] = 101
        self.assertFalse(worker.run_cycle())
        now[0] = 102
        self.assertTrue(worker.run_cycle())
        score_payloads = [payload for kind, payload in sender.events if kind == "score"]
        self.assertEqual(score_payloads[0], score_payloads[1])
        self.assertEqual({"sent": 2}, self.store.get_job("alice", job_id)["delivery"])

    def test_trace_outage_blocks_score_until_trace_recovers(self):
        self.enqueue(expected={"task_completed": True})
        sender = RecordingSender(fail_traces=1)
        now = [100.0]
        worker = EvaluationWorker(self.store, sender, clock=lambda: now[0])
        worker.drain()
        self.assertEqual(["trace"], [kind for kind, _ in sender.events])
        now[0] = 102
        worker.drain()
        self.assertEqual(["trace", "trace", "score"], [kind for kind, _ in sender.events])

    def test_remote_accept_then_worker_crash_preserves_retry_score_id(self):
        self.enqueue(expected={"task_completed": True})
        EvaluationWorker(self.store, clock=lambda: 100).drain()
        trace = self.store.claim_score(now=100, lease_seconds=2)
        self.store.acknowledge_score(trace["id"], trace["lease_token"], now=100)
        old = self.store.claim_score(now=100, lease_seconds=2)
        remote_received = old["payload"]["id"]
        # Simulate process death after remote accepted the score and before local ACK.
        new = EvaluationStore(self.path).claim_score(now=103)
        self.assertEqual(remote_received, new["payload"]["id"])
        with self.assertRaises(LeaseLost):
            self.store.acknowledge_score(old["id"], old["lease_token"], now=103)
        self.store.acknowledge_score(new["id"], new["lease_token"], now=103)

    def test_exhausted_job_lease_becomes_failed(self):
        job_id = self.enqueue(max_attempts=1)
        self.store.claim_job(now=100, lease_seconds=1)
        self.assertIsNone(self.store.claim_job(now=102))
        self.assertEqual("failed", self.store.get_job("alice", job_id)["status"])
        with self.assertRaises(KeyError):
            self.store.retry_failed("bob", job_id)
        self.store.retry_failed("alice", job_id)
        self.assertEqual("pending", self.store.get_job("alice", job_id)["status"])

    def test_feedback_isolation_and_explicit_golden_promotion(self):
        job_id = self.enqueue(input_data="synthetic question")
        self.assertIsNone(self.store.get_job("bob", job_id))
        self.assertEqual([], self.store.list_jobs("bob"))
        with self.assertRaises(KeyError):
            self.store.add_feedback(user_id="bob", job_id=job_id, rating=0)
        feedback_id = self.store.add_feedback(user_id="alice", job_id=job_id, rating=0,
                                              corrected_expected={"answer_numeric": "0.31"})
        self.assertEqual([], self.store.export_golden("alice", "reviewed-v1")["cases"])
        with self.assertRaises(KeyError):
            self.store.promote_feedback(user_id="bob", feedback_id=feedback_id, dataset_version="reviewed-v1")
        case_id = self.store.promote_feedback(user_id="alice", feedback_id=feedback_id, dataset_version="reviewed-v1")
        self.assertEqual(case_id, self.store.promote_feedback(user_id="alice", feedback_id=feedback_id, dataset_version="reviewed-v1"))
        golden = self.store.export_golden("alice", "reviewed-v1")
        self.assertEqual(1, len(golden["cases"]))
        self.assertEqual("synthetic question", golden["cases"][0]["input"])
        self.assertEqual([], self.store.export_golden("bob", "reviewed-v1")["cases"])


if __name__ == "__main__":
    unittest.main()
