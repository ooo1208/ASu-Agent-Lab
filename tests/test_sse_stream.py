import json

import httpx
import pytest

from tests.conftest import BASE_URL, require_live_llm, unique_credentials


@pytest.mark.live
def test_simple_chat_has_complete_sse_lifecycle() -> None:
    require_live_llm()
    with httpx.Client(timeout=180) as client:
        credentials = unique_credentials()
        auth = client.post(f"{BASE_URL}/api/auth/register", json=credentials)
        assert auth.status_code == 201, auth.text
        headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
        with client.stream(
            "POST",
            f"{BASE_URL}/api/chat/stream",
            headers=headers,
            json={"message": "你好，请用一句话介绍你的能力。", "thread_id": None},
        ) as response:
            assert response.status_code == 200
            events = [
                json.loads(line[5:].strip())
                for line in response.iter_lines()
                if line.startswith("data:")
            ]

    event_types = [event["type"] for event in events]
    assert "token" in event_types
    assert event_types[-1] == "done"
    assert events[-1].get("thread_id")
    assert events[-1].get("content")

