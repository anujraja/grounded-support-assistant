# API and streaming contract

The FastAPI service owns retrieval, citation numbering, confidence, tool policy, and audit state. The browser is a renderer and approval surface; it does not create evidence or execute tools directly.

Figures below are markdown-graphs ASCII twins (dashed `[ TITLE ]` frames). Live colored graphs live in the book at [anuj-markdown-graphs](https://github.com/anujraja/anuj-markdown-graphs).

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Report Chroma, Ollama model, and reranker status |
| `POST` | `/api/ingest` | Ingest the bundled fictional documents |
| `POST` | `/api/upload` | Ingest one UTF-8 `.md` or `.txt` file up to 2 MB |
| `POST` | `/api/chat` | Retrieve evidence and stream a cited answer using SSE |
| `POST` | `/api/tools/propose` | Create an allowlisted proposal from a question and findings |
| `POST` | `/api/tools/execute` | Approve or reject a stored, undecided proposal |
| `GET` | `/api/documents` | List indexed files and chunk counts |
| `GET` | `/api/audit` | Return the local redacted audit trail |

Interactive request and response schemas are available at `/docs` while the backend is running.

```routes
+----------------------- [ ROUTES ] ----------------------+
| verb   path          does                               |
| GET    /health       chroma + ollama                    |
| POST   /ingest       sample docs                        |
| POST   /upload       one utf-8 file                     |
| POST   /chat         sse cited                          |
| POST   /propose      allowlisted                        |
| POST   /execute      approve once                       |
| GET    /documents    indexed files                      |
| GET    /audit        redacted log                       |
+---------------------------------------------------------+
```

The workbench talks HTTP and SSE. Citation numbers, retrieval scores, and tool proposals are assigned on the server before any token is drawn.

```owner
+----------------------- [ OWNER ] -----------------------+
| browser     renderer + approval tab                     |
| fastapi     retrieval, cites, policy                    |
| tools       only after a human yes                      |
| audit       in-memory, redacted                         |
| chroma      chunks + vectors                            |
| ollama      tokens, never tools                         |
+---------------------------------------------------------+
```

## Chat request

```json
{
  "question": "What does the sentry-trace header do?",
  "rerank": null
}
```

`rerank` may be `true`, `false`, or omitted. When omitted, the environment setting controls the optional reranker.

## Server-sent events

`POST /api/chat` returns `text/event-stream`. Events arrive in this order:

1. `meta`: citations, retrieved chunks, score details, confidence, tool proposal, audit ID, and safety flags.
2. `token`: one or more incremental text fragments from Ollama or a deterministic refusal.
3. `error`: a safe error description when retrieval or generation fails.
4. `done`: the terminal event, normally carrying the audit ID.

```events
+----------------------- [ EVENTS ] ----------------------+
| 1  meta: cites, scores, proposal            done        |
| 2  token: ollama fragments                  now         |
| 3  error: safe description                  next        |
| 4  done: audit id                           next        |
+---------------------------------------------------------+
```

```stream
+----------------------- [ STREAM ] ----------------------+
| question → /api/chat                                    |
| meta cites → token stream                               |
| cite guard → done                                       |
+---------------------------------------------------------+
```

Example framing:

```text
event: meta
data: {"citations":[...],"confidence":{...}}

event: token
data: "Verified finding... [1]"

event: done
data: {"audit_id":"..."}
```

The server accepts only citation numbers that correspond to the retrieved chunk list. Unsupported numeric labels emitted by the model are replaced, and a grounded response with evidence receives at least one supporting citation.

## Tool lifecycle

The registry stores an allowlisted proposal. The UI sees the id, arguments, and reason. Execute takes that id and a boolean. Rejected tools never run. Approved tools pass `extra="forbid"` schemas into a deterministic local function. Then audit.

```life
+------------------------ [ LIFE ] -----------------------+
| store proposal → show in ui                             |
| approve → or reject                                     |
| schema check → local function                           |
| audit write → response                                  |
+---------------------------------------------------------+
```

Unknown ids, a second decision, unknown tool names, and surprise arguments all 400.

```deny
+------------------------ [ DENY ] -----------------------+
| + stored proposal     required                          |
|   one decision        required                          |
|   strict schema       forbid extra                      |
| − unknown id          400                               |
| − already decided     400                               |
| − extra args          422                               |
|   decisions           once                              |
+---------------------------------------------------------+
```

A proposal can be decided once. Unknown proposal IDs, repeated decisions, unknown tool names, and unexpected arguments are rejected.

## Error behavior

- Unsupported upload type: `415`
- Upload larger than 2 MB: `413`
- Non-UTF-8 upload: `400`
- Invalid Pydantic request: `422`
- Invalid or already-decided tool proposal: `400`
- Ollama/retrieval failure during chat: streamed `error`, followed by `done`

```codes
+----------------------- [ CODES ] -----------------------+
|                    status                               |
| not .md/.txt       415                                  |
| over 2 mb          413                                  |
| not utf-8          400                                  |
| bad schema         422                                  |
| bad proposal       400                                  |
| ollama fail        sse error                            |
+---------------------------------------------------------+
```
