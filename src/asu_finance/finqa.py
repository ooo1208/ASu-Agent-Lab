"""Read user-supplied official FinQA JSON without downloading or leaking labels."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .evidence import EvidenceError, EvidenceStore, text_fragments

SPLITS = {"train", "dev", "test", "private_test"}


@dataclass(frozen=True)
class FinQAExample:
    example_id: str
    split: str
    question: str
    pre_text: list[str]
    post_text: list[str]
    table: list[list[str]]
    answer: str | None
    execution_answer: str | None
    program: str | None
    gold_evidence: dict[str, str]

    def to_dict(self, *, include_labels: bool = False) -> dict:
        data = asdict(self)
        if not include_labels:
            for key in ("answer", "execution_answer", "program", "gold_evidence"):
                data.pop(key)
        return data

    def evidence_fragments(self) -> list[dict]:
        fragments = []
        for index, text in enumerate(self.pre_text):
            for piece in text_fragments(text):
                piece["metadata"] = {"evidence_key": f"text_{index}", "section": "pre_text"}
                fragments.append(piece)
        if self.table:
            header = self.table[0]
            for row_index, row in enumerate(self.table[1:], 1):
                if not row:
                    continue
                label = row[0]
                cells = [f"{header[col] if col < len(header) else f'column_{col}'}: {value}" for col, value in enumerate(row[1:], 1)]
                body = label + " | " + " | ".join(cells)
                for piece in text_fragments(body):
                    piece["metadata"] = {"evidence_key": f"table_{row_index}", "section": "table",
                                         "table_row": row_index, "header": header, "cells": row}
                    fragments.append(piece)
        for index, text in enumerate(self.post_text, len(self.pre_text)):
            for piece in text_fragments(text):
                piece["metadata"] = {"evidence_key": f"text_{index}", "section": "post_text"}
                fragments.append(piece)
        return fragments


def _text_list(value, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(part, str) for part in value):
        raise EvidenceError(f"FinQA {field} must be a list of strings.")
    return value


def normalize_example(raw: dict, split: str) -> FinQAExample:
    if split not in SPLITS:
        raise EvidenceError(f"FinQA split must be one of {', '.join(sorted(SPLITS))}.")
    if not isinstance(raw, dict) or not isinstance(raw.get("qa"), dict):
        raise EvidenceError("Each FinQA example must be an object with a qa object.")
    qa = raw["qa"]
    example_id, question = raw.get("id"), qa.get("question")
    if not isinstance(example_id, str) or not example_id.strip() or not isinstance(question, str) or not question.strip():
        raise EvidenceError("FinQA id and qa.question must be non-empty strings.")
    table = raw.get("table", [])
    if not isinstance(table, list) or any(not isinstance(row, list) for row in table):
        raise EvidenceError("FinQA table must be a list of rows.")
    table = [[str(cell) if cell is not None else "" for cell in row] for row in table]
    private = split == "private_test"
    gold = {} if private else qa.get("gold_inds", {})
    if not isinstance(gold, dict):
        raise EvidenceError("FinQA qa.gold_inds must be an object when present.")
    program = None if private else qa.get("program")
    if program is not None and not isinstance(program, str):
        raise EvidenceError("FinQA qa.program must be a string when present.")
    scalar = lambda key: None if private or qa.get(key) is None else str(qa[key]).strip()
    return FinQAExample(example_id, split, question, _text_list(raw.get("pre_text"), "pre_text"),
                        _text_list(raw.get("post_text"), "post_text"), table, scalar("answer"), scalar("exe_ans"),
                        program.strip() if program else None, {str(k): str(v) for k, v in gold.items()})


def load_finqa(path: str | Path, *, split: str | None = None) -> list[FinQAExample]:
    """Load a local official JSON list. Caller obtains dataset under its own terms."""
    path = Path(path)
    split = split or path.stem
    if split not in SPLITS:
        raise EvidenceError("Specify --split for a file not named train/dev/test/private_test.json.")
    if path.stat().st_size > 200 * 1024 * 1024:
        raise EvidenceError("FinQA JSON exceeds the 200 MiB import limit.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("FinQA file must contain valid UTF-8 JSON.") from exc
    if not isinstance(raw, list):
        raise EvidenceError("Official FinQA JSON must contain a list of examples.")
    examples = [normalize_example(item, split) for item in raw]
    if len({item.example_id for item in examples}) != len(examples):
        raise EvidenceError("Duplicate FinQA example ids in this file.")
    return examples


def import_finqa(store: EvidenceStore, user_id: str, examples: list[FinQAExample], *, namespace: str = "finqa") -> list[dict]:
    """Only index report evidence. Questions, answers and gold labels stay out of FTS.

    Each split receives a distinct namespace to avoid accidental train/test mixing.
    A returned item can be joined to offline evaluation labels by example_id.
    """
    results = []
    for example in examples:
        result = store.ingest_fragments(user_id, f"{example.example_id.rsplit('/', 1)[-1]}.txt", example.evidence_fragments(),
            namespace=f"{namespace}:{example.split}",
            metadata={"dataset": "FinQA", "example_id": example.example_id, "split": example.split,
                      "report_source": example.example_id, "location_note": "Evidence keys refer to FinQA JSON; no invented PDF page anchors."})
        result["example_id"] = example.example_id
        results.append(result)
    return results
