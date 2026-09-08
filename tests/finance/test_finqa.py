import json

import pytest

from asu_finance import EvidenceError, EvidenceStore
from asu_finance.finqa import import_finqa, load_finqa, normalize_example


@pytest.fixture
def raw():
    return {"id": "SYNTHETIC/2025/report-1", "pre_text": ["Synthetic report in millions."],
            "post_text": ["Same accounting scope."], "table": [["metric", "2024", "2025"], ["revenue", "100", "120"]],
            "qa": {"question": "How much did revenue grow?", "answer": "PRIVATE_GOLD_LABEL_20_PERCENT",
                   "exe_ans": 20, "program": "subtract(120,100), divide(#0,100)", "gold_inds": {"table_1": "revenue 100 120"}}}


def test_finqa_table_headers_labels_and_split_isolation(tmp_path, raw):
    path = tmp_path / "train.json"
    path.write_text(json.dumps([raw]), encoding="utf-8")
    examples = load_finqa(path)
    assert examples[0].execution_answer == "20"
    assert "program" not in examples[0].to_dict()
    assert examples[0].to_dict(include_labels=True)["program"].startswith("subtract")
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    imported = import_finqa(store, "u", examples)
    hit = store.search("u", "revenue", namespace="finqa:train")[0]
    assert "2024: 100" in hit["text"] and "2025: 120" in hit["text"]
    assert hit["metadata"]["evidence_key"] == "table_1"
    assert hit["document_metadata"]["example_id"] == raw["id"]
    assert imported[0]["namespace"] == "finqa:train"
    assert not store.search("u", "PRIVATE_GOLD_LABEL_20_PERCENT", namespace="finqa:train")
    assert not store.search("u", "subtract", namespace="finqa:train")
    assert not store.search("u", "revenue", namespace="finqa:test")
    assert not store.search("other", "revenue", namespace="finqa:train")


def test_private_split_never_exposes_reference_labels(raw):
    example = normalize_example(raw, "private_test")
    assert example.program is None and example.answer is None and example.execution_answer is None
    assert example.gold_evidence == {}
    minimal = {**raw, "qa": {"question": "How much?"}}
    assert normalize_example(minimal, "private_test").question == "How much?"


def test_invalid_finqa_schema_and_duplicates(tmp_path, raw):
    with pytest.raises(EvidenceError, match="qa"):
        normalize_example({"id": "bad"}, "train")
    with pytest.raises(EvidenceError, match="split"):
        normalize_example(raw, "production")
    path = tmp_path / "dev.json"
    path.write_text(json.dumps([raw, raw]), encoding="utf-8")
    with pytest.raises(EvidenceError, match="Duplicate"):
        load_finqa(path)
