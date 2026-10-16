from rag.corpus import Chunk
from rag.prompts import (
    TIER_GUIDELINES, GUARDRAILS, format_contexts, format_system_prompt,
    format_user_turn, format_profile_context,
)


def test_tier_guidelines_has_correct_gold_range():
    assert "$2,000" in TIER_GUIDELINES
    assert "$4,999.99" in TIER_GUIDELINES
    assert "$9,999.99" not in TIER_GUIDELINES  # planted error #1, must be gone


def test_tier_guidelines_has_correct_platinum_floor():
    assert "$5,000" in TIER_GUIDELINES
    assert "$10,000" not in TIER_GUIDELINES  # planted error #2, must be gone


def test_tier_guidelines_does_not_claim_free_expedited_shipping():
    lower = TIER_GUIDELINES.lower()
    assert "free expedited shipping" not in lower  # planted error #3, must be gone


def test_tier_guidelines_instructs_conditional_phrasing():
    # Spec decision: conditional phrasing everywhere, not just near-threshold.
    lower = TIER_GUIDELINES.lower() + GUARDRAILS.lower()
    assert "conditional" in lower or "currently receive" in lower


def test_format_contexts_joins_labeled_chunks():
    chunks = [
        Chunk("A-1", "A", "Doc A", "Heading1", "text one"),
        Chunk("B-1", "B", "Doc B", "Heading2", "text two"),
    ]
    joined = format_contexts(chunks)
    assert "text one" in joined
    assert "text two" in joined
    assert "A" in joined and "Heading1" in joined


def test_format_system_prompt_embeds_retrieved_context():
    prompt = format_system_prompt("SOME RETRIEVED TEXT")
    assert "SOME RETRIEVED TEXT" in prompt
    assert "NorthStar" in prompt


def test_format_user_turn_fills_all_fields():
    ctx = {
        "customer_id": "CUST-1", "loyalty_tier": "Gold", "churn_probability": 0.81,
        "days_since_last_purchase": 47, "total_lifetime_value": 3120.40,
        "avg_order_value": 186.25, "category_diversity_score": 0.5,
        "online_to_store_ratio": 0.72, "top_categories": ["Outdoor", "Footwear"],
    }
    turn = format_user_turn(ctx)
    assert "CUST-1" in turn
    assert "Gold" in turn
    assert "81%" in turn
    assert "Outdoor" in turn


def test_format_user_turn_tolerates_missing_optional_field():
    # Review Focus: a profile missing an expected key must not raise.
    ctx = {
        "customer_id": "CUST-2", "loyalty_tier": "Bronze", "churn_probability": 0.5,
        "days_since_last_purchase": 10, "total_lifetime_value": 100.0,
        "avg_order_value": 50.0, "category_diversity_score": 0.2,
        "online_to_store_ratio": 0.5,
        # top_categories intentionally omitted
    }
    turn = format_user_turn(ctx)
    assert "CUST-2" in turn


def test_format_profile_context_includes_tier_and_categories():
    ctx = {"loyalty_tier": "Gold", "top_categories": ["Outdoor", "Footwear"]}
    profile_ctx = format_profile_context(ctx)
    assert "Gold" in profile_ctx
    assert "Outdoor" in profile_ctx
