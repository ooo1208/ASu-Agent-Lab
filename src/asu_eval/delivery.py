"""Optional Langfuse score delivery using its documented public REST API."""

import base64
import hashlib
import json
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise HTTPError(req.full_url, code, "redirect rejected", headers, fp)


# Keep project credentials on the explicitly configured origin.
urlopen = build_opener(_RejectRedirect()).open


class ScoreSender(Protocol):
    def send(self, payload: dict[str, Any]) -> None: ...
    def send_trace(self, payload: dict[str, Any]) -> None: ...


def remote_trace_id(user_id: str, trace_id: str) -> str:
    """Tenant-scope arbitrary business IDs into valid, stable 128-bit OTEL IDs."""
    identity = json.dumps([user_id, trace_id], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"asu-trace:{identity}".encode()).hexdigest()[:32]


def remote_span_id(job_id: str) -> str:
    return hashlib.sha256(f"asu-completed-run:{job_id}".encode()).hexdigest()[:16]


class DeliveryError(RuntimeError):
    pass


class LangfuseScoreSender:
    """POST /api/public/scores, stable id for retry idempotency, no tracing side effects."""

    def __init__(self, host: str, public_key: str, secret_key: str, *, timeout: float = 10):
        parsed = urlsplit(host)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Langfuse host must be an HTTP(S) origin without credentials")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("non-local Langfuse hosts must use HTTPS")
        if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Langfuse host must be an origin, without path/query/fragment")
        if not public_key or not secret_key:
            raise ValueError("Langfuse public and secret keys are required in remote mode")
        if not 0 < timeout < 60:
            raise ValueError("timeout must be positive and below the default 60-second lease")
        self.url = host.rstrip("/") + "/api/public/scores"
        self.trace_url = host.rstrip("/") + "/api/public/otel/v1/traces"
        self._authorization = "Basic " + base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "LangfuseScoreSender":
        return cls(os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                   os.environ.get("LANGFUSE_PUBLIC_KEY", ""), os.environ.get("LANGFUSE_SECRET_KEY", ""))

    def send(self, payload: dict[str, Any]) -> None:
        self._post(self.url, payload)

    def send_trace(self, payload: dict[str, Any]) -> None:
        """A completed snapshot root span, not fabricated per-tool/model spans."""
        def attr(key: str, value: Any) -> dict[str, Any]:
            return {"key": key, "value": {"stringValue": value if isinstance(value, str)
                                         else json.dumps(value, ensure_ascii=False, allow_nan=False)}}

        end_ns = int(payload["captured_at"] * 1_000_000_000)
        latency = payload["output"].get("latency_ms")
        valid_latency = isinstance(latency, (int, float)) and not isinstance(latency, bool) and 0 <= latency <= 86_400_000
        start_ns = end_ns - int(latency * 1_000_000) if valid_latency else end_ns
        span = {
            "traceId": payload["traceId"], "spanId": payload["observationId"],
            "name": "ASu completed Agent run", "kind": 1,
            "startTimeUnixNano": str(start_ns), "endTimeUnixNano": str(end_ns),
            "attributes": [
                attr("langfuse.observation.type", "agent"), attr("langfuse.trace.name", "ASu completed Agent run"),
                attr("langfuse.user.id", payload["user_id"]), attr("langfuse.session.id", payload["session_id"]),
                attr("langfuse.version", payload["version"]), attr("langfuse.environment", "asu-agent-lab"),
                attr("langfuse.observation.input", payload["input"]),
                attr("langfuse.observation.output", payload["output"]),
                attr("langfuse.observation.metadata.capture_kind", "completed_snapshot"),
                attr("langfuse.observation.metadata.business_trace_id", payload["business_trace_id"]),
                attr("langfuse.observation.metadata.timing", "capture_time_minus_recorded_latency" if valid_latency else "capture_time_only"),
            ],
        }
        body = {"resourceSpans": [{"resource": {"attributes": [attr("service.name", "asu-evaluation-worker")]},
                                    "scopeSpans": [{"scope": {"name": "asu-eval", "version": "1"}, "spans": [span]}]}]}
        self._post(self.trace_url, body, trace=True)

    def _post(self, url: str, payload: dict[str, Any], *, trace: bool = False) -> None:
        headers = {"Content-Type": "application/json", "Authorization": self._authorization}
        if trace:
            headers["x-langfuse-ingestion-version"] = "4"
        request = Request(url, data=json.dumps(payload, allow_nan=False).encode("utf-8"), method="POST", headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise DeliveryError(f"Langfuse returned HTTP {response.status}")
                raw = response.read(1_000_000)
                if trace and raw:
                    result = json.loads(raw)
                    partial = result.get("partialSuccess", {})
                    if int(partial.get("rejectedSpans", 0)):
                        raise DeliveryError("Langfuse rejected an OTLP span")
                # HTTP 2xx acknowledges ingestion, not immediate dashboard visibility.
        except HTTPError as exc:
            # Deliberately do not persist response bodies, URLs containing secrets, or headers.
            raise DeliveryError(f"Langfuse returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise DeliveryError(f"Langfuse transport failed ({type(exc).__name__})") from None
