"""Collect repeatable read-only service and optional live Agent metrics."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
WEB_URL = os.getenv("ERP_WEB_URL", "http://127.0.0.1:8090")
JAVA_URL = os.getenv("ERP_JAVA_URL", "http://127.0.0.1:8080/api")
MCP_URL = os.getenv("ERP_MCP_URL", "http://127.0.0.1:8000/mcp")


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, round((len(values) - 1) * p))
    return round(values[index], 3)


async def timed_get(client: httpx.AsyncClient, url: str) -> float:
    started = time.perf_counter()
    response = await client.get(url)
    response.raise_for_status()
    return time.perf_counter() - started


async def stream_sample(client: httpx.AsyncClient) -> dict:
    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    credentials = {
        "username": f"qa_bench_{suffix}",
        "password": "QaTest!2026",
        "display_name": "性能测试用户",
    }
    auth = await client.post(f"{WEB_URL}/api/auth/register", json=credentials)
    auth.raise_for_status()
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    started = time.perf_counter()
    first_event = None
    first_token = None
    event_types: list[str] = []
    error = None
    try:
        async with client.stream(
            "POST",
            f"{WEB_URL}/api/chat/stream",
            headers=headers,
            json={"message": "你好，请用一句话介绍你的能力。", "thread_id": None},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                event_type = event.get("type", "unknown")
                event_types.append(event_type)
                elapsed = time.perf_counter() - started
                first_event = first_event if first_event is not None else elapsed
                if event_type == "token" and first_token is None:
                    first_token = elapsed
    except Exception as exc:
        error = str(exc)
    total = time.perf_counter() - started
    return {
        "success": error is None and "done" in event_types,
        "total_seconds": round(total, 3),
        "first_event_seconds": round(first_event, 3) if first_event is not None else None,
        "first_token_seconds": round(first_token, 3) if first_token is not None else None,
        "event_count": len(event_types),
        "event_types": sorted(set(event_types)),
        "error": error,
    }


async def collect_live_samples(concurrency: int, samples: int) -> list[dict]:
    """Collect live SSE samples with a dedicated, open HTTP client."""
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async with httpx.AsyncClient(timeout=180) as live_client:
        async def live_one() -> dict:
            async with semaphore:
                return await stream_sample(live_client)

        live_results = await asyncio.gather(
            *(live_one() for _ in range(samples)), return_exceptions=True
        )

    return [
        item if isinstance(item, dict) else {"success": False, "error": str(item)}
        for item in live_results
    ]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--include-llm", action="store_true")
    args = parser.parse_args()

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {"concurrency": args.concurrency, "samples": args.samples},
        "services": {},
        "http_read_benchmark": {},
        "notes": [],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for name, url in {
            "web_api": f"{WEB_URL}/health",
            "java_erp": f"{JAVA_URL}/parts/search?name=%E7%81%AB%E8%8A%B1%E5%A1%9E",
        }.items():
            try:
                elapsed = await timed_get(client, url)
                report["services"][name] = {"status": "ok", "seconds": round(elapsed, 3)}
            except Exception as exc:
                report["services"][name] = {"status": "error", "error": str(exc)}

        semaphore = asyncio.Semaphore(max(1, args.concurrency))

        async def one() -> float:
            async with semaphore:
                return await timed_get(client, f"{JAVA_URL}/inventory/warning")

        started = time.perf_counter()
        results = await asyncio.gather(
            *(one() for _ in range(args.samples)), return_exceptions=True
        )
        durations = [value for value in results if isinstance(value, float)]
        failures = len(results) - len(durations)
        report["http_read_benchmark"] = {
            "endpoint": "/inventory/warning",
            "samples": len(results),
            "successes": len(durations),
            "failures": failures,
            "wall_seconds": round(time.perf_counter() - started, 3),
            "avg_seconds": round(statistics.mean(durations), 3) if durations else None,
            "p50_seconds": percentile(durations, 0.50),
            "p95_seconds": percentile(durations, 0.95),
            "max_seconds": round(max(durations), 3) if durations else None,
        }

    if args.include_llm:
        normalized = await collect_live_samples(args.concurrency, args.samples)
        successful = [item for item in normalized if item.get("success")]
        totals = [item["total_seconds"] for item in successful]
        report["sse_benchmark"] = {
            "samples": len(normalized),
            "successes": len(successful),
            "failures": len(normalized) - len(successful),
            "avg_total_seconds": round(statistics.mean(totals), 3) if totals else None,
            "p50_total_seconds": percentile(totals, 0.50),
            "p95_total_seconds": percentile(totals, 0.95),
            "results": normalized,
        }
        if not successful:
            report["notes"].append(
                "All live SSE samples failed; inspect sse_benchmark.results for provider or service errors."
            )
    else:
        report["notes"].append("LLM/SSE benchmark not run; use --include-llm explicitly.")

    REPORT_DIR.mkdir(exist_ok=True)
    output = REPORT_DIR / f"benchmark-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
