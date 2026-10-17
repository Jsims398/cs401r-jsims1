"""Second attempt at the 5th 'correct behavior' example -- the first attempt
(CUST-10099001, Gold/in-store/Electronics+Home) surfaced a tier-leakage
failure instead and was reclassified into track-b-examples.md's Failures
section. This profile is a fresh, distinct mix for the actual 5th example.
"""
from rag.pipeline import invoke

customer_context = {
    "customer_id": "CUST-10099002",
    "churn_probability": 0.72,
    "loyalty_tier": "Silver",
    "days_since_last_purchase": 60,
    "total_lifetime_value": 980.00,
    "avg_order_value": 95.00,
    "category_diversity_score": 0.25,
    "online_to_store_ratio": 0.85,
    "top_categories": ["Apparel", "Beauty"],
}
question = (
    "Generate a retention offer for this Silver member who shops almost "
    "entirely online and buys apparel and beauty products."
)

result = invoke(customer_context, question)
print("=== ANSWER ===")
print(result["answer"])
print("\n=== CONTEXTS (chunk_ids only) ===")
for ctx in result["contexts"]:
    first_line = ctx.splitlines()[0]
    print(" ", first_line)
