# Architecture

Grounded Support Assistant is a local proof-of-concept for evidence-first technical support. It is intentionally small: one FastAPI backend, one React workbench, local Chroma persistence, local embedding/reranking models, and Ollama for generation.

The architecture is optimized for interview clarity. Retrieval, citations, confidence, tool approval, and audit events are server-owned so the demo can explain where each grounded answer came from and why a risky action was not executed automatically.

## System Context

```mermaid
flowchart LR
  Operator["Support operator / interviewer"]
  Browser["React evidence workbench<br/>localhost:5173"]
  API["FastAPI support API<br/>localhost:8010 or container:8000"]
  Docs["Fictional Markdown docs<br/>sample_docs + uploads"]
  Chroma["ChromaDB persistent collection<br/>backend/data/chroma or Docker volume"]
  Embeddings["Sentence Transformers<br/>local embedding model"]
  Reranker["Optional CrossEncoder reranker<br/>local model, graceful fallback"]
  Ollama["Ollama local LLM<br/>qwen2.5:3b by default"]
  Audit["In-memory audit log<br/>demo process state"]

  Operator -->|"asks questions, approves tools"| Browser
  Browser -->|"HTTP + streaming SSE"| API
  API -->|"reads / ingests"| Docs
  API -->|"stores chunks and vectors"| Chroma
  API -->|"embeds docs and queries"| Embeddings
  API -->|"optionally reranks candidates"| Reranker
  API -->|"streams prompt responses"| Ollama
  API -->|"records questions, chunk ids, decisions"| Audit
  Browser -->|"renders citations, retrieval scores, audit"| Operator
```

## Container Boundaries

```mermaid
flowchart TB
  subgraph Frontend["frontend/ React + TypeScript + Vite"]
    UI["App.tsx<br/>three-pane evidence workbench"]
    APIClient["src/lib/api.ts<br/>fetch, upload, SSE parser"]
    CSS["index.css<br/>plain CSS visual system"]
  end

  subgraph Backend["backend/app FastAPI"]
    Main["main.py<br/>HTTP endpoints + SSE orchestration"]
    Ingestion["ingestion.py<br/>chunking, hashing, Chroma persistence"]
    Retrieval["retrieval.py<br/>vector + BM25 fusion"]
    Reranking["reranking.py<br/>optional cross-encoder"]
    Generation["generation.py<br/>Ollama prompt + stream"]
    Confidence["confidence.py<br/>POC confidence heuristic"]
    Tools["tools.py<br/>allowlist + strict schemas + approval registry"]
    Audit["audit.py<br/>local redacted audit events"]
    Models["models.py<br/>Pydantic contracts"]
    Config["config.py<br/>environment settings"]
  end

  UI --> APIClient
  APIClient -->|"GET /health, GET /api/documents"| Main
  APIClient -->|"POST /api/chat SSE"| Main
  APIClient -->|"POST /api/upload"| Main
  APIClient -->|"POST /api/tools/execute"| Main

  Main --> Ingestion
  Main --> Retrieval
  Main --> Reranking
  Main --> Confidence
  Main --> Generation
  Main --> Tools
  Main --> Audit
  Main --> Models
  Main --> Config
```

## Data Ownership

| Data | Owner | Stored in | Notes |
| --- | --- | --- | --- |
| Source documents | `sample_docs/` and upload endpoint | Filesystem for samples; uploaded text is immediately chunked | Demo content is fictional and must stay free of real customer data. |
| Chunks and metadata | `DocumentStore` | Chroma collection `support_chunks` | Stores chunk text, filename, heading, chunk id, timestamp, and content hash. |
| Embeddings | `DocumentStore` | Chroma collection | Generated locally through Sentence Transformers. |
| BM25 corpus | `HybridRetriever` | Rebuilt in memory from stored chunks | Keeps exact technical terms, versions, headers, and error codes retrievable. |
| Citations | `main.py` | Response metadata only | Citation numbers are assigned from retrieved chunks and filtered during generation. |
| Tool proposals | `ToolRegistry` | In-memory process state | A proposal must exist before execution and can be decided only once. |
| Audit trail | `AuditLog` | In-memory process state | Redacted local demo log, not durable compliance storage. |

## Critical Flow: Ingestion

```mermaid
sequenceDiagram
  autonumber
  participant User as Operator
  participant UI as React workbench
  participant API as FastAPI /api/ingest or /api/upload
  participant Store as DocumentStore
  participant Embed as Sentence Transformers
  participant Chroma as ChromaDB

  User->>UI: Click ingest samples or upload .md/.txt
  UI->>API: POST /api/ingest or POST /api/upload
  API->>Store: ingest_paths() or ingest_text()
  Store->>Store: SHA-256 document hash duplicate check
  Store->>Store: Heading-aware overlapping chunks
  Store->>Embed: Embed chunk text locally
  Embed-->>Store: Normalized vectors
  Store->>Chroma: Add ids, text, metadata, embeddings
  Chroma-->>Store: Persisted chunks
  Store-->>API: Ingested and skipped counts
  API-->>UI: IngestResponse
```

## Critical Flow: Grounded Chat

```mermaid
sequenceDiagram
  autonumber
  participant User as Operator
  participant UI as React workbench
  participant API as FastAPI /api/chat
  participant Retriever as HybridRetriever
  participant Reranker as OptionalReranker
  participant Conf as Confidence heuristic
  participant Tools as Tool proposal logic
  participant LLM as Ollama
  participant Audit as AuditLog

  User->>UI: Submit support question
  UI->>API: POST /api/chat
  API->>Retriever: Vector search + BM25 search
  Retriever-->>API: Deduped ranked chunks + debug scores
  API->>Reranker: Optional rerank in worker thread
  Reranker-->>API: Reranked chunks or original order
  API->>Conf: Calculate explainable confidence
  API->>Tools: Propose allowed tool if question warrants it
  API->>Audit: Record question, chunk ids, confidence, proposal
  API-->>UI: SSE meta event with citations, retrieval, confidence, tool proposal
  API->>LLM: Prompt with retrieved evidence only
  LLM-->>API: Streaming tokens
  API->>API: Strip unsupported citation numbers
  API-->>UI: SSE token events
  API-->>UI: SSE done event
```

## Critical Flow: Tool Approval

```mermaid
sequenceDiagram
  autonumber
  participant User as Operator
  participant UI as Tool approval tab
  participant API as FastAPI /api/tools/execute
  participant Registry as ToolRegistry
  participant Tool as Deterministic local function
  participant Audit as AuditLog

  UI-->>User: Show proposed tool, args, and reason
  User->>UI: Approve or reject
  UI->>API: POST /api/tools/execute { proposal_id, approved }
  API->>Registry: Validate stored proposal and one-time decision
  alt Rejected
    Registry-->>API: No execution result
  else Approved
    Registry->>Registry: Strict Pydantic argument validation
    Registry->>Tool: Execute allowlisted deterministic function
    Tool-->>Registry: Result
    Registry-->>API: Result
  end
  API->>Audit: Record decision and result
  API-->>UI: ToolDecisionResponse
```

## Module Contracts

| Module | Responsibility | Must not do |
| --- | --- | --- |
| `main.py` | Orchestrate endpoints, streaming, citation assignment, and audit writes | Embed business logic that belongs in retrieval/tools/confidence modules. |
| `ingestion.py` | Chunk documents, deduplicate by content hash, persist Chroma records | Call Ollama or decide answer confidence. |
| `retrieval.py` | Tokenize, run vector/BM25 retrieval, normalize and fuse scores | Generate answers or invent citations. |
| `reranking.py` | Optionally rerank candidates with a local model | Make reranking mandatory for a successful chat. |
| `generation.py` | Build grounded prompts and stream Ollama output | Execute tools or choose citation ids. |
| `confidence.py` | Produce a transparent heuristic label | Claim statistical calibration. |
| `tools.py` | Define the complete allowlist, strict schemas, proposal storage, and execution gate | Perform network, filesystem mutation, or production actions. |
| `audit.py` | Redact and record local demo audit events | Store secrets or act as compliance-grade durable logging. |

## Failure Modes

| Failure | Current behavior | Portfolio talking point | Production hardening |
| --- | --- | --- | --- |
| Ollama unavailable | `/health` reports degraded; chat streams an explicit unavailable message | The app fails closed instead of inventing support guidance | Queue/retry policy, model readiness probes, fallback model strategy. |
| Reranker unavailable | Hybrid retrieval continues and exposes `reranker_error` | Optional quality layer is not a single point of failure | Model cache management and versioned evaluation. |
| Empty or weak retrieval | Low confidence and escalation recommendation | The assistant admits insufficient evidence | Calibrated evaluation set and support-ticket routing integration. |
| Unknown/destructive tool | Rejected by allowlist or no proposal generated | The model never receives execution authority | Auth, RBAC, signed approvals, immutable audit store. |
| Duplicate document upload | Content hash skips duplicate ingestion | Deterministic ingestion behavior | Durable document registry and tenant-level versioning. |
| Process restart | Audit/proposals disappear | Honest POC boundary | Postgres/SQLite audit table and persisted proposal state. |

## Extension Points

- **Evaluation suite:** add a small question-answer gold set that checks citation precision, refusal behavior, and retrieval rank.
- **Durable audit:** move `AuditLog` and proposal decisions into SQLite or Postgres with migrations.
- **Authentication:** require operator identity before uploads or tool decisions.
- **Corpus management:** add delete/reindex/version operations for documents.
- **Provider abstraction:** keep local Ollama as default, but allow a guarded interface for another inference provider.
- **Reranking quality:** add model availability checks and surface model metadata in `/health`.

## What This Architecture Does Not Try To Solve

- Multi-tenant isolation
- Production support queue integration
- Real customer data ingestion
- Autonomous remediation
- Compliance-grade audit retention
- Calibrated confidence scoring

Those omissions are intentional for the proof-of-concept. The design keeps the important safety and retrieval decisions visible while avoiding infrastructure that would distract from the interview demonstration.
