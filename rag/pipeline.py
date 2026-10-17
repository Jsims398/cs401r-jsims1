"""Wires retrieval + prompting + generation into the exact interface
evaluation_harness.RAGEvaluator expects: invoke(customer_context, question)
-> {"answer": str, "contexts": list[str]}.
"""

from functools import partial

from rag.corpus import load_and_chunk_corpus
from rag.index import ChunkIndex, build_index, load_index, save_index, titan_embed
from rag.retrieve import QUERY_STRATEGIES, retrieve
from rag.prompts import (
    format_contexts, format_system_prompt, format_user_turn, format_profile_context,
)
from rag.generate import generate_offer

DEFAULT_INDEX_CACHE_DIR = "rag/index_cache"

_index_cache: dict[str, ChunkIndex] = {}


def get_or_build_index(cache_dir: str = DEFAULT_INDEX_CACHE_DIR,
                        region: str = "us-east-1") -> ChunkIndex:
    if cache_dir in _index_cache:
        return _index_cache[cache_dir]

    chunks = load_and_chunk_corpus("northstar-policy-docs")
    embed_fn = partial(titan_embed, region=region)

    index = load_index(cache_dir, expected_chunks=chunks)
    if index is None:
        index = build_index(chunks, embed_fn)
        save_index(index, cache_dir)

    _index_cache[cache_dir] = index
    return index


def invoke(customer_context: dict, question: str, query_strategy: str = "hybrid",
           k: int = 6, include_profile_context: bool = True,
           cache_dir: str = DEFAULT_INDEX_CACHE_DIR, region: str = "us-east-1") -> dict:
    index = get_or_build_index(cache_dir=cache_dir, region=region)

    query_fn = QUERY_STRATEGIES[query_strategy]
    query = query_fn(customer_context)

    embed_fn = partial(titan_embed, region=region)
    retrieved_chunks = retrieve(index, query, embed_fn, k=k)

    retrieved_context_text = format_contexts(retrieved_chunks)
    system_prompt = format_system_prompt(retrieved_context_text)
    user_prompt = format_user_turn(customer_context)

    answer = generate_offer(system_prompt, user_prompt, region=region)

    contexts = [c.labeled_text() for c in retrieved_chunks]
    if include_profile_context:
        contexts.append(format_profile_context(customer_context))

    return {"answer": answer, "contexts": contexts}
