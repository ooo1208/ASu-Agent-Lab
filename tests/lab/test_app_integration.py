import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from asu_eval.worker import EvaluationWorker
from asu_lab import services


def stream_events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]


def ask(lab_client, headers, *, thread="order-thread", message="演示下单 2 件"):
    response = lab_client.post("/api/chat/stream", headers=headers, json={"thread_id": thread, "message": message})
    return stream_events(response)


def install_erp_transport(monkeypatch, *, status=200, payload=None):
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=payload or {"code": 200, "data": {"id": 42, "orderNumber": "SYNTHETIC-42"}})

    def factory(*args, **kwargs):
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("asu_lab.app.httpx.AsyncClient", factory)
    return requests


def test_real_auth_registration_login_and_hashed_sessions(lab_client, users):
    assert lab_client.get("/api/auth/me").status_code == 401
    invalid = lab_client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert invalid.status_code == 401
    login = lab_client.post("/api/auth/login", json={"username": "ALICE", "password": "test-password-2026"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert lab_client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).json()["user_id"] == users["alice"]["id"]
    assert lab_client.post("/api/auth/register", json={"username": "Alice", "password": "test-password-2026"}).status_code == 400
    with lab_client.app.state.local_state.connect() as db:
        stored_password = db.execute("SELECT password_hash FROM users WHERE username='alice'").fetchone()[0]
        hashes = [row[0] for row in db.execute("SELECT token_hash FROM sessions")]
    assert "test-password-2026" not in stored_password
    assert token not in hashes


def test_authenticated_users_cannot_read_mutate_or_resume_each_others_thread(lab_client, users):
    alice, bob = users["alice"]["headers"], users["bob"]["headers"]
    ask(lab_client, alice)
    assert lab_client.get("/api/history", headers=bob).json()["sessions"] == []
    for route in ("/api/history/order-thread/messages", "/api/chat/order-thread"):
        assert lab_client.get(route, headers=bob).status_code == 404
    assert lab_client.patch("/api/history/order-thread", headers=bob, params={"title": "stolen"}).status_code == 404
    assert lab_client.delete("/api/history/order-thread", headers=bob).status_code == 404
    assert lab_client.post("/api/chat/stream", headers=bob, json={"thread_id": "order-thread", "message": "steal"}).status_code == 404
    assert lab_client.post("/api/chat/order-thread/resume", headers=bob, json={"resume": {"decisions": [{"type": "approve"}]}}).status_code == 404
    assert lab_client.get("/api/chat/order-thread", headers=alice).json()["pending"]["status"] == "awaiting_approval"


def test_documents_citations_and_captured_evaluations_are_isolated(lab_client, users):
    alice, bob = users["alice"]["headers"], users["bob"]["headers"]
    doc = lab_client.post("/api/finance/documents", headers=alice, json={"filename": "synthetic.txt", "content": "UNIQUE_SYNTHETIC_REVENUE is 12345."})
    assert doc.status_code == 201, doc.text
    document = doc.json()
    citation = document["citation_ids"][0]
    assert lab_client.get("/api/finance/search", headers=alice, params={"q": "UNIQUE_SYNTHETIC_REVENUE"}).json()["results"]
    assert lab_client.get("/api/finance/search", headers=bob, params={"q": "UNIQUE_SYNTHETIC_REVENUE"}).json()["results"] == []
    assert lab_client.get(f"/api/finance/citations/{citation}", headers=bob).status_code == 404
    assert lab_client.delete(f"/api/finance/documents/{document['document_id']}", headers=bob).status_code == 404
    events = ask(lab_client, alice, message="UNIQUE_SYNTHETIC_REVENUE", thread="evidence-thread")
    assert any(citation in event.get("content", "") for event in events)
    own_jobs = lab_client.get("/api/evaluation/jobs", headers=alice).json()
    assert len(own_jobs) == 1
    assert lab_client.get("/api/evaluation/jobs", headers=bob).json() == []
    job_id = own_jobs[0]["id"]
    assert lab_client.get(f"/api/evaluation/jobs/{job_id}", headers=bob).status_code == 404
    assert lab_client.post(f"/api/evaluation/jobs/{job_id}/feedback", headers=bob, json={"rating": 0}).status_code == 404
    EvaluationWorker(services.evaluation_store()).drain()
    result = lab_client.get(f"/api/evaluation/jobs/{job_id}", headers=alice).json()
    assert result["status"] == "complete"
    assert result["payload"]["actual"]["tool_calls"][0]["arguments"]["query"] == "UNIQUE_SYNTHETIC_REVENUE"


def test_reject_approval_makes_zero_erp_calls_and_cannot_be_replayed(lab_client, users, monkeypatch):
    requests = install_erp_transport(monkeypatch)
    headers = users["alice"]["headers"]
    assert any(event["type"] == "interrupt" for event in ask(lab_client, headers))
    body = {"resume": {"decisions": [{"type": "reject"}]}}
    stream_events(lab_client.post("/api/chat/order-thread/resume", headers=headers, json=body))
    assert requests == []
    for decision in ("reject", "approve"):
        response = lab_client.post("/api/chat/order-thread/resume", headers=headers, json={"resume": {"decisions": [{"type": decision}]}})
        assert response.status_code == 409
    assert requests == []
    jobs = services.evaluation_store().list_jobs(users["alice"]["id"])
    assert len(jobs) == 2
    for job in jobs:
        snapshot = services.evaluation_store().get_job(users["alice"]["id"], job["id"])["payload"]["actual"]
        assert snapshot["safety"]["side_effect_performed"] is False


def test_approved_request_calls_erp_once_with_idempotency_then_enqueues_evaluation(lab_client, users, monkeypatch):
    requests = install_erp_transport(monkeypatch)
    headers = users["alice"]["headers"]
    ask(lab_client, headers)
    original = lab_client.get("/api/chat/order-thread", headers=headers).json()["pending"]
    body = {"resume": {"decisions": [{"type": "approve"}]}}
    events = stream_events(lab_client.post("/api/chat/order-thread/resume", headers=headers, json=body))
    assert any(event["type"] == "done" for event in events)
    assert len(requests) == 1
    assert requests[0].headers["Idempotency-Key"] == original["request_id"]
    payload = json.loads(requests[0].content)
    assert payload["orderDetail"][0]["unitPrice"] == "38.50"
    assert payload["orderDetail"][0]["quantity"] == 2
    assert lab_client.post("/api/chat/order-thread/resume", headers=headers, json=body).status_code == 409
    assert len(requests) == 1
    pending = lab_client.get("/api/chat/order-thread", headers=headers).json()["pending"]
    assert pending["status"] == "completed"
    jobs = services.evaluation_store().list_jobs(users["alice"]["id"])
    snapshots = [services.evaluation_store().get_job(users["alice"]["id"], job["id"])["payload"]["actual"] for job in jobs]
    executed = [snapshot for snapshot in snapshots if snapshot["safety"]["side_effect_performed"]]
    assert len(executed) == 1
    assert executed[0]["safety"]["approved"] is True
    assert executed[0]["tool_calls"][0]["status"] == "success"


def test_simultaneous_approval_claims_cannot_execute_twice(lab_client, users, monkeypatch):
    requests = install_erp_transport(monkeypatch)
    headers = users["alice"]["headers"]
    ask(lab_client, headers)
    body = {"resume": {"decisions": [{"type": "approve"}]}}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(lab_client.post, "/api/chat/order-thread/resume", headers=headers, json=body) for _ in range(2)]
        responses = [future.result() for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(requests) == 1


@pytest.mark.parametrize("decisions", [[1], None, [{"type": "edit"}]])
def test_malformed_approval_does_not_consume_pending_action(lab_client, users, monkeypatch, decisions):
    requests = install_erp_transport(monkeypatch)
    headers = users["alice"]["headers"]
    ask(lab_client, headers)
    response = lab_client.post("/api/chat/order-thread/resume", headers=headers, json={"resume": {"decisions": decisions}})
    assert response.status_code == 422
    assert requests == []
    assert lab_client.get("/api/chat/order-thread", headers=headers).json()["pending"]["status"] == "awaiting_approval"


def test_uncertain_erp_response_is_recorded_and_never_automatically_replayed(lab_client, users, monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("simulated response lost after request transmission", request=request)

    def factory(*args, **kwargs):
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("asu_lab.app.httpx.AsyncClient", factory)
    headers = users["alice"]["headers"]
    ask(lab_client, headers)
    body = {"resume": {"decisions": [{"type": "approve"}]}}
    stream_events(lab_client.post("/api/chat/order-thread/resume", headers=headers, json=body))
    assert len(requests) == 1
    assert lab_client.get("/api/chat/order-thread", headers=headers).json()["pending"]["status"] == "outcome_unknown"
    assert lab_client.post("/api/chat/order-thread/resume", headers=headers, json=body).status_code == 409
    assert len(requests) == 1


def test_new_demo_order_cannot_overwrite_an_unresolved_approval(lab_client, users, monkeypatch):
    requests = install_erp_transport(monkeypatch)
    headers = users["alice"]["headers"]
    ask(lab_client, headers, message="演示下单 2 件")
    original = lab_client.get("/api/chat/order-thread", headers=headers).json()["pending"]
    response = lab_client.post("/api/chat/stream", headers=headers, json={"thread_id": "order-thread", "message": "演示下单 9 件"})
    assert response.status_code in {200, 409}
    if response.status_code == 200:
        events = stream_events(response)
        assert any(item["type"] == "error" for item in events)
    current = lab_client.get("/api/chat/order-thread", headers=headers).json()["pending"]
    assert current["request_id"] == original["request_id"]
    assert current["payload"]["orderDetail"][0]["quantity"] == 2
    assert requests == []
