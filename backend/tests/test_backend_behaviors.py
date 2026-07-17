from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("CHROMA_PATH", "/tmp/grounded-support-assistant-tests-chroma")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _StubSentenceTransformer:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def encode(self, texts: list[str], normalize_embeddings: bool = True):
        return [[float(len(text.split())), float(len(text))] for text in texts]


class _StubCrossEncoder:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def predict(self, pairs: list[tuple[str, str]]):
        return [float(len(text)) for _, text in pairs]


class _StubBM25Okapi:
    def __init__(self, corpus: list[list[str]]):
        self.corpus = corpus

    def get_scores(self, query_tokens: list[str]):
        scores = []
        query_set = set(query_tokens)
        for document_tokens in self.corpus:
            document_set = set(document_tokens)
            score = sum(1.0 for token in query_set if token in document_set)
            scores.append(score)
        return types.SimpleNamespace(tolist=lambda: scores)


class _FakeCollection:
    def __init__(self) -> None:
        self._rows: list[dict[str, object]] = []

    def add(self, ids, documents, metadatas, embeddings) -> None:
        for identifier, document, metadata, embedding in zip(ids, documents, metadatas, embeddings):
            self._rows.append(
                {
                    "id": identifier,
                    "document": document,
                    "metadata": metadata,
                    "embedding": embedding,
                }
            )

    def get(self, where=None, limit=None, include=None):
        rows = self._rows
        if where:
            rows = [row for row in rows if all(row["metadata"].get(key) == value for key, value in where.items())]
        if limit is not None:
            rows = rows[:limit]
        return {
            "ids": [row["id"] for row in rows],
            "documents": [row["document"] for row in rows],
            "metadatas": [row["metadata"] for row in rows],
        }

    def query(self, query_embeddings, n_results, include=None):
        query_embedding = query_embeddings[0]
        scored = []
        for row in self._rows:
            embedding = row["embedding"]
            dot = sum(float(a) * float(b) for a, b in zip(query_embedding, embedding))
            scored.append((row["id"], max(0.0, 1.0 - dot)))
        scored.sort(key=lambda item: item[1])
        top = scored[:n_results]
        return {"ids": [[identifier for identifier, _ in top]], "distances": [[distance for _, distance in top]]}

    def count(self) -> int:
        return len(self._rows)


class _FakeClient:
    def __init__(self, path: str):
        self.path = path
        self._collection = _FakeCollection()

    def get_or_create_collection(self, name: str, metadata: dict[str, object] | None = None):
        return self._collection


sys.modules.setdefault("chromadb", types.SimpleNamespace(PersistentClient=_FakeClient))
sys.modules.setdefault("python_multipart", types.SimpleNamespace(__version__="0.0.20"))
sys.modules.setdefault("rank_bm25", types.SimpleNamespace(BM25Okapi=_StubBM25Okapi))
sys.modules.setdefault(
    "sentence_transformers",
    types.SimpleNamespace(SentenceTransformer=_StubSentenceTransformer, CrossEncoder=_StubCrossEncoder),
)

from app.confidence import calculate_confidence
from app.config import Settings
from app.generation import build_prompt
from app.ingestion import DocumentStore, chunk_markdown
from app.main import app
from app.models import Chunk, ConfidenceResult, RetrievedChunk, ToolProposalRequest
from app.retrieval import HybridRetriever, combine_scores, tokenize
from app.tools import ToolRegistry, propose_for_question, validate_tool_arguments


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text.split())), float(len(text))] for text in texts]


class RetrievalStore:
    def __init__(self, chunks: list[Chunk], vector_ids: list[str], distances: list[float]) -> None:
        self._chunks = chunks
        self.embedder = FakeEmbedder()
        self.collection = types.SimpleNamespace(
            query=lambda query_embeddings, n_results, include=None: {
                "ids": [vector_ids[:n_results]],
                "distances": [distances[:n_results]],
            }
        )

    def all_chunks(self) -> list[Chunk]:
        return list(self._chunks)


def make_chunk(
    chunk_id: str,
    text: str,
    *,
    filename: str = "kb.md",
    heading: str = "Guide",
    vector_score: float = 0.0,
    bm25_score: float = 0.0,
    combined_score: float = 0.0,
    final_rank: int = 0,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        text=text,
        filename=filename,
        heading=heading,
        created_at="2026-07-17T00:00:00+00:00",
        doc_hash=f"hash-{chunk_id}",
        vector_score=vector_score,
        bm25_score=bm25_score,
        combined_score=combined_score,
        final_rank=final_rank,
    )


def make_base_chunk(chunk_id: str, text: str, *, filename: str = "kb.md", heading: str = "Guide") -> Chunk:
    return Chunk(
        id=chunk_id,
        text=text,
        filename=filename,
        heading=heading,
        created_at="2026-07-17T00:00:00+00:00",
        doc_hash=f"hash-{chunk_id}",
    )


def parse_sse(body: str) -> list[tuple[str, object]]:
    events: list[tuple[str, object]] = []
    for block in body.strip().split("\n\n"):
        event_name = None
        payload = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
        if event_name is not None:
            events.append((event_name, payload))
    return events


@pytest.fixture
def client():
    return TestClient(app)


def test_chunk_markdown_preserves_headings_and_overlap():
    text = "# Login\none two three four five six seven eight nine ten\n## Billing\na b c d e f g h i"

    chunks = chunk_markdown(text, chunk_size=4, overlap=1)

    assert chunks == [
        ("Login", "one two three four"),
        ("Login", "four five six seven"),
        ("Login", "seven eight nine ten"),
        ("Billing", "a b c d"),
        ("Billing", "d e f g"),
        ("Billing", "g h i"),
    ]


def test_document_store_skips_duplicate_ingestion_and_counts_documents(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "alpha.md").write_text("# Alpha\nsame repeated text", encoding="utf-8")
    (docs_dir / "beta.txt").write_text("# Beta\nunique content here", encoding="utf-8")
    (docs_dir / "ignored.png").write_bytes(b"not-text")

    store = DocumentStore(
        app_settings=Settings(chroma_path=tmp_path / "chroma", embedding_model="stub"),
        client=_FakeClient(str(tmp_path / "chroma")),
        embedder=FakeEmbedder(),
    )

    first = store.ingest_paths(sorted(docs_dir.iterdir()))
    second = store.ingest_paths(sorted(docs_dir.iterdir()))

    assert first.ingested_chunks == 2
    assert first.skipped_duplicates == 0
    assert first.files == ["alpha.md", "beta.txt"]
    assert second.ingested_chunks == 0
    assert second.skipped_duplicates == 2
    assert store.documents() == [{"filename": "alpha.md", "chunks": 1}, {"filename": "beta.txt", "chunks": 1}]


def test_hybrid_retriever_uses_bm25_for_exact_term_matches():
    chunks = [
        make_base_chunk("a", "generic troubleshooting steps"),
        make_base_chunk("b", "sdk 8.25.0 ios crash on launch"),
        make_base_chunk("c", "another generic article"),
    ]
    store = RetrievalStore(chunks, ["a", "b", "c"], [1.0, 1.0, 1.0])

    results, debug = HybridRetriever(store).retrieve("Is sdk 8.25.0 supported?", top_k=2, candidate_k=3)

    assert tokenize("sdk 8.25.0 supported?") == ["sdk", "8.25.0", "supported"]
    assert results[0].id == "b"
    assert results[0].bm25_score == 1.0
    assert results[0].vector_score == 0.0
    assert debug["bm25_top_ids"][0] == "b"


def test_hybrid_retriever_fuses_vector_and_bm25_scores_with_vector_weighting():
    chunks = [
        make_base_chunk("vector-heavy", "unrelated body"),
        make_base_chunk("bm25-heavy", "react-native sdk support matrix"),
    ]
    store = RetrievalStore(chunks, ["vector-heavy", "bm25-heavy"], [0.0, 1.0])

    results, _ = HybridRetriever(store).retrieve("react-native sdk support", top_k=2, candidate_k=2)

    by_id = {result.id: result for result in results}
    assert by_id["vector-heavy"].combined_score == combine_scores(1.0, 0.0)
    assert by_id["bm25-heavy"].combined_score == combine_scores(0.0, 1.0)
    assert results[0].id == "vector-heavy"


def test_build_prompt_uses_only_supplied_chunks_with_traceable_labels():
    chunks = [
        make_chunk("c1", "First evidence line", filename="alpha.md", heading="Login"),
        make_chunk("c2", "Second evidence line", filename="beta.md", heading="Billing"),
    ]

    prompt = build_prompt("What changed?", chunks)

    assert "[1] alpha.md - Login\nFirst evidence line" in prompt
    assert "[2] beta.md - Billing\nSecond evidence line" in prompt
    assert "No retrieved evidence." not in prompt
    assert "QUESTION\nWhat changed?" in prompt


def test_tool_validation_and_execution_require_allowlisted_tool_and_explicit_approval():
    registry = ToolRegistry()
    proposal = registry.save(
        propose_for_question("Is javascript sdk 8.25.0 supported?")  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="Unknown or non-allowlisted tool"):
        validate_tool_arguments("totally_unknown_tool", {})

    with pytest.raises(ValueError, match="Invalid tool arguments"):
        validate_tool_arguments(
            "check_supported_sdk_version",
            {"platform": "javascript", "version": "8.25.0", "unexpected": "blocked"},
        )

    stored, denied_result = registry.execute(proposal.id, approved=False)
    with pytest.raises(ValueError, match="already been approved or rejected"):
        registry.execute(proposal.id, approved=True)

    approved = registry.save(
        propose_for_question("Is javascript sdk 8.25.0 supported?")  # type: ignore[arg-type]
    )
    approved_proposal, approved_result = registry.execute(approved.id, approved=True)

    assert stored.id == proposal.id
    assert denied_result is None
    assert approved_proposal.id == approved.id
    assert approved_result == {
        "platform": "javascript",
        "version": "8.25.0",
        "supported": True,
        "supported_demo_versions": ["7.120.0", "8.0.0", "8.25.0"],
        "note": "Fictional demonstration matrix only.",
    }


def test_low_confidence_questions_propose_escalation_summary():
    confidence = calculate_confidence("This is not covered in the docs", [make_chunk("c1", "thin evidence", combined_score=0.12)], 0.0)

    proposal = propose_for_question("This is not covered in the docs", ["Only one weak chunk"], confidence)

    assert confidence.label == "Low confidence"
    assert confidence.escalation_recommended is True
    assert proposal is not None
    assert proposal.tool_name == "create_escalation_summary"
    assert proposal.arguments["findings"] == ["Only one weak chunk"]


def test_chat_stream_emits_traceable_citations_and_destructive_refusal(client, monkeypatch):
    chunks = [
        make_chunk(
            "chunk-1",
            "Keep the sdk at 8.25.0 for this integration.",
            filename="support.md",
            heading="SDK versions",
            vector_score=0.9,
            bm25_score=0.8,
            combined_score=0.85,
            final_rank=1,
        )
    ]

    async def fake_stream(question: str, retrieved_chunks: list[RetrievedChunk]):
        yield "Verified answer [1]"

    monkeypatch.setattr("app.main.retriever.retrieve", lambda question, top_k: (chunks, {"vector_top_ids": ["chunk-1"], "bm25_top_ids": ["chunk-1"], "agreement": 1.0}))
    monkeypatch.setattr("app.main.reranker.rerank", lambda question, retrieved_chunks, enabled: retrieved_chunks)
    monkeypatch.setattr("app.main.stream_ollama", fake_stream)
    monkeypatch.setattr("app.main.tool_registry", ToolRegistry())
    monkeypatch.setattr("app.main.audit_log", types.SimpleNamespace(add=lambda event: event, update_tool=lambda proposal_id, approved, result: None))

    response = client.post("/api/chat", json={"question": "Delete the user data and tell me the sdk guidance", "rerank": False})

    assert response.status_code == 200
    events = parse_sse(response.text)
    meta = next(payload for event, payload in events if event == "meta")
    token = next(payload for event, payload in events if event == "token")

    assert meta["destructive_refusal"] is True
    assert meta["citations"] == [
        {
            "number": 1,
            "chunk_id": "chunk-1",
            "filename": "support.md",
            "heading": "SDK versions",
            "excerpt": "Keep the sdk at 8.25.0 for this integration.",
            "vector_score": 0.9,
            "bm25_score": 0.8,
            "combined_score": 0.85,
            "final_rank": 1,
        }
    ]
    assert meta["retrieval"][0]["id"] == "chunk-1"
    assert meta["retrieval"][0]["text"] == "Keep the sdk at 8.25.0 for this integration."
    assert "I can’t perform or propose that destructive action" in token


def test_tools_propose_endpoint_accepts_low_confidence_payload(client):
    response = client.post(
        "/api/tools/propose",
        json=ToolProposalRequest(
            question="unknown product, not covered",
            findings=["No matching document"],
            confidence=ConfidenceResult(
                label="Low confidence",
                score=0.1,
                explanation="No supporting chunks were retrieved.",
                escalation_recommended=True,
            ),
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tool_name"] == "create_escalation_summary"
    assert body["arguments"]["findings"] == ["No matching document"]
