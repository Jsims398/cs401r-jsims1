"""Manual smoke test: runs the real pipeline (real Bedrock calls) against one
customer profile and prints the result for human inspection. Not part of the
pytest suite -- it costs Bedrock tokens and needs live AWS credentials.

Usage: python scripts/smoke_test_rag.py
"""

from rag.pipeline import invoke

if __name__ == "__main__":
    customer_context = {
        "customer_id": "CUST-10000317",
        "churn_probability": 0.81,
        "loyalty_tier": "Gold",
        "days_since_last_purchase": 47,
        "total_lifetime_value": 3120.40,
        "avg_order_value": 186.25,
        "category_diversity_score": 0.5,
        "online_to_store_ratio": 0.72,
        "top_categories": ["Outdoor", "Footwear"],
    }
    question = (
        "Generate a personalized retention offer for this at-risk Gold member "
        "who shops mostly online for outdoor gear and footwear."
    )

    print("Building/loading index and generating offer (real Bedrock calls)...\n")
    result = invoke(customer_context, question)

    print("=== ANSWER ===")
    print(result["answer"])
    print("\n=== CONTEXTS ===")
    for i, ctx in enumerate(result["contexts"]):
        print(f"\n--- context {i} ---")
        print(ctx)
