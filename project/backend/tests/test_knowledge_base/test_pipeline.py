# Purpose of this file is to test ingestion, cleaning, chunking and the reciprocal rank fusion of the knowledge base
from app.knowledge_base.ingestion import (
    DocumentMeta,
    PageRecord,
    load_manifest,
    iter_pages,
)
from app.knowledge_base.preprocessing import (
    build_chunks,
    clean_text,
    strip_repeated_lines,
)
from app.knowledge_base.retrieval import MANIFEST_PATH, reciprocal_rank_fusion, tokenize


def _chunks(sample_docs):
    return build_chunks(iter_pages(load_manifest(MANIFEST_PATH), sample_docs))


def test_manifest_access_rules():
    docs = {d.doc_id: d for d in load_manifest(MANIFEST_PATH)}
    assert docs["finance-ops-manual"].is_allowed("finance")
    assert not docs["finance-ops-manual"].is_allowed("customer_service")
    assert not docs["returns-policy"].is_allowed(None)  # default deny
    assert not docs["returns-policy"].is_allowed("unknown_role")


def test_pages_and_metadata_are_preserved(sample_docs):
    chunks = _chunks(sample_docs)
    window = next(
        c for c in chunks if c.doc_id == "returns-policy" and c.section == "2.1"
    )
    assert window.page == 1 and window.version == "3.2" and window.status == "current"
    shipping = next(
        c for c in chunks if c.doc_id == "returns-policy" and c.section == "2.4"
    )
    assert shipping.page == 2


def test_headers_footers_and_page_numbers_are_removed(sample_docs):
    for chunk in _chunks(sample_docs):
        assert "Internal use" not in chunk.text
        assert "Page 1 of" not in chunk.text
        assert "Acme Retail -" not in chunk.text


def test_chunks_do_not_mix_sections(sample_docs):
    chunks = _chunks(sample_docs)
    clause_21 = next(
        c for c in chunks if c.doc_id == "returns-policy" and c.section == "2.1"
    )
    assert "14 days" in clause_21.text and "2.2 Item condition" not in clause_21.text


def test_superseded_status_comes_from_manifest(sample_docs):
    faq = [c for c in _chunks(sample_docs) if c.doc_id == "returns-faq"]
    assert faq and all(c.status == "superseded" for c in faq)


def test_clean_text_fixes_hyphenation_and_ligatures():
    assert clean_text("refund-\nable  items") == "refundable items"
    assert clean_text("o\ufb03ce") == "office"


def test_page_numbers_are_stripped_even_without_repetition():
    doc = DocumentMeta(doc_id="d", title="T", version="1", filename="x.pdf")
    pages = [PageRecord(doc=doc, page=1, text="Some real content here.\n\n3")]
    assert strip_repeated_lines(pages)[0].text == "Some real content here."


def test_tokenizer_keeps_numbers():
    assert tokenize("Within 14 days, LKR 50,000 and v3.2") == [
        "within",
        "14",
        "days",
        "lkr",
        "50,000",
        "and",
        "v3",
        "2",
    ]


def test_rrf_rewards_agreement_between_rankings():
    scores = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a", "d"]])
    assert max(scores, key=scores.get) == "a"
    assert scores["a"] > scores["b"] and scores["c"] > scores["d"]
