from unittest.mock import patch

from rag.corpus import Chunk
import rag.pipeline as pipeline


FAKE_CHUNKS = [
    Chunk("POL-LOY-011-4", "POL-LOY-011", "Summit Rewards", "Tier Benefits", "Gold gets 1.5x points."),
    Chunk("POL-RET-004-1", "POL-RET-004", "Returns Policy", "Standard Return Window", "30 days to return."),
]

CTX = {
    "customer_id": "CUST-1", "loyalty_tier": "Gold", "churn_probability": 0.8,
    "days_since_last_purchase": 40, "total_lifetime_value": 3000.0,
    "avg_order_value": 150.0, "category_diversity_score": 0.5,
    "online_to_store_ratio": 0.7, "top_categories": ["Outdoor"],
}


def test_invoke_returns_answer_and_contexts_keys():
    with patch.object(pipeline, "get_or_build_index", return_value="FAKE_INDEX"), \
         patch.object(pipeline, "retrieve", return_value=FAKE_CHUNKS), \
         patch.object(pipeline, "generate_offer", return_value="Subject: Hi\nBody: ...\nRationale: ..."):
        result = pipeline.invoke(CTX, "Generate an offer.")
    assert set(result.keys()) == {"answer", "contexts"}
    assert result["answer"] == "Subject: Hi\nBody: ...\nRationale: ..."


def test_invoke_contexts_include_retrieved_chunks_and_profile():
    with patch.object(pipeline, "get_or_build_index", return_value="FAKE_INDEX"), \
         patch.object(pipeline, "retrieve", return_value=FAKE_CHUNKS), \
         patch.object(pipeline, "generate_offer", return_value="answer text"):
        result = pipeline.invoke(CTX, "Generate an offer.")
    joined = " ".join(result["contexts"])
    assert "Gold gets 1.5x points." in joined
    assert "30 days to return." in joined
    assert "Gold" in joined and "Outdoor" in joined  # profile context present


def test_invoke_can_exclude_profile_context():
    with patch.object(pipeline, "get_or_build_index", return_value="FAKE_INDEX"), \
         patch.object(pipeline, "retrieve", return_value=FAKE_CHUNKS), \
         patch.object(pipeline, "generate_offer", return_value="answer text"):
        result = pipeline.invoke(CTX, "Generate an offer.", include_profile_context=False)
    joined = " ".join(result["contexts"])
    assert "Customer profile:" not in joined
    assert len(result["contexts"]) == len(FAKE_CHUNKS)


def test_invoke_uses_requested_query_strategy():
    captured = {}

    def fake_retrieve(index, query, embed_fn, k):
        captured["query"] = query
        return FAKE_CHUNKS

    with patch.object(pipeline, "get_or_build_index", return_value="FAKE_INDEX"), \
         patch.object(pipeline, "retrieve", side_effect=fake_retrieve), \
         patch.object(pipeline, "generate_offer", return_value="answer text"):
        pipeline.invoke(CTX, "Generate an offer.", query_strategy="constraint")
    assert "final sale" in captured["query"].lower()
