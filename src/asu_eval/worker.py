"""Run independently from the web server: python -m asu_eval.worker --once."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable

from .delivery import LangfuseScoreSender, ScoreSender
from .scoring import evaluate
from .store import EvaluationStore, LeaseLost

logger = logging.getLogger(__name__)


class EvaluationWorker:
    def __init__(self, store: EvaluationStore, sender: ScoreSender | None = None, *,
                 lease_seconds: float = 60, clock: Callable[[], float] = time.time):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.store, self.sender, self.lease_seconds, self.clock = store, sender, lease_seconds, clock

    def run_cycle(self) -> bool:
        """At most one evaluation and one remote delivery. False means no eligible work."""
        worked = False
        job = self.store.claim_job(lease_seconds=self.lease_seconds, now=self.clock())
        if job:
            worked = True
            try:
                scores = evaluate(job["payload"]["actual"], job["payload"]["expected"])
                self.store.complete_job(job["id"], job["lease_token"], scores, now=self.clock())
            except LeaseLost:
                logger.warning("evaluation lease lost; a later claim will recover it")
            except Exception as exc:
                try:
                    self.store.fail_job(job["id"], job["lease_token"], type(exc).__name__, now=self.clock())
                except LeaseLost:
                    logger.warning("evaluation failure arrived after lease expiry")
        # Offline mode leaves outbox rows pending; it never marks them as delivered.
        if self.sender is not None:
            item = self.store.claim_score(lease_seconds=self.lease_seconds, now=self.clock())
            if item:
                worked = True
                try:
                    if item["kind"] == "trace":
                        self.sender.send_trace(item["payload"])
                    else:
                        self.sender.send(item["payload"])
                    self.store.acknowledge_score(item["id"], item["lease_token"], now=self.clock())
                except LeaseLost:
                    logger.warning("delivery lease lost; retries retain the same remote score ID")
                except Exception as exc:
                    try:
                        self.store.fail_score(item["id"], item["lease_token"], type(exc).__name__, now=self.clock())
                    except LeaseLost:
                        logger.warning("delivery failure arrived after lease expiry")
        return worked

    def drain(self, max_cycles: int = 1000) -> int:
        count = 0
        while count < max_cycles and self.run_cycle():
            count += 1
        return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Durable evaluation worker; local scoring is the default")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("ASU_EVAL_DB", "data/evaluation.sqlite3")))
    parser.add_argument("--delivery", choices=("offline", "langfuse"), default="offline")
    parser.add_argument("--once", action="store_true", help="Drain eligible work then exit; do not wait for future retries")
    parser.add_argument("--poll-seconds", type=float, default=1)
    parser.add_argument("--max-cycles", type=int, default=1000)
    args = parser.parse_args(argv)
    if args.poll_seconds <= 0 or args.max_cycles <= 0:
        parser.error("poll-seconds and max-cycles must be positive")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        sender = LangfuseScoreSender.from_env() if args.delivery == "langfuse" else None
        store = EvaluationStore(args.db)
    except ValueError as exc:
        parser.error(str(exc))
    worker = EvaluationWorker(store, sender)
    try:
        if args.once:
            worker.drain(args.max_cycles)
        else:
            while True:
                worker.drain(args.max_cycles)
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        pass
    print(json.dumps({"delivery_mode": args.delivery, **store.counts()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
