import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from asu_finance import EvidenceStore
from asu_finance.api import create_finance_router


@pytest.fixture
def client(tmp_path):
    def test_auth(authorization: str | None = Header(default=None)):
        # Fixed test credentials only; production must verify JWT/session tokens.
        owners = {"Bearer alice-test-token": "alice", "Bearer bob-test-token": "bob"}
        if authorization not in owners:
            raise HTTPException(status_code=401)
        return {"user_id": owners[authorization]}
    app = FastAPI()
    app.include_router(create_finance_router(EvidenceStore(tmp_path / "api.sqlite3"), test_auth))
    return TestClient(app)


def test_api_auth_citation_privacy_and_client_user_override_rejected(client):
    alice = {"Authorization": "Bearer alice-test-token"}
    bob = {"Authorization": "Bearer bob-test-token"}
    body = {"filename": "report.txt", "content": "revenue 120"}
    assert client.post("/finance/documents", json=body).status_code == 401
    assert client.post("/finance/documents", headers=alice, json={**body, "user_id": "bob"}).status_code == 422
    imported = client.post("/finance/documents", headers=alice, json=body)
    assert imported.status_code == 201
    citation = imported.json()["citation_ids"][0]
    assert client.get(f"/finance/citations/{citation}", headers=alice).status_code == 200
    assert client.get(f"/finance/citations/{citation}", headers=bob).status_code == 404
    assert client.get("/finance/search?q=revenue", headers=bob).json()["results"] == []
    document = imported.json()["document_id"]
    assert client.delete(f"/finance/documents/{document}", headers=bob).status_code == 404
    assert client.delete(f"/finance/documents/{document}", headers=alice).status_code == 200


def test_api_decimal_strings_and_validation(client):
    headers = {"Authorization": "Bearer alice-test-token"}
    result = client.post("/finance/calculate", headers=headers, json={"operation": "add", "values": {"a": "0.1", "b": "0.2"}})
    assert result.json()["result"] == "0.3"
    assert client.post("/finance/calculate", headers=headers, json={"operation": "add", "values": {"a": 0.1, "b": "0.2"}}).status_code == 422
    assert client.post("/finance/calculate", headers=headers, json={"operation": "divide", "values": {"a": "1", "b": "0"}}).status_code == 422
    assert client.post("/finance/program", headers=headers, json={"program": "__import__('os')"}).status_code == 422
    assert client.post("/finance/documents", headers=headers, json={"filename": "a.pdf", "content": "bad!", "encoding": "base64"}).status_code == 422
