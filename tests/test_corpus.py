from rag.corpus import (
    Chunk, load_raw_documents, chunk_document, load_and_chunk_corpus, MAX_CHUNK_CHARS,
)


def test_load_raw_documents_finds_all_four_docs():
    docs = load_raw_documents("northstar-policy-docs")
    doc_ids = {d["doc_id"] for d in docs}
    assert doc_ids == {"POL-RET-004", "POL-LOY-011", "POL-SHP-007", "KB-FAQ-022"}


def test_load_raw_documents_extracts_title():
    docs = load_raw_documents("northstar-policy-docs")
    loy = next(d for d in docs if d["doc_id"] == "POL-LOY-011")
    assert "Summit Rewards" in loy["title"]


def test_chunk_document_splits_on_level2_headers():
    md = (
        "# Title\n\n**Document ID:** DOC-1\n\n---\n\n"
        "## Section One\n\nShort body one.\n\n"
        "## Section Two\n\nShort body two.\n"
    )
    chunks = chunk_document("DOC-1", "Title", md)
    headings = [c.heading for c in chunks]
    assert headings == ["Section One", "Section Two"]
    assert chunks[0].text == "Short body one."
    assert chunks[1].text == "Short body two."


def test_chunk_document_assigns_sequential_ids():
    md = "## A\n\nBody A.\n\n## B\n\nBody B.\n"
    chunks = chunk_document("DOC-X", "T", md)
    assert [c.chunk_id for c in chunks] == ["DOC-X-1", "DOC-X-2"]


def test_chunk_document_splits_oversized_section_on_paragraphs():
    para = "X" * 700
    md = f"## Big Section\n\n{para}\n\n{para}\n\n{para}\n"
    chunks = chunk_document("DOC-Y", "T", md, max_chars=1200)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 1200 + 1  # allow the single oversized-paragraph edge case
        assert c.heading == "Big Section"


def test_chunk_document_never_splits_inside_a_table():
    table = "\n".join(f"| row{i} | val{i} |" for i in range(40))
    md = f"## Table Section\n\n{table}\n"
    chunks = chunk_document("DOC-Z", "T", md, max_chars=200)
    # The whole table must survive as one chunk even though it exceeds max_chars,
    # because splitting it would produce a header-less, unusable table fragment.
    table_chunks = [c for c in chunks if "| row0 |" in c.text]
    assert len(table_chunks) == 1
    assert "| row39 |" in table_chunks[0].text


def test_labeled_text_includes_doc_id_and_heading():
    c = Chunk(chunk_id="X-1", doc_id="X", doc_title="T", heading="Returns", text="30 days.")
    labeled = c.labeled_text()
    assert "X" in labeled
    assert "Returns" in labeled
    assert "30 days." in labeled


def test_load_and_chunk_corpus_produces_chunks_for_every_doc():
    chunks = load_and_chunk_corpus("northstar-policy-docs")
    doc_ids_seen = {c.doc_id for c in chunks}
    assert doc_ids_seen == {"POL-RET-004", "POL-LOY-011", "POL-SHP-007", "KB-FAQ-022"}
    assert len(chunks) >= 20  # 4 docs, 5-9 top-level sections each
