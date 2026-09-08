"""Persistent, owner-scoped evidence retrieval with SQLite FTS5 (not embeddings)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class EvidenceError(ValueError):
    pass


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_FRAGMENT_CHARS = 4000


def _scope(user_id: str, namespace: str) -> None:
    for name, value in (("user_id", user_id), ("namespace", namespace)):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise EvidenceError(f"{name} must be a non-empty string of at most 200 characters.")


def _index_text(text: str) -> str:
    # unicode61 treats an unspaced Chinese phrase as one token; add overlapping
    # Han bigrams for lexical Chinese recall. This is still NOT semantic retrieval.
    terms = []
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        terms.extend(run[i:i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            terms.append(run)
    return text + "\n" + " ".join(terms)


def _query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise EvidenceError("Search query must contain 1–1000 characters.")
    words = re.findall(r"[^\W_]+", query, re.UNICODE)
    terms = []
    for word in words:
        if re.fullmatch(r"[\u3400-\u9fff]+", word) and len(word) > 2:
            terms.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            terms.append(word)
    terms = list(dict.fromkeys(terms))[:40]
    if not terms:
        raise EvidenceError("Search query must contain letters, Chinese characters or numbers.")
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)


def text_fragments(text: str, *, page: int | None = None, lines_per_chunk: int = 12) -> list[dict]:
    fragments, pending = [], []
    first, last, size = 1, 1, 0
    for line_number, line in enumerate(text.splitlines(), 1):
        # A single long line must not bypass chunk limits. Each part keeps its
        # original line anchor, so citations remain resolvable.
        parts = [line[i:i + MAX_FRAGMENT_CHARS] for i in range(0, len(line), MAX_FRAGMENT_CHARS)] or [""]
        for part in parts:
            if pending and (len(pending) >= lines_per_chunk or size + len(part) > MAX_FRAGMENT_CHARS):
                body = "\n".join(pending).strip()
                if body:
                    fragments.append({"text": body, "page": page, "line_start": first, "line_end": last})
                pending, size = [], 0
            if not pending:
                first = line_number
            pending.append(part)
            last, size = line_number, size + len(part) + 1
    if pending and (body := "\n".join(pending).strip()):
        fragments.append({"text": body, "page": page, "line_start": first, "line_end": last})
    return fragments


def parse_document(filename: str, content: str | bytes) -> list[dict]:
    data = content.encode("utf-8") if isinstance(content, str) else content
    if not isinstance(data, bytes) or len(data) > MAX_DOCUMENT_BYTES:
        raise EvidenceError("Document must be at most 10 MiB.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise EvidenceError("PDF import requires the optional pypdf package.") from exc
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise EvidenceError("Encrypted PDFs are not supported.")
            if len(reader.pages) > 500:
                raise EvidenceError("PDF exceeds 500 pages.")
            fragments = []
            for page_number, page in enumerate(reader.pages, 1):
                fragments.extend(text_fragments(page.extract_text() or "", page=page_number))
            if not fragments:
                raise EvidenceError("PDF has no extractable text; OCR is not included.")
            return fragments
        except EvidenceError:
            raise
        except Exception as exc:
            raise EvidenceError("Could not parse this PDF.") from exc
    if suffix not in {".txt", ".md", ".csv"}:
        raise EvidenceError("Supported formats: .txt, .md, .csv, and optional .pdf.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceError("Text and CSV documents must use UTF-8 encoding.") from exc
    if suffix != ".csv":
        return text_fragments(text)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader, None)
        if not header:
            return []
        fragments, previous_line = [], reader.line_num
        for row_index, row in enumerate(reader, 1):
            start_line = previous_line + 1
            previous_line = reader.line_num
            if not any(cell.strip() for cell in row):
                continue
            pairs = [f"{header[i] if i < len(header) else f'column_{i + 1}'}: {cell}" for i, cell in enumerate(row)]
            body = " | ".join(pairs)
            if len(body) > MAX_FRAGMENT_CHARS:
                raise EvidenceError("CSV row exceeds 4000 characters; split oversized rows before importing.")
            fragments.append({"text": body, "line_start": start_line, "line_end": previous_line,
                              "metadata": {"table_row": row_index, "header": header, "cells": row}})
        return fragments
    except csv.Error as exc:
        raise EvidenceError("Invalid CSV format.") from exc


class EvidenceStore:
    """Use a filesystem SQLite path. Every query requires a trusted owner id."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            raise EvidenceError("Use a filesystem database path; connections are scoped per operation.")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            try:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS finance_documents (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, namespace TEXT NOT NULL,
                    filename TEXT NOT NULL, sha256 TEXT NOT NULL, metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS finance_document_owner ON finance_documents(user_id, namespace);
                CREATE TABLE IF NOT EXISTS finance_fragments (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES finance_documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, text TEXT NOT NULL, page INTEGER, line_start INTEGER, line_end INTEGER,
                    metadata TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS finance_fragment_document ON finance_fragments(document_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS finance_fts USING fts5(fragment_id UNINDEXED, body, tokenize='unicode61');
                """)
            except sqlite3.OperationalError as exc:
                raise EvidenceError("SQLite FTS5 support is required; use a Python build with FTS5 enabled.") from exc

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def ingest(self, user_id: str, filename: str, content: str | bytes, *, namespace: str = "default", metadata: dict | None = None) -> dict:
        # Content API never opens arbitrary paths. CLI/local code may read an
        # explicitly supplied path then call this method.
        return self.ingest_fragments(user_id, filename, parse_document(filename, content), namespace=namespace, metadata=metadata)

    def ingest_fragments(self, user_id: str, filename: str, fragments: list[dict], *, namespace: str = "default", metadata: dict | None = None) -> dict:
        _scope(user_id, namespace)
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename or len(filename) > 240:
            raise EvidenceError("A filename of 1–240 characters is required.")
        if not fragments or len(fragments) > 10000:
            raise EvidenceError("A document must contain 1–10000 non-empty evidence fragments.")
        if any(not isinstance(f.get("text"), str) or not f["text"].strip() or len(f["text"]) > MAX_FRAGMENT_CHARS for f in fragments):
            raise EvidenceError("Evidence fragments must contain 1–4000 characters.")
        if sum(len(f["text"].encode("utf-8")) for f in fragments) > MAX_DOCUMENT_BYTES:
            raise EvidenceError("Extracted document text exceeds 10 MiB.")
        document_id = uuid.uuid4().hex
        digest = hashlib.sha256("\n".join(f["text"] for f in fragments).encode("utf-8")).hexdigest()
        ids = []
        with self._connect() as conn:
            conn.execute("INSERT INTO finance_documents(id,user_id,namespace,filename,sha256,metadata) VALUES(?,?,?,?,?,?)",
                         (document_id, user_id, namespace, filename, digest, json.dumps(metadata or {}, ensure_ascii=False)))
            for index, fragment in enumerate(fragments, 1):
                fragment_id = f"{document_id}:{index}"
                conn.execute("INSERT INTO finance_fragments VALUES(?,?,?,?,?,?,?,?)", (
                    fragment_id, document_id, index, fragment["text"], fragment.get("page"), fragment.get("line_start"),
                    fragment.get("line_end"), json.dumps(fragment.get("metadata", {}), ensure_ascii=False)))
                conn.execute("INSERT INTO finance_fts(fragment_id,body) VALUES(?,?)", (fragment_id, _index_text(fragment["text"])))
                ids.append(fragment_id)
        return {"document_id": document_id, "filename": filename, "namespace": namespace, "fragment_count": len(ids), "citation_ids": ids, "sha256": digest}

    @staticmethod
    def _result(row) -> dict:
        item = dict(row)
        item["metadata"] = json.loads(item["metadata"])
        item["document_metadata"] = json.loads(item["document_metadata"])
        return item

    def search(self, user_id: str, query: str, *, namespace: str = "default", limit: int = 5) -> list[dict]:
        _scope(user_id, namespace)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise EvidenceError("Search limit must be between 1 and 20.")
        match = _query(query)
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT f.id AS citation_id, f.document_id, d.filename, d.namespace, f.text,
                       f.page, f.line_start, f.line_end, f.metadata, d.metadata AS document_metadata,
                       bm25(finance_fts) AS rank
                FROM finance_fts JOIN finance_fragments f ON f.id=finance_fts.fragment_id
                JOIN finance_documents d ON d.id=f.document_id
                WHERE finance_fts MATCH ? AND d.user_id=? AND d.namespace=?
                ORDER BY rank, f.id LIMIT ?
            """, (match, user_id, namespace, limit)).fetchall()
        return [self._result(row) for row in rows]

    def get_citation(self, user_id: str, citation_id: str, *, namespace: str = "default") -> dict | None:
        _scope(user_id, namespace)
        with self._connect() as conn:
            row = conn.execute("""
                SELECT f.id AS citation_id, f.document_id, d.filename, d.namespace, f.text,
                       f.page, f.line_start, f.line_end, f.metadata, d.metadata AS document_metadata
                FROM finance_fragments f JOIN finance_documents d ON d.id=f.document_id
                WHERE f.id=? AND d.user_id=? AND d.namespace=?
            """, (citation_id, user_id, namespace)).fetchone()
        return self._result(row) if row else None

    def delete_document(self, user_id: str, document_id: str, *, namespace: str = "default") -> bool:
        _scope(user_id, namespace)
        with self._connect() as conn:
            owned = conn.execute("SELECT id FROM finance_documents WHERE id=? AND user_id=? AND namespace=?", (document_id, user_id, namespace)).fetchone()
            if not owned:
                return False
            conn.execute("DELETE FROM finance_fts WHERE fragment_id IN (SELECT id FROM finance_fragments WHERE document_id=?)", (document_id,))
            conn.execute("DELETE FROM finance_documents WHERE id=?", (document_id,))
        return True
