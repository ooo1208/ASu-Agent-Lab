import pytest
from fastapi.testclient import TestClient

from asu_lab import services
from asu_lab.app import create_app


@pytest.fixture
def lab_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ASU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ASU_RELEASE", "integration-test")
    monkeypatch.delenv("ERP_API_KEY", raising=False)
    for factory in (services.evaluation_store, services.evidence_store, services.task_context_store):
        factory.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        yield client
    for factory in (services.evaluation_store, services.evidence_store, services.task_context_store):
        factory.cache_clear()


@pytest.fixture
def users(lab_client):
    result = {}
    for name in ("alice", "bob"):
        response = lab_client.post("/api/auth/register", json={"username": name, "password": "test-password-2026"})
        assert response.status_code == 200, response.text
        result[name] = {"headers": {"Authorization": "Bearer " + response.json()["access_token"]},
                        "id": response.json()["user"]["user_id"]}
    return result
