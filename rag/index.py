"""FAISS index over the policy corpus, embedded with Titan v2.

The embedding function is injected (not hardcoded to Bedrock) so the index
and search logic can be unit-tested deterministically without AWS calls --
only titan_embed() itself talks to Bedrock, and it is exercised by the live
smoke test instead of a unit test.
"""

import hashlib
import json
import pickle
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import faiss

from rag.corpus import Chunk

EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM = 1024


def _embed_request_body(text: str) -> str:
    return json.dumps({"inputText": text})


def _parse_embed_response(raw_body: bytes) -> list[float]:
    return json.loads(raw_body)["embedding"]


def titan_embed(texts: list[str], region: str = "us-east-1") -> np.ndarray:
    """Embed each text with Titan v2 via Bedrock. One call per text --
    Titan's embed API takes a single inputText per invocation, not a batch."""
    import boto3
    client = boto3.client("bedrock-runtime", region_name=region)
    vectors = []
    for text in texts:
        response = client.invoke_model(
            modelId=EMBED_MODEL_ID,
            body=_embed_request_body(text),
            contentType="application/json",
            accept="application/json",
        )
        vectors.append(_parse_embed_response(response["body"].read()))
    arr = np.array(vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


class ChunkIndex:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, faiss_index: "faiss.Index"):
        self.chunks = chunks
        self.vectors = vectors
        self._faiss_index = faiss_index

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        q = np.asarray(query_vector, dtype="float32").reshape(1, -1)
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm
        k = min(k, len(self.chunks))
        scores, indices = self._faiss_index.search(q, k)
        return [(self.chunks[i], float(scores[0][rank]))
                for rank, i in enumerate(indices[0]) if i != -1]


def build_index(chunks: list[Chunk],
                 embed_fn: Callable[[list[str]], np.ndarray]) -> ChunkIndex:
    texts = [c.labeled_text() for c in chunks]
    vectors = embed_fn(texts)
    dim = vectors.shape[1]
    faiss_index = faiss.IndexFlatIP(dim)  # inner product on normalized vectors == cosine
    faiss_index.add(vectors)
    return ChunkIndex(chunks, vectors, faiss_index)


def cache_key(chunks: list[Chunk]) -> str:
    """Hash of every chunk's id+text, so a corpus or chunking-logic change
    invalidates a stale cached index instead of silently serving old data."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(c.chunk_id.encode())
        h.update(b"\0")
        h.update(c.text.encode())
        h.update(b"\0")
    return h.hexdigest()


def save_index(index: ChunkIndex, cache_dir: str) -> None:
    path = Path(cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index._faiss_index, str(path / "index.faiss"))
    with open(path / "chunks.pkl", "wb") as f:
        pickle.dump(index.chunks, f)
    with open(path / "cache_key.txt", "w") as f:
        f.write(cache_key(index.chunks))


def load_index(cache_dir: str,
               expected_chunks: Optional[list[Chunk]] = None) -> Optional[ChunkIndex]:
    path = Path(cache_dir)
    index_path, chunks_path, key_path = (
        path / "index.faiss", path / "chunks.pkl", path / "cache_key.txt",
    )
    if not (index_path.exists() and chunks_path.exists() and key_path.exists()):
        return None

    with open(chunks_path, "rb") as f:
        chunks = pickle.load(f)

    if expected_chunks is not None:
        stored_key = key_path.read_text().strip()
        if stored_key != cache_key(expected_chunks):
            return None

    faiss_index = faiss.read_index(str(index_path))
    vectors = faiss_index.reconstruct_n(0, faiss_index.ntotal)
    return ChunkIndex(chunks, vectors, faiss_index)
