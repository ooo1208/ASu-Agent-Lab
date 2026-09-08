"""Offline, synthetic evidence -> arithmetic -> independently checked citation demo."""

import json
import tempfile
from pathlib import Path

from asu_finance import EvidenceStore, calculate
from asu_finance.review import verify_claim


def main():
    with tempfile.TemporaryDirectory(prefix="asu-finance-demo-") as directory:
        store = EvidenceStore(Path(directory) / "evidence.sqlite3")
        report = Path(__file__).with_name("synthetic_report.md")
        store.ingest("demo-user", report.name, report.read_bytes(), metadata={"synthetic": True})
        evidence = store.search("demo-user", "营业收入")
        calculation = calculate("change_rate", {"old": "100", "new": "120"})
        review = verify_claim(store, "demo-user", operation="change_rate", values={"old": "100", "new": "120"},
                              reported_value=calculation["result"], citation_ids=[evidence[0]["citation_id"]])
        print(json.dumps({"synthetic_demo": True, "calculation": calculation, "review": review}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
