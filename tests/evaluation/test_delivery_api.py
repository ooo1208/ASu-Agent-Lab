import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from asu_eval.delivery import DeliveryError, LangfuseScoreSender, remote_trace_id
from asu_eval.store import EvaluationStore


class DeliveryTests(unittest.TestCase):
    def test_http_payload_uses_stable_ids_and_otel_endpoint(self):
        sender = LangfuseScoreSender("http://localhost:3000", "public", "secret")
        response = MagicMock()
        response.__enter__.return_value = response
        response.status, response.read.return_value = 200, b"{}"
        trace = {"traceId": "a" * 32, "observationId": "b" * 16, "user_id": "alice",
                 "session_id": "s", "version": "v1", "input": "synthetic", "output": {"latency_ms": 10},
                 "captured_at": 100, "business_trace_id": "original"}
        with patch("asu_eval.delivery.urlopen", return_value=response) as mocked:
            sender.send_trace(trace)
            request = mocked.call_args.args[0]
            self.assertEqual("http://localhost:3000/api/public/otel/v1/traces", request.full_url)
            payload = json.loads(request.data)
            span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
            self.assertEqual(trace["traceId"], span["traceId"])
            self.assertLess(int(span["startTimeUnixNano"]), int(span["endTimeUnixNano"]))
            sender.send({"id": "score-id", "traceId": trace["traceId"], "name": "task_completion", "value": 1})
            self.assertEqual("score-id", json.loads(mocked.call_args.args[0].data)["id"])

    def test_otel_partial_failure_is_not_acknowledged(self):
        sender = LangfuseScoreSender("http://localhost:3000", "public", "secret")
        response = MagicMock()
        response.__enter__.return_value = response
        response.status, response.read.return_value = 200, b'{"partialSuccess":{"rejectedSpans":"1"}}'
        with patch("asu_eval.delivery.urlopen", return_value=response), self.assertRaises(DeliveryError):
            sender._post(sender.trace_url, {}, trace=True)

    def test_remote_transport_requires_https_and_ids_are_tenant_scoped(self):
        with self.assertRaises(ValueError):
            LangfuseScoreSender("http://public.example", "public", "secret")
        self.assertNotEqual(remote_trace_id("alice", "same"), remote_trace_id("bob", "same"))
        self.assertNotEqual(remote_trace_id("alice:team", "trace"), remote_trace_id("alice", "team:trace"))


try:
    from fastapi import FastAPI, Header
    from fastapi.testclient import TestClient
    from asu_eval.api import create_router
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False


@unittest.skipUnless(HAVE_FASTAPI, "FastAPI + httpx are optional for core evaluation tests")
class ApiIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EvaluationStore(Path(self.temp.name) / "api.sqlite3")
        app = FastAPI()

        def identity(x_test_user: str = Header()):
            return {"user_id": x_test_user}

        app.include_router(create_router(self.store, identity), prefix="/api")
        self.client = TestClient(app)
        self.body = {"trace_id": "t", "session_id": "s", "version": "v1",
                     "actual": {"task_completed": True}, "expected": {"task_completed": True}}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def call(self, method, path, user="alice", **kwargs):
        return self.client.request(method, "/api/evaluation" + path, headers={"x-test-user": user}, **kwargs)

    def test_job_feedback_retry_and_golden_are_owner_scoped(self):
        response = self.call("POST", "/jobs", json=self.body)
        self.assertEqual(202, response.status_code, response.text)
        job_id = response.json()["job_id"]
        self.assertEqual(404, self.call("GET", f"/jobs/{job_id}", user="bob").status_code)
        self.assertEqual([], self.call("GET", "/jobs", user="bob").json())
        feedback = {"rating": 0, "corrected_expected": {"task_completed": False}}
        self.assertEqual(404, self.call("POST", f"/jobs/{job_id}/feedback", user="bob", json=feedback).status_code)
        self.assertEqual(404, self.call("POST", f"/jobs/{job_id}/retry", user="bob").status_code)
        feedback_id = self.call("POST", f"/jobs/{job_id}/feedback", json=feedback).json()["feedback_id"]
        path = f"/feedback/{feedback_id}/promote"
        self.assertEqual(404, self.call("POST", path, user="bob", json={"dataset_version": "v2"}).status_code)
        self.assertEqual(201, self.call("POST", path, json={"dataset_version": "v2"}).status_code)
        self.assertEqual([], self.call("GET", "/golden/v2", user="bob").json()["cases"])
        self.assertEqual(1, len(self.call("GET", "/golden/v2").json()["cases"]))

    def test_body_cannot_override_authenticated_owner(self):
        response = self.call("POST", "/jobs", json={**self.body, "user_id": "bob"})
        self.assertEqual(422, response.status_code)
        self.assertEqual(422, self.client.post("/api/evaluation/jobs", json=self.body).status_code)


if __name__ == "__main__":
    unittest.main()
