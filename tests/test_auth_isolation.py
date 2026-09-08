import httpx
import pytest

from tests.conftest import BASE_URL, unique_credentials


pytestmark = pytest.mark.integration


def register(client: httpx.Client) -> tuple[dict, dict[str, str]]:
    credentials = unique_credentials()
    response = client.post(f"{BASE_URL}/api/auth/register", json=credentials)
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload, {"Authorization": f"Bearer {payload['access_token']}"}


def test_register_login_me_and_empty_history() -> None:
    with httpx.Client(timeout=20) as client:
        payload, headers = register(client)
        me = client.get(f"{BASE_URL}/api/auth/me", headers=headers)
        history = client.get(f"{BASE_URL}/api/history?page=1&limit=20", headers=headers)

    assert me.status_code == 200
    assert me.json()["user_id"] == payload["user"]["user_id"]
    assert history.status_code == 200
    assert history.json()["total"] == 0


def test_unauthorized_requests_are_rejected() -> None:
    with httpx.Client(timeout=20) as client:
        me = client.get(f"{BASE_URL}/api/auth/me")
        history = client.get(f"{BASE_URL}/api/history")

    assert me.status_code == 401
    assert history.status_code == 401
