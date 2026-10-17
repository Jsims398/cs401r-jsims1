"""Run all three Template-4 query strategies against every OFFER_TEST_CASES
customer and record what each one retrieves, so the design doc can report
which performs best and WHY (not just a number) -- Template 4's lab task.
"""

import csv
from functools import partial

from rag.index import titan_embed
from rag.pipeline import get_or_build_index
from rag.retrieve import QUERY_STRATEGIES, retrieve
from evaluation.evaluation_harness import OFFER_TEST_CASES

OUTPUT_PATH = "docs/lab3-evidence/query-strategy-comparison.csv"


def main():
    index = get_or_build_index()
    embed_fn = partial(titan_embed, region="us-east-1")

    rows = []
    for strategy_name, query_fn in QUERY_STRATEGIES.items():
        for tc in OFFER_TEST_CASES:
            query = query_fn(tc.customer_context)
            chunks = retrieve(index, query, embed_fn, k=6)
            rows.append({
                "strategy": strategy_name,
                "customer_id": tc.customer_id,
                "n_chunks_retrieved": len(chunks),
                "chunk_ids": ";".join(c.chunk_id for c in chunks),
                "doc_ids_covered": ";".join(sorted(set(c.doc_id for c in chunks))),
            })

    import os
    os.makedirs("docs/lab3-evidence", exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    for row in rows:
        print(f"  {row['strategy']:12s} {row['customer_id']:16s} "
              f"docs={row['doc_ids_covered']}")


if __name__ == "__main__":
    main()
