"""Three query strategies from Template 4 of offer_generation_prompts.md,
retrieving POLICY (what the offer may promise), never products -- the
corpus has no product catalog."""

from typing import Callable

from rag.corpus import Chunk
from rag.index import ChunkIndex


def tier_benefit_query(customer_context: dict) -> str:
    tier = customer_context.get("loyalty_tier", "")
    return (
        f"loyalty tier {tier} benefits points earn rate "
        f"free shipping threshold return window birthday reward"
    )


def constraint_query(customer_context: dict) -> str:
    # Deliberately tier-independent: these limits apply to every customer.
    return (
        "final sale non-returnable exclusions expired offers cannot be reinstated "
        "retention offer validity single use combinability"
    )


def hybrid_query(customer_context: dict) -> str:
    tier = customer_context.get("loyalty_tier", "")
    channel = "online" if customer_context.get("online_to_store_ratio", 0.5) > 0.5 else "in store"
    return (
        f"tier {tier} entitlements and shipping thresholds for a customer who shops {channel}"
    )


QUERY_STRATEGIES: dict[str, Callable[[dict], str]] = {
    "tier_benefit": tier_benefit_query,
    "constraint": constraint_query,
    "hybrid": hybrid_query,
}


def retrieve(index: ChunkIndex, query: str,
             embed_fn: Callable[[list[str]], "object"], k: int = 6) -> list[Chunk]:
    query_vector = embed_fn([query])[0]
    results = index.search(query_vector, k=k)
    return [chunk for chunk, _score in results]
