"""SQLite queue with leases, fencing tokens, and atomic score/outbox writes."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .scoring import SCORER_VERSION, Score, evaluate, validate_expected
from .delivery import remote_span_id, remote_trace_id


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class LeaseLost(RuntimeError):
    """The worker may no longer acknowledge this leased item."""


class EvaluationStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            raise ValueError("use a file-backed database for durable evaluation")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS evaluation_jobs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, dedupe_key TEXT NOT NULL,
                    trace_id TEXT NOT NULL, session_id TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5, available_at REAL NOT NULL,
                    lease_token TEXT, lease_until REAL, last_error TEXT,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(user_id, dedupe_key)
                );
                CREATE INDEX IF NOT EXISTS jobs_queue ON evaluation_jobs(status,available_at,lease_until);
                CREATE INDEX IF NOT EXISTS jobs_owner ON evaluation_jobs(user_id,created_at);
                CREATE TABLE IF NOT EXISTS evaluation_results (
                    job_id TEXT NOT NULL REFERENCES evaluation_jobs(id), name TEXT NOT NULL,
                    value REAL NOT NULL, reason TEXT NOT NULL, scorer_version TEXT NOT NULL,
                    PRIMARY KEY(job_id,name)
                );
                CREATE TABLE IF NOT EXISTS score_outbox (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES evaluation_jobs(id),
                    payload TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'score', status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 10,
                    available_at REAL NOT NULL, lease_token TEXT, lease_until REAL,
                    last_error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS outbox_queue ON score_outbox(status,available_at,lease_until);
                CREATE TABLE IF NOT EXISTS evaluation_feedback (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES evaluation_jobs(id),
                    user_id TEXT NOT NULL, rating INTEGER NOT NULL, comment TEXT NOT NULL,
                    corrected_expected TEXT, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS golden_cases (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, dataset_version TEXT NOT NULL,
                    feedback_id TEXT NOT NULL REFERENCES evaluation_feedback(id),
                    body TEXT NOT NULL, created_at REAL NOT NULL,
                    UNIQUE(user_id,dataset_version,feedback_id)
                );
                PRAGMA user_version=2;
            """)
            if "kind" not in {row["name"] for row in db.execute("PRAGMA table_info(score_outbox)")}:
                db.execute("ALTER TABLE score_outbox ADD COLUMN kind TEXT NOT NULL DEFAULT 'score'")
                for row in db.execute("SELECT * FROM evaluation_jobs WHERE status='complete'").fetchall():
                    self._insert_trace(db, row, time.time())

    @contextmanager
    def connection(self, *, transaction: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            if transaction:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if transaction:
                db.commit()
        except BaseException:
            if transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def enqueue(self, *, user_id: str, trace_id: str, session_id: str, actual: dict[str, Any],
                expected: dict[str, Any], version: str, run_id: str | None = None,
                input_data: Any = None, max_attempts: int = 5, now: float | None = None) -> str:
        for name, value in (("user_id", user_id), ("trace_id", trace_id), ("session_id", session_id), ("version", version)):
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ValueError(f"{name} must be a nonempty string of at most 256 characters")
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            raise ValueError("actual and expected must be JSON objects")
        if not 1 <= max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        evaluate(actual, expected)  # Validate the contract before accepting a durable job.
        payload = dumps({"actual": actual, "expected": expected, "version": version,
                         "input": input_data, "scorer_version": SCORER_VERSION})
        if len(payload.encode("utf-8")) > 1_000_000:
            raise ValueError("evaluation snapshot must not exceed 1 MB")
        key = run_id or f"{trace_id}:{version}:{SCORER_VERSION}"
        if not isinstance(key, str) or not key or len(key) > 1024:
            raise ValueError("run_id must contain 1 to 1024 characters")
        timestamp = time.time() if now is None else now
        with self.connection(transaction=True) as db:
            existing = db.execute("SELECT id,payload,trace_id,session_id FROM evaluation_jobs WHERE user_id=? AND dedupe_key=?",
                                  (user_id, key)).fetchone()
            if existing:
                if existing["payload"] != payload or existing["trace_id"] != trace_id or existing["session_id"] != session_id:
                    raise ValueError("run_id already exists with a different snapshot")
                return str(existing["id"])
            job_id = str(uuid.uuid4())
            db.execute("""INSERT INTO evaluation_jobs
                (id,user_id,dedupe_key,trace_id,session_id,payload,max_attempts,available_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (job_id, user_id, key, trace_id, session_id, payload, max_attempts, timestamp, timestamp, timestamp))
            return job_id

    def _claim(self, table: str, *, lease_seconds: float = 60, now: float | None = None) -> dict[str, Any] | None:
        if table not in {"evaluation_jobs", "score_outbox"}:
            raise ValueError("unsupported queue")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        timestamp = time.time() if now is None else now
        with self.connection(transaction=True) as db:
            db.execute(f"""UPDATE {table} SET status='failed',last_error='lease expired; retry limit reached',
                lease_token=NULL,lease_until=NULL,updated_at=?
                WHERE status='running' AND lease_until<=? AND attempts>=max_attempts""", (timestamp, timestamp))
            if table == "score_outbox":
                db.execute("""UPDATE score_outbox SET status='failed',last_error='trace export failed; retry the job delivery',
                    updated_at=? WHERE kind='score' AND status='pending' AND EXISTS (
                    SELECT 1 FROM score_outbox t WHERE t.job_id=score_outbox.job_id AND t.kind='trace' AND t.status='failed')""",
                           (timestamp,))
            dependency = "" if table == "evaluation_jobs" else """AND (kind='trace' OR EXISTS (
                SELECT 1 FROM score_outbox t WHERE t.job_id=score_outbox.job_id AND t.kind='trace' AND t.status='sent'))"""
            row = db.execute(f"""SELECT * FROM {table} WHERE attempts<max_attempts AND
                ((status='pending' AND available_at<=?) OR (status='running' AND lease_until<=?))
                {dependency} ORDER BY created_at,id LIMIT 1""", (timestamp, timestamp)).fetchone()
            if row is None:
                return None
            token = str(uuid.uuid4())
            db.execute(f"""UPDATE {table} SET status='running',attempts=attempts+1,
                lease_token=?,lease_until=?,updated_at=? WHERE id=?""",
                       (token, timestamp + lease_seconds, timestamp, row["id"]))
            result = dict(row)
            result.update(status="running", attempts=row["attempts"] + 1, lease_token=token,
                          lease_until=timestamp + lease_seconds)
            result["payload"] = json.loads(result["payload"])
            return result

    def claim_job(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._claim("evaluation_jobs", **kwargs)

    def claim_score(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._claim("score_outbox", **kwargs)

    @staticmethod
    def _verify_lease(db: sqlite3.Connection, table: str, item_id: str, token: str, now: float) -> sqlite3.Row:
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
        if not row or row["status"] != "running" or row["lease_token"] != token or row["lease_until"] <= now:
            raise LeaseLost("lease expired or was claimed by another worker")
        return row

    def complete_job(self, job_id: str, lease_token: str, scores: list[Score], *, now: float | None = None) -> None:
        if not scores or len({s.name for s in scores}) != len(scores):
            raise ValueError("scores must be nonempty with unique names")
        timestamp = time.time() if now is None else now
        with self.connection(transaction=True) as db:
            job = self._verify_lease(db, "evaluation_jobs", job_id, lease_token, timestamp)
            self._insert_trace(db, job, timestamp)
            for score in scores:
                if not 0 <= score.value <= 1:
                    raise ValueError("score values must be within [0, 1]")
                db.execute("INSERT INTO evaluation_results VALUES(?,?,?,?,?)",
                           (job_id, score.name, score.value, score.reason, SCORER_VERSION))
                score_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"asu-eval:{job_id}:{SCORER_VERSION}:{score.name}"))
                payload = dumps({"id": score_id, "traceId": remote_trace_id(job["user_id"], job["trace_id"]),
                                 "observationId": remote_span_id(job_id), "name": score.name,
                                 "value": score.value, "dataType": "NUMERIC", "comment": score.reason})
                db.execute("""INSERT INTO score_outbox(id,job_id,payload,available_at,created_at,updated_at)
                              VALUES(?,?,?,?,?,?)""", (score_id, job_id, payload, timestamp, timestamp, timestamp))
            db.execute("""UPDATE evaluation_jobs SET status='complete',lease_token=NULL,lease_until=NULL,
                        last_error=NULL,updated_at=? WHERE id=?""", (timestamp, job_id))

    @staticmethod
    def _insert_trace(db: sqlite3.Connection, job: sqlite3.Row, now: float) -> None:
        snapshot = json.loads(job["payload"])
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"asu-trace-export:{job['id']}"))
        body = {"traceId": remote_trace_id(job["user_id"], job["trace_id"]), "observationId": remote_span_id(job["id"]),
                "business_trace_id": job["trace_id"], "user_id": job["user_id"], "session_id": job["session_id"],
                "version": snapshot["version"], "input": snapshot.get("input"), "output": snapshot["actual"],
                "captured_at": job["created_at"]}
        db.execute("""INSERT OR IGNORE INTO score_outbox(id,job_id,payload,kind,available_at,created_at,updated_at)
                      VALUES(?,?,?,'trace',?,?,?)""", (event_id, job["id"], dumps(body), now, now, now))

    def acknowledge_score(self, score_id: str, lease_token: str, *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        with self.connection(transaction=True) as db:
            self._verify_lease(db, "score_outbox", score_id, lease_token, timestamp)
            db.execute("""UPDATE score_outbox SET status='sent',lease_token=NULL,lease_until=NULL,
                        last_error=NULL,updated_at=? WHERE id=?""", (timestamp, score_id))

    def _fail(self, table: str, item_id: str, token: str, error: str, *, now: float | None = None,
              base_delay: float = 2, max_delay: float = 300) -> None:
        if table not in {"evaluation_jobs", "score_outbox"}:
            raise ValueError("unsupported queue")
        timestamp = time.time() if now is None else now
        with self.connection(transaction=True) as db:
            row = self._verify_lease(db, table, item_id, token, timestamp)
            status = "failed" if row["attempts"] >= row["max_attempts"] else "pending"
            delay = min(max_delay, base_delay * (2 ** min(row["attempts"] - 1, 20)))
            db.execute(f"""UPDATE {table} SET status=?,available_at=?,lease_token=NULL,lease_until=NULL,
                last_error=?,updated_at=? WHERE id=?""", (status, timestamp + delay, error[:300], timestamp, item_id))

    def fail_job(self, item_id: str, token: str, error: str, **kwargs: Any) -> None:
        self._fail("evaluation_jobs", item_id, token, error, **kwargs)

    def fail_score(self, item_id: str, token: str, error: str, **kwargs: Any) -> None:
        self._fail("score_outbox", item_id, token, error, **kwargs)

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM evaluation_jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["payload"] = json.loads(result["payload"])
            result["remote_trace_id"] = remote_trace_id(user_id, result["trace_id"])
            result["remote_observation_id"] = remote_span_id(job_id)
            result.pop("lease_token", None)
            result["scores"] = [dict(s) for s in db.execute(
                "SELECT name,value,reason,scorer_version FROM evaluation_results WHERE job_id=? ORDER BY name", (job_id,))]
            result["delivery"] = {r["status"]: r["n"] for r in db.execute(
                "SELECT status,count(*) n FROM score_outbox WHERE job_id=? GROUP BY status", (job_id,))}
            return result

    def list_jobs(self, user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("""SELECT id,trace_id,session_id,status,attempts,created_at,updated_at
                FROM evaluation_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?""", (user_id, max(1, min(limit, 200))))]

    def add_feedback(self, *, user_id: str, job_id: str, rating: int, comment: str = "",
                     corrected_expected: dict[str, Any] | None = None) -> str:
        if type(rating) is not int or rating not in {0, 1}:
            raise ValueError("rating must be 0 or 1")
        if len(comment) > 4000:
            raise ValueError("feedback comment must be at most 4000 characters")
        if corrected_expected is not None:
            validate_expected(corrected_expected)
            evaluate({}, corrected_expected)
            if len(dumps(corrected_expected).encode("utf-8")) > 1_000_000:
                raise ValueError("corrected expectations must not exceed 1 MB")
        with self.connection(transaction=True) as db:
            if not db.execute("SELECT 1 FROM evaluation_jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
                raise KeyError("job not found")
            feedback_id = str(uuid.uuid4())
            db.execute("INSERT INTO evaluation_feedback VALUES(?,?,?,?,?,?,?)",
                       (feedback_id, job_id, user_id, rating, comment,
                        dumps(corrected_expected) if corrected_expected is not None else None, time.time()))
            return feedback_id

    def list_feedback(self, user_id: str, job_id: str) -> list[dict[str, Any]]:
        if self.get_job(user_id, job_id) is None:
            raise KeyError("job not found")
        with self.connection() as db:
            result = [dict(row) for row in db.execute(
                "SELECT * FROM evaluation_feedback WHERE user_id=? AND job_id=? ORDER BY created_at", (user_id, job_id))]
        for row in result:
            if row["corrected_expected"] is not None:
                row["corrected_expected"] = json.loads(row["corrected_expected"])
        return result

    def promote_feedback(self, *, user_id: str, feedback_id: str, dataset_version: str) -> str:
        if not dataset_version or len(dataset_version) > 100:
            raise ValueError("dataset_version must contain 1 to 100 characters")
        with self.connection(transaction=True) as db:
            row = db.execute("""SELECT f.*,j.payload FROM evaluation_feedback f JOIN evaluation_jobs j ON j.id=f.job_id
                               WHERE f.id=? AND f.user_id=? AND j.user_id=?""", (feedback_id, user_id, user_id)).fetchone()
            if row is None:
                raise KeyError("feedback not found")
            if row["corrected_expected"] is None:
                raise ValueError("reviewed corrected_expected is required before promotion")
            case_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"asu-golden:{user_id}:{dataset_version}:{feedback_id}"))
            payload = json.loads(row["payload"])
            case = {"id": case_id, "input": payload.get("input"),
                    "expected": json.loads(row["corrected_expected"]),
                    "source": {"kind": "human_review", "feedback_id": feedback_id, "job_id": row["job_id"]}}
            db.execute("INSERT OR IGNORE INTO golden_cases VALUES(?,?,?,?,?,?)",
                       (case_id, user_id, dataset_version, feedback_id, dumps(case), time.time()))
            return case_id

    def export_golden(self, user_id: str, dataset_version: str) -> dict[str, Any]:
        with self.connection() as db:
            cases = [json.loads(row["body"]) for row in db.execute("""SELECT body FROM golden_cases
                WHERE user_id=? AND dataset_version=? ORDER BY id""", (user_id, dataset_version))]
        return {"name": "reviewed-agent-cases", "version": dataset_version, "cases": cases}

    def retry_failed(self, user_id: str, job_id: str) -> None:
        """Explicit recovery after configuration is fixed; preserve event IDs and results."""
        now = time.time()
        with self.connection(transaction=True) as db:
            if not db.execute("SELECT 1 FROM evaluation_jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
                raise KeyError("job not found")
            db.execute("""UPDATE evaluation_jobs SET status='pending',attempts=0,available_at=?,last_error=NULL,updated_at=?
                WHERE id=? AND status='failed'""", (now, now, job_id))
            db.execute("""UPDATE score_outbox SET status='pending',attempts=0,available_at=?,last_error=NULL,updated_at=?
                WHERE job_id=? AND status='failed'""", (now, now, job_id))

    def counts(self) -> dict[str, dict[str, int]]:
        """Operator-local queue health; intentionally not exposed via tenant API."""
        with self.connection() as db:
            return {table: {row["status"]: row["n"] for row in db.execute(
                f"SELECT status,count(*) n FROM {table} GROUP BY status")}
                    for table in ("evaluation_jobs", "score_outbox")}
