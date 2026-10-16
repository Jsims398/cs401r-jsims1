import numpy as np

from rag.corpus import Chunk
from rag.index import build_index
from rag.retrieve import (
    tier_benefit_query, constraint_query, hybrid_query, QUERY_STRATEGIES, retrieve,
)

CTX = {
    "loyalty_tier": "Gold",
    "online_to_store_ratio": 0.72,
    "top_categories": ["Outdoor", "Footwear"],
}


def test_tier_benefit_query_mentions_tier():
    q = tier_benefit_query(CTX)
    assert "Gold" in q
    assert "points" in q.lower() or "earn" in q.lower()


def test_constraint_query_is_tier_independent():
    q1 = constraint_query(CTX)
    q2 = constraint_query({**CTX, "loyalty_tier": "Bronze"})
    assert q1 == q2  # constraints (final sale, expired offers) don't vary by tier
    assert "final sale" in q1.lower()


def test_hybrid_query_mentions_tier_and_shopping_channel():
    q = hybrid_query(CTX)
    assert "Gold" in q
    assert "online" in q.lower()


def test_hybrid_query_in_store_wording_for_low_online_ratio():
    q = hybrid_query({**CTX, "online_to_store_ratio": 0.1})
    assert "in store" in q.lower()


def test_query_strategies_registry_has_all_three():
    assert set(QUERY_STRATEGIES.keys()) == {"tier_benefit", "constraint", "hybrid"}
    for fn in QUERY_STRATEGIES.values():
        assert isinstance(fn(CTX), str)


def _stub_embed_fn(texts: list[str]) -> np.ndarray:
    vocab = ["returns", "shipping", "loyalty"]
    vectors = []
    for t in texts:
        lower = t.lower()
        vectors.append([1.0 if w in lower else 0.0 for w in vocab])
    arr = np.array(vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def test_retrieve_returns_chunks_not_tuples():
    chunks = [
        Chunk("R-1", "R", "Returns", "H", "returns content"),
        Chunk("S-1", "S", "Shipping", "H", "shipping content"),
    ]
    idx = build_index(chunks, _stub_embed_fn)
    results = retrieve(idx, "returns policy", _stub_embed_fn, k=2)
    assert all(isinstance(c, Chunk) for c in results)
    assert results[0].chunk_id == "R-1"


def test_retrieve_respects_k():
    chunks = [
        Chunk("R-1", "R", "Returns", "H", "returns content"),
        Chunk("S-1", "S", "Shipping", "H", "shipping content"),
        Chunk("L-1", "L", "Loyalty", "H", "loyalty content"),
    ]
    idx = build_index(chunks, _stub_embed_fn)
    results = retrieve(idx, "loyalty tier", _stub_embed_fn, k=1)
    assert len(results) == 1


def test_retrieve_returns_topk_even_with_low_similarity():
    # Review Focus: a query with NO vocabulary overlap must still return the
    # top-k nearest chunks (FAISS always has a nearest neighbor), not an
    # empty list -- an empty contexts list would silently tank faithfulness
    # for what looks like a different bug.
    chunks = [Chunk("R-1", "R", "Returns", "H", "returns content")]
    idx = build_index(chunks, _stub_embed_fn)
    results = retrieve(idx, "completely unrelated query zzz", _stub_embed_fn, k=1)
    assert len(results) == 1
