"""Regression tests for benchmark HTTP client lifecycle."""

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_benchmark.py"
MODULE_SPEC = importlib.util.spec_from_file_location("procurepilot_run_benchmark", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
run_benchmark = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(run_benchmark)


@pytest.mark.asyncio
async def test_live_samples_use_an_open_dedicated_client(monkeypatch) -> None:
    observed_clients = []

    async def fake_stream_sample(client):
        observed_clients.append(client)
        assert not client.is_closed
        return {"success": True, "total_seconds": 0.01}

    monkeypatch.setattr(run_benchmark, "stream_sample", fake_stream_sample)

    results = await run_benchmark.collect_live_samples(concurrency=2, samples=3)

    assert len(results) == 3
    assert all(item["success"] for item in results)
    assert len({id(client) for client in observed_clients}) == 1
    assert observed_clients[0].is_closed
