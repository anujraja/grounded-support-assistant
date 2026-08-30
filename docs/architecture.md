# Architecture

Grounded Support Assistant is a local proof-of-concept for evidence-first technical support. It is intentionally small: one FastAPI backend, one React workbench, local Chroma persistence, local embedding/reranking models, and Ollama for generation.

The architecture is optimized for interview clarity. Retrieval, citations, confidence, tool approval, and audit events are server-owned so the demo can explain where each grounded answer came from and why a risky action was not executed automatically.

Figures below are markdown-graphs ASCII twins (dashed `[ TITLE ]` frames). Live colored graphs live in [anuj-markdown-graphs](https://github.com/anujraja/anuj-markdown-graphs).

## System Context

The operator asks questions and signs tools in the React evidence workbench. The browser talks HTTP and SSE to FastAPI. Docs, vectors, embeddings, optional reranker, and Ollama all sit next to the API.

```context
+---------------------- [ CONTEXT ] ----------------------+
| operator → react workbench                              |
| fastapi → chromadb                                      |
| ollama → audit log                                      |
+---------------------------------------------------------+
```

Frontend is a three-pane workbench. Backend modules stay small on purpose.

```stack
+----------------------- [ STACK ] -----------------------+
| grounded support                                        |
| ├─ frontend/                                            |
| │  ├─ App.tsx                 three panes               |
| │  ├─ api.ts                  sse parser                |
| │  └─ index.css               plain css                 |
| └─ backend/app                                          |
|    ├─ main.py                 sse + cites               |
|    ├─ ingestion.py            chunk + hash              |
|    ├─ retrieval.py            vector + bm25             |
|    ├─ generation.py           ollama stream             |
|    ├─ tools.py                allowlist                 |
|    └─ audit.py                in-memory                 |
+---------------------------------------------------------+
```

## Data Ownership

Chunks, embeddings, citation numbers, tool proposals, and the audit trail are not invented in the browser. Demo content is fictional. Uploaded text is chunked immediately. The BM25 corpus is rebuilt in memory from stored chunks so error codes and version pins stay retrievable.

| Data | Owner | Stored in | Notes |
| --- | --- | --- | --- |
| Source documents | `sample_docs/` and upload endpoint | Filesystem for samples; uploaded text is immediately chunked | Demo content is fictional and must stay free of real customer data. |
| Chunks and metadata | `DocumentStore` | Chroma collection `support_chunks` | Stores chunk text, filename, heading, chunk id, timestamp, and content hash. |
| Embeddings | `DocumentStore` | Chroma collection | Generated locally through Sentence Transformers. |
| BM25 corpus | `HybridRetriever` | Rebuilt in memory from stored chunks | Keeps exact technical terms, versions, headers, and error codes retrievable. |
| Citations | `main.py` | Response metadata only | Citation numbers are assigned from retrieved chunks and filtered during generation. |
| Tool proposals | `ToolRegistry` | In-memory process state | A proposal must exist before execution and can be decided only once. |
| Audit trail | `AuditLog` | In-memory process state | Redacted local demo log, not durable compliance storage. |

```data
+------------------------ [ DATA ] -----------------------+
| data             owner              stored              |
| documents        sample_docs        files               |
| chunks           DocumentStore      chroma              |
| embeddings       DocumentStore      chroma              |
| bm25 corpus      HybridRetriever    memory              |
| citations        main.py            response            |
| tool proposals   ToolRegistry       memory              |
| audit trail      AuditLog           memory              |
+---------------------------------------------------------+
```

## Critical Flow: Ingestion

Ingest hits `/api/ingest` or `/api/upload`. A SHA-256 content hash skips duplicates. Chunks follow headings and overlap. Sentence Transformers embed locally. Chroma keeps ids, text, metadata, and vectors. The UI only needs counts back. No model is called on this path.

```ingest
+----------------------- [ INGEST ] ----------------------+
| upload markdown → hash skip                             |
| heading chunks → local embed                            |
| chroma persist → ingest counts                          |
+---------------------------------------------------------+
```

```steps
+----------------------- [ STEPS ] -----------------------+
| 1  click ingest samples or upload           done        |
| 2  hash duplicate check                     done        |
| 3  heading-aware overlapping chunks         done        |
| 4  embed locally, write chroma              now         |
| 5  return ingested / skipped counts         next        |
+---------------------------------------------------------+
```

## Critical Flow: Grounded Chat

A question goes to `/api/chat`. Hybrid retrieval (vector + BM25) returns deduped chunks and debug scores. The cross-encoder reranks in a worker thread and fails open. Confidence is an explainable heuristic, then a tool may be proposed, then Ollama streams against retrieved evidence only.

Citation numbers the model invents are stripped before render. The meta SSE event carries citations, retrieval, confidence, and any tool proposal before tokens start.

```chat
+------------------------ [ CHAT ] -----------------------+
| question → hybrid retrieve                              |
| optional rerank → confidence                            |
| tool propose → ollama stream                            |
+---------------------------------------------------------+
```

```stream
+----------------------- [ STREAM ] ----------------------+
| question    ████████████████████            1     |
| retrieve    ████████                          n     |
| rerank      █████                             k     |
| tokens      ███                               sse   |
| cited       ██                                ok    |
+---------------------------------------------------------+
```

## Critical Flow: Tool Approval

The approval tab shows the proposed tool, args, and reason. `/api/tools/execute` takes a proposal id and a boolean. The registry validates the stored proposal and refuses a second decision. Rejected tools never run. Approved tools pass a strict Pydantic schema into a deterministic local function.

The allowlist is the complete execution authority. Unknown and destructive actions never reach the operator. Every decision is audited, including rejections.

```gate
+------------------------ [ GATE ] -----------------------+
| proposed tool → approval                                |
| approve → or reject                                     |
| schema check → local function                           |
+---------------------------------------------------------+
```

```allow
+----------------------- [ ALLOW ] -----------------------+
| + version_check     schema                              |
|   lookup_config     schema                              |
|   search_docs       schema                              |
| − delete_project    blocked                             |
| − network call      blocked                             |
|   executable        3                                   |
+---------------------------------------------------------+
```

## Module Contracts

`main.py` orchestrates endpoints, streaming, citation assignment, and audit writes. It does not embed retrieval or tool logic. Ingestion does not call Ollama. Retrieval does not invent citations. Generation does not execute tools. Confidence does not claim calibration.

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

```duty
+------------------------ [ DUTY ] -----------------------+
| module          does              must not              |
| main.py         sse + cites       no retrieval          |
| ingestion.py    chunk + hash      no ollama             |
| retrieval.py    vector + bm25     no cites              |
| reranking.py    optional model    not required          |
| generation.py   grounded stream   no tools              |
| confidence.py   heuristic         not calibrated        |
| tools.py        allowlist         no network            |
| audit.py        redact events     no secrets            |
+---------------------------------------------------------+
```

## Failure Modes

Ollama down: health is degraded and chat says so instead of inventing guidance. Reranker down: hybrid retrieval continues and exposes `reranker_error`. Empty hits: low confidence and a human. Duplicate upload: hash skip. Process restart: audit and proposals disappear — that boundary is part of the demo.

| Failure | Current behavior | Portfolio talking point | Production hardening |
| --- | --- | --- | --- |
| Ollama unavailable | `/health` reports degraded; chat streams an explicit unavailable message | The app fails closed instead of inventing support guidance | Queue/retry policy, model readiness probes, fallback model strategy. |
| Reranker unavailable | Hybrid retrieval continues and exposes `reranker_error` | Optional quality layer is not a single point of failure | Model cache management and versioned evaluation. |
| Empty or weak retrieval | Low confidence and escalation recommendation | The assistant admits insufficient evidence | Calibrated evaluation set and support-ticket routing integration. |
| Unknown/destructive tool | Rejected by allowlist or no proposal generated | The model never receives execution authority | Auth, RBAC, signed approvals, immutable audit store. |
| Duplicate document upload | Content hash skips duplicate ingestion | Deterministic ingestion behavior | Durable document registry and tenant-level versioning. |
| Process restart | Audit/proposals disappear | Honest POC boundary | Postgres/SQLite audit table and persisted proposal state. |

```fail
+------------------------ [ FAIL ] -----------------------+
|                    now                 later            |
| ollama down        fail closed         retry + probe    |
| reranker miss      skip, expose error  cached model     |
| weak retrieval     escalate            ticket route     |
| bad tool           reject              rbac + signed    |
| dup upload         hash skip           tenant versions  |
| process restart    lost audit          postgres         |
+---------------------------------------------------------+
```

## Extension Points

- **Evaluation suite:** add a small question-answer gold set that checks citation precision, refusal behavior, and retrieval rank.
- **Durable audit:** move `AuditLog` and proposal decisions into SQLite or Postgres with migrations.
- **Authentication:** require operator identity before uploads or tool decisions.
- **Corpus management:** add delete/reindex/version operations for documents.
- **Provider abstraction:** keep local Ollama as default, but allow a guarded interface for another inference provider.
- **Reranking quality:** add model availability checks and surface model metadata in `/health`.

## What This Architecture Does Not Try To Solve

Those omissions are intentional for the proof-of-concept. The design keeps the important safety and retrieval decisions visible while avoiding infrastructure that would distract from the interview demonstration.

```omit
+------------------------ [ OMIT ] -----------------------+
|   local ollama default       in                         |
|   human tool gate            in                         |
|   server-owned cites         in                         |
| − multi-tenant isolation     out                        |
| − support queue              out                        |
| − real customer data         out                        |
| − autonomous remediation     out                        |
| − compliance audit store     out                        |
+---------------------------------------------------------+
```
