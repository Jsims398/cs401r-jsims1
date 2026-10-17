"""One-off: generate the 5th 'correct behavior' example for
docs/lab3-evidence/track-b-examples.md -- a profile not in OFFER_TEST_CASES,
picked to exercise hybrid's "in store" channel wording on a non-Bronze tier
(the 4 harness cases only trigger that branch for Bronze/CUST-10000904).
"""
from rag.pipeline import invoke
from rag.retrieve import hybrid_query

customer_context = {
    "customer_id": "CUST-10099001",
    "churn_probability": 0.69,
    "loyalty_tier": "Gold",
    "days_since_last_purchase": 55,
    "total_lifetime_value": 2890.00,
    "avg_order_value": 210.00,
    "category_diversity_score": 0.375,
    "online_to_store_ratio": 0.15,
    "top_categories": ["Electronics", "Home"],
}
question = (
    "Generate a retention offer for this Gold member who shops almost "
    "entirely in store and buys electronics and home goods."
)

print("query:", hybrid_query(customer_context))
result = invoke(customer_context, question)
print("\n=== ANSWER ===")
print(result["answer"])
print("\n=== CONTEXTS (chunk_ids only) ===")
for ctx in result["contexts"]:
    first_line = ctx.splitlines()[0]
    print(" ", first_line)
