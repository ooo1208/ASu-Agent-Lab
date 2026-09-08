import pytest

from asu_finance import EvidenceError, EvidenceStore
from asu_finance.evidence import parse_document
from asu_finance.review import verify_claim
from asu_finance.tools import finance_functions


@pytest.fixture
def store(tmp_path):
    return EvidenceStore(tmp_path / "evidence.sqlite3")


def test_retrieval_citations_owner_namespace_and_persistence(store):
    alice = store.ingest("alice", "report.md", "营业收入从 100 增长到 120。\nassets 200 liabilities 80")
    bob = store.ingest("bob", "secret.txt", "营业收入 secret merger 999")
    store.ingest("alice", "draft.txt", "营业收入 draft 777", namespace="draft")
    results = store.search("alice", "营业收入")
    assert len(results) == 1 and "120" in results[0]["text"]
    assert results[0]["filename"] == "report.md"
    assert results[0]["line_start"] == 1 and results[0]["line_end"] == 2
    citation = results[0]["citation_id"]
    assert store.get_citation("alice", citation)["document_id"] == alice["document_id"]
    assert store.get_citation("bob", citation) is None
    assert store.get_citation("alice", citation, namespace="draft") is None
    assert not store.search("alice", "secret")
    assert not store.delete_document("alice", bob["document_id"])
    assert EvidenceStore(store.db_path).get_citation("alice", citation)["text"] == results[0]["text"]
    assert store.delete_document("alice", alice["document_id"])
    assert not store.search("alice", "营业收入")
    assert store.get_citation("alice", citation) is None


def test_csv_preserves_headers_and_multiline_source_anchors(store):
    store.ingest("u", "table.csv", 'metric,2025,note\nrevenue,120,"first\nsecond"\nassets,200,ok\n')
    hit = store.search("u", "revenue")[0]
    assert "2025: 120" in hit["text"]
    assert (hit["line_start"], hit["line_end"]) == (2, 3)
    assert hit["metadata"]["table_row"] == 1
    assert store.search("u", "assets")[0]["line_start"] == 4


def test_safe_query_and_long_line_chunking(store):
    store.ingest("u", "long.txt", "revenue " + "a" * 8500)
    assert store.search("u", 'revenue OR "\' DROP TABLE finance_documents --')[0]["filename"] == "long.txt"
    with store._connect() as conn:
        lengths = [row[0] for row in conn.execute("SELECT length(text) FROM finance_fragments")]
    assert max(lengths) <= 4000 and len(lengths) == 3
    with pytest.raises(EvidenceError):
        store.search("u", "***")
    with pytest.raises(EvidenceError):
        store.search("", "revenue")
    with pytest.raises(EvidenceError):
        store.ingest("u", "file.exe", b"bad")


def test_claim_review_does_not_accept_unauthorized_citations_or_unsupported_numbers(store):
    own = store.ingest("alice", "report.txt", "revenue 100 in 2024, revenue 120 in 2025")
    other = store.ingest("bob", "secret.txt", "revenue 50")
    args = dict(operation="change_rate", values={"old": "100", "new": "120"}, reported_value="20")
    review = verify_claim(store, "alice", citation_ids=own["citation_ids"], **args)
    assert review["checks_passed"] and review["requires_semantic_review"]
    assert not verify_claim(store, "alice", citation_ids=other["citation_ids"], **args)["checks_passed"]
    wrong = verify_claim(store, "alice", citation_ids=own["citation_ids"], **{**args, "reported_value": "21"})
    assert not wrong["arithmetic_matches"]
    missing = verify_claim(store, "alice", operation="add", values={"a": "50", "b": "100"}, reported_value="150", citation_ids=own["citation_ids"])
    assert missing["inputs_not_found_in_evidence"] == ["a"]


def test_plain_tools_bind_owner_and_return_structured_errors(store):
    secret = store.ingest("bob", "b.txt", "revenue 120")
    functions = finance_functions(store, "alice")
    assert functions["search_financial_evidence"]("revenue")["results"] == []
    assert "error" in functions["get_financial_citation"](secret["citation_ids"][0])
    assert "error" in functions["calculate_financial_metric"]("divide", {"a": "1", "b": "0"})


def test_pdf_text_page_anchor_when_optional_dependency_exists():
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    import io
    writer = pypdf.PdfWriter()
    for text in ("Revenue 120", "Assets 200"):
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 200 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    fragments = parse_document("report.pdf", buffer.getvalue())
    assert [(item["page"], item["text"]) for item in fragments] == [(1, "Revenue 120"), (2, "Assets 200")]
