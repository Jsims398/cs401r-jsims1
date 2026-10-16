import json
import numpy as np
import pytest

from rag.corpus import Chunk
from rag.index import (
    ChunkIndex, build_index, save_index, load_index, cache_key,
    _embed_request_body, _parse_embed_response,
)


def _stub_embed_fn(texts: list[str]) -> np.ndarray:
    """Deterministic fake embedding: encodes which of 3 known words appear,
    so retrieval tests can assert a specific chunk ranks first without AWS."""
    vocab = ["apple", "banana", "cherry"]
    vectors = []
    for t in texts:
        lower = t.lower()
        vectors.append([1.0 if w in lower else 0.0 for w in vocab])
    arr = np.array(vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _chunks():
    return [
        Chunk("A-1", "A", "Doc A", "H1", "apple content"),
        Chunk("B-1", "B", "Doc B", "H1", "banana content"),
        Chunk("C-1", "C", "Doc C", "H1", "cherry content"),
    ]


def test_build_index_returns_chunk_index_with_all_chunks():
    idx = build_index(_chunks(), _stub_embed_fn)
    assert isinstance(idx, ChunkIndex)
    assert len(idx.chunks) == 3


def test_search_ranks_most_similar_chunk_first():
    idx = build_index(_chunks(), _stub_embed_fn)
    query_vec = _stub_embed_fn(["I want banana info"])[0]
    results = idx.search(query_vec, k=3)
    assert results[0][0].chunk_id == "B-1"
    assert len(results) == 3


def test_search_respects_k():
    idx = build_index(_chunks(), _stub_embed_fn)
    query_vec = _stub_embed_fn(["apple"])[0]
    results = idx.search(query_vec, k=1)
    assert len(results) == 1
    assert results[0][0].chunk_id == "A-1"


def test_save_and_load_roundtrip(tmp_path):
    idx = build_index(_chunks(), _stub_embed_fn)
    save_index(idx, str(tmp_path))
    loaded = load_index(str(tmp_path))
    assert loaded is not None
    assert [c.chunk_id for c in loaded.chunks] == ["A-1", "B-1", "C-1"]
    query_vec = _stub_embed_fn(["cherry"])[0]
    results = loaded.search(query_vec, k=1)
    assert results[0][0].chunk_id == "C-1"


def test_load_index_returns_none_when_cache_missing(tmp_path):
    assert load_index(str(tmp_path / "does_not_exist")) is None


def test_load_index_returns_none_when_cache_key_mismatches(tmp_path):
    idx = build_index(_chunks(), _stub_embed_fn)
    save_index(idx, str(tmp_path))
    # Simulate a chunking change: different chunks than what's cached.
    different_chunks = _chunks()[:2]
    with open(tmp_path / "cache_key.txt", "w") as f:
        f.write("stale-key-that-will-not-match")
    assert load_index(str(tmp_path), expected_chunks=different_chunks) is None


def test_cache_key_changes_when_chunk_text_changes():
    k1 = cache_key(_chunks())
    mutated = _chunks()
    mutated[0] = Chunk("A-1", "A", "Doc A", "H1", "DIFFERENT TEXT")
    k2 = cache_key(mutated)
    assert k1 != k2


def test_embed_request_body_shape():
    body = _embed_request_body("hello world")
    parsed = json.loads(body)
    assert parsed == {"inputText": "hello world"}


def test_parse_embed_response_extracts_embedding():
    raw = json.dumps({"embedding": [0.1, 0.2, 0.3], "inputTextTokenCount": 2}).encode()
    assert _parse_embed_response(raw) == [0.1, 0.2, 0.3]
