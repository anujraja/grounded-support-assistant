from __future__ import annotations

import re
from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from .ingestion import DocumentStore
from .models import Chunk, RetrievedChunk

STOP_WORDS = {
    "a", "an", "and", "are", "do", "does", "for", "how", "i", "in", "is", "it",
    "my", "of", "on", "or", "the", "this", "to", "what", "when", "why", "with",
}


def tokenize(text: str) -> list[str]:
    """Keep punctuation-bearing technical tokens useful to BM25."""
    return [token for token in re.findall(r"[a-z0-9_.:/-]+", text.lower()) if token not in STOP_WORDS]


def normalize_scores(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high <= low:
        return [1.0 if high > 0 else 0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def combine_scores(vector_score: float, bm25_score: float, vector_weight: float = 0.55) -> float:
    return round(vector_weight * vector_score + (1 - vector_weight) * bm25_score, 6)


class HybridRetriever:
    def __init__(self, store: DocumentStore):
        self.store = store

    def retrieve(self, question: str, top_k: int = 6, candidate_k: int = 16) -> tuple[list[RetrievedChunk], dict[str, object]]:
        chunks = [
            chunk
            for chunk in self.store.all_chunks()
            if not chunk.text.lstrip().startswith("> Fictional demonstration content only.")
        ]
        if not chunks:
            return [], {"vector_top_ids": [], "bm25_top_ids": [], "agreement": 0.0}

        candidate_k = min(candidate_k, len(chunks))
        query_embedding = self.store.embedder.embed([question])
        allowed_ids = {chunk.id for chunk in chunks}
        vector = self.store.collection.query(
            query_embeddings=query_embedding,
            n_results=min(len(chunks), max(candidate_k, candidate_k * 2)),
            include=["distances"],
        )
        vector_raw: dict[str, float] = {}
        for identifier, distance in zip(vector["ids"][0], vector["distances"][0]):
            if identifier in allowed_ids and len(vector_raw) < candidate_k:
                vector_raw[identifier] = max(0.0, 1.0 - float(distance))

        corpus = [tokenize(chunk.text) for chunk in chunks]
        bm25_raw_values = BM25Okapi(corpus).get_scores(tokenize(question)).tolist()
        bm25_raw = {chunk.id: float(score) for chunk, score in zip(chunks, bm25_raw_values)}

        vector_ids = sorted(vector_raw, key=vector_raw.get, reverse=True)
        bm25_ids = sorted(bm25_raw, key=bm25_raw.get, reverse=True)[:candidate_k]
        candidate_ids = list(dict.fromkeys(vector_ids + bm25_ids))

        vector_norm_values = normalize_scores([vector_raw.get(identifier, 0.0) for identifier in candidate_ids])
        bm25_norm_values = normalize_scores([bm25_raw.get(identifier, 0.0) for identifier in candidate_ids])
        by_id = {chunk.id: chunk for chunk in chunks}
        results: list[RetrievedChunk] = []
        for identifier, vector_score, bm25_score in zip(candidate_ids, vector_norm_values, bm25_norm_values):
            chunk = by_id[identifier]
            results.append(
                RetrievedChunk(
                    **chunk.model_dump(),
                    vector_score=round(vector_score, 6),
                    bm25_score=round(bm25_score, 6),
                    combined_score=combine_scores(vector_score, bm25_score),
                )
            )
        results.sort(key=lambda item: item.combined_score, reverse=True)
        results = results[:top_k]
        for rank, result in enumerate(results, 1):
            result.final_rank = rank

        compare_n = min(5, candidate_k)
        overlap = set(vector_ids[:compare_n]) & set(bm25_ids[:compare_n])
        debug = {
            "vector_top_ids": vector_ids[:compare_n],
            "bm25_top_ids": bm25_ids[:compare_n],
            "agreement": round(len(overlap) / max(1, compare_n), 3),
        }
        return results, debug
