from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Chunk(StrictModel):
    id: str
    text: str
    filename: str
    heading: str = ""
    created_at: str
    doc_hash: str


class RetrievedChunk(Chunk):
    vector_score: float = 0.0
    bm25_score: float = 0.0
    combined_score: float = 0.0
    final_rank: int = 0
    rerank_score: float | None = None


class IngestResponse(StrictModel):
    ingested_chunks: int
    skipped_duplicates: int
    files: list[str]


class ChatRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    rerank: bool | None = None


class Citation(StrictModel):
    number: int
    chunk_id: str
    filename: str
    heading: str
    excerpt: str
    vector_score: float
    bm25_score: float
    combined_score: float
    final_rank: int


class ConfidenceResult(StrictModel):
    label: Literal["High confidence", "Medium confidence", "Low confidence"]
    score: float
    explanation: str
    escalation_recommended: bool
    heuristic: str = "Proof-of-concept heuristic, not a calibrated probability."


class CheckSupportedSDKArgs(StrictModel):
    platform: Literal["javascript", "python", "react-native"]
    version: str = Field(pattern=r"^\d+(?:\.\d+){1,2}$")


class InspectTraceHeadersArgs(StrictModel):
    headers: dict[str, str] = Field(min_length=1, max_length=30)


class CreateEscalationSummaryArgs(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    findings: list[str] = Field(min_length=1, max_length=10)


ToolName = Literal[
    "check_supported_sdk_version",
    "inspect_trace_headers",
    "create_escalation_summary",
]


class ToolProposal(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: ToolName
    arguments: dict[str, Any]
    reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolProposalRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    findings: list[str] = Field(default_factory=list)
    confidence: ConfidenceResult | None = None


class ToolDecisionRequest(StrictModel):
    proposal_id: str
    approved: bool


class ToolDecisionResponse(StrictModel):
    proposal: ToolProposal
    approved: bool
    result: dict[str, Any] | None = None


class AuditEvent(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    question: str
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    tool_proposal_id: str | None = None
    tool_proposed: str | None = None
    tool_approved: bool | None = None
    tool_result: dict[str, Any] | None = None
    confidence: str | None = None
    escalation_recommended: bool = False
