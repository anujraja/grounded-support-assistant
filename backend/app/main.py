from __future__ import annotations

import json
import re
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .audit import AuditLog
from .confidence import calculate_confidence
from .config import SAMPLE_DOCS, settings
from .generation import stream_ollama
from .ingestion import DocumentStore
from .models import (
    AuditEvent,
    ChatRequest,
    Citation,
    IngestResponse,
    ToolDecisionRequest,
    ToolDecisionResponse,
    ToolProposal,
    ToolProposalRequest,
)
from .reranking import OptionalReranker
from .retrieval import HybridRetriever
from .tools import ToolRegistry, propose_for_question

store = DocumentStore()
retriever = HybridRetriever(store)
reranker = OptionalReranker(settings.reranker_model, settings.enable_reranking)
tool_registry = ToolRegistry()
audit_log = AuditLog()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if store.collection.count() == 0:
        await asyncio.to_thread(store.ingest_paths, sorted(SAMPLE_DOCS.glob("*")))
    yield


app = FastAPI(title="Grounded Support Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def sse(event: str, data: Any) -> str:
    payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@app.get("/health")
async def health() -> dict[str, Any]:
    ollama: dict[str, Any]
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            models = [item.get("name") for item in response.json().get("models", [])]
        model_available = settings.ollama_model in models
        ollama = {
            "status": "ok" if model_available else "unavailable",
            "model_configured": settings.ollama_model,
            "model_available": model_available,
        }
        if not model_available:
            ollama.update({"error": "ModelNotPulled", "help": f"Run: ollama pull {settings.ollama_model}"})
    except httpx.HTTPError as exc:
        ollama = {"status": "unavailable", "error": type(exc).__name__, "help": "Start Ollama and pull the configured model."}
    dependencies = {
        "chroma": {"status": "ok", "chunks": store.collection.count()},
        "ollama": ollama,
        "reranker": {"enabled": settings.enable_reranking, "last_error": reranker.last_error},
    }
    return {"status": "ok" if ollama["status"] == "ok" else "degraded", "dependencies": dependencies}


@app.post("/api/ingest", response_model=IngestResponse)
def ingest_samples() -> IngestResponse:
    return store.ingest_paths(sorted(SAMPLE_DOCS.glob("*")))


@app.post("/api/upload", response_model=IngestResponse)
async def upload_document(file: UploadFile = File(...)) -> IngestResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".md", ".txt"}:
        raise HTTPException(status_code=415, detail="Only .md and .txt files are accepted")
    body = await file.read(2_000_001)
    if len(body) > 2_000_000:
        raise HTTPException(status_code=413, detail="Document exceeds the 2 MB demo limit")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Document must be UTF-8 text") from exc
    safe_name = Path(file.filename or "upload.txt").name
    count, duplicate = await asyncio.to_thread(store.ingest_text, text, safe_name)
    return IngestResponse(ingested_chunks=count, skipped_duplicates=int(duplicate), files=[safe_name])


@app.get("/api/documents")
def list_documents() -> list[dict[str, object]]:
    return store.documents()


@app.get("/api/audit", response_model=list[AuditEvent])
def list_audit() -> list[AuditEvent]:
    return audit_log.list()


@app.post("/api/tools/propose", response_model=ToolProposal | None)
def propose_tool(request: ToolProposalRequest) -> ToolProposal | None:
    proposal = propose_for_question(request.question, request.findings, request.confidence)
    if not proposal:
        return None
    proposal = tool_registry.save(proposal)
    audit_log.add(
        AuditEvent(
            question=request.question,
            tool_proposal_id=proposal.id,
            tool_proposed=proposal.tool_name,
            confidence=request.confidence.label if request.confidence else None,
            escalation_recommended=request.confidence.escalation_recommended if request.confidence else False,
        )
    )
    return proposal


@app.post("/api/tools/execute", response_model=ToolDecisionResponse)
def execute_tool(request: ToolDecisionRequest) -> ToolDecisionResponse:
    try:
        proposal, result = tool_registry.execute(request.proposal_id, request.approved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_log.update_tool(proposal.id, request.approved, result)
    return ToolDecisionResponse(proposal=proposal, approved=request.approved, result=result)


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    async def events():
        try:
            chunks, retrieval_debug = await asyncio.to_thread(retriever.retrieve, request.question, settings.top_k)
            chunks = await asyncio.to_thread(reranker.rerank, request.question, chunks, request.rerank)
            confidence = calculate_confidence(request.question, chunks, float(retrieval_debug["agreement"]))
            citations = [
                Citation(
                    number=index,
                    chunk_id=chunk.id,
                    filename=chunk.filename,
                    heading=chunk.heading,
                    excerpt=chunk.text[:420],
                    vector_score=chunk.vector_score,
                    bm25_score=chunk.bm25_score,
                    combined_score=chunk.combined_score,
                    final_rank=chunk.final_rank,
                )
                for index, chunk in enumerate(chunks, 1)
            ]
            findings = [f"Retrieved {chunk.filename}: {chunk.heading or 'Document'}" for chunk in chunks[:3]]
            proposal = propose_for_question(request.question, findings, confidence)
            if proposal:
                proposal = tool_registry.save(proposal)
            destructive = bool(re.search(r"\b(delete|purge|destroy|disable|rotate|modify)\b", request.question, re.I))
            audit = audit_log.add(
                AuditEvent(
                    question=request.question,
                    retrieved_chunk_ids=[chunk.id for chunk in chunks],
                    tool_proposal_id=proposal.id if proposal else None,
                    tool_proposed=proposal.tool_name if proposal else None,
                    confidence=confidence.label,
                    escalation_recommended=confidence.escalation_recommended or destructive,
                )
            )
            yield sse(
                "meta",
                {
                    "citations": [citation.model_dump() for citation in citations],
                    "retrieval": [chunk.model_dump() for chunk in chunks],
                    "retrieval_debug": retrieval_debug,
                    "confidence": confidence.model_dump(),
                    "tool_proposal": proposal.model_dump(mode="json") if proposal else None,
                    "audit_id": audit.id,
                    "destructive_refusal": destructive,
                    "reranker_error": reranker.last_error,
                },
            )
            if destructive:
                yield sse(
                    "token",
                    "I can’t perform or propose that destructive action. No destructive tool is allowlisted. A human support engineer must review the request.",
                )
            else:
                pending_citation = ""
                citation_seen = False
                async for token in stream_ollama(request.question, chunks):
                    safe_token = ""
                    for character in token:
                        if not pending_citation:
                            if character == "[":
                                pending_citation = character
                            else:
                                safe_token += character
                        elif character.isdigit():
                            pending_citation += character
                        elif character == "]" and len(pending_citation) > 1:
                            citation_number = int(pending_citation[1:])
                            if 1 <= citation_number <= len(chunks):
                                safe_token += f"[{citation_number}]"
                                citation_seen = True
                            else:
                                safe_token += "[unsupported citation removed]"
                            pending_citation = ""
                        else:
                            safe_token += pending_citation + character
                            pending_citation = ""
                    if safe_token:
                        yield sse("token", safe_token)
                if pending_citation:
                    yield sse("token", pending_citation)
                if chunks and not citation_seen:
                    yield sse("token", "\n\nSupporting evidence: [1]")
            yield sse("done", {"audit_id": audit.id})
        except Exception as exc:
            yield sse("error", {"message": f"Request failed safely: {type(exc).__name__}: {exc}"})
            yield sse("done", {})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
