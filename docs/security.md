# Security Review

This document describes the current security posture of the proof-of-concept. It is not a claim of full assurance. The scope here is the implemented local demo in this repository.

Figures below are markdown-graphs ASCII twins (dashed `[ TITLE ]` frames). Live colored graphs live in [anuj-markdown-graphs](https://github.com/anujraja/anuj-markdown-graphs).

## Scope analyzed

- FastAPI endpoints in `backend/app/main.py`
- tool proposal and execution path in `backend/app/tools.py`
- audit handling in `backend/app/audit.py`
- prompt construction and streaming in `backend/app/generation.py`
- ingestion and retrieval paths in `backend/app/ingestion.py` and `backend/app/retrieval.py`

## Security goals for this demo

1. Prevent model autonomy from turning into tool execution.
2. Prevent destructive operations from being available through the demo.
3. Keep citations tied to retrieved evidence instead of model invention.
4. Avoid accidental leakage of secrets into audit output.
5. Fail safely when dependencies are missing or degraded.

```goals
+----------------------- [ GOALS ] -----------------------+
| autonomy     model never executes                       |
| destroy      no such tool exists                        |
| cites        retrieved chunks only                      |
| secrets      redact before audit                        |
| deps         fail closed or skip                        |
+---------------------------------------------------------+
```

## Trust boundaries

| Boundary | Trust level | Notes |
| --- | --- | --- |
| User question | Untrusted | Can contain prompt injection attempts, tool-like text, destructive requests, and secrets. |
| Uploaded file | Untrusted | Constrained to `.md` and `.txt`, UTF-8, 2 MB limit. |
| Model output | Untrusted | The UI only renders streamed text and backend-filtered citations. |
| Tool execution | Trusted only after approval | Backend requires a stored proposal and strict schema validation. |
| Audit log | Trusted local state | In-memory only; redaction exists but persistence and auth are intentionally absent. |

```trust
+----------------------- [ TRUST ] -----------------------+
| surface      trust                                      |
| question     untrusted                                  |
| upload       untrusted                                  |
| model text   untrusted                                  |
| tool run     after yes                                  |
| audit log    local                                      |
+---------------------------------------------------------+
```

## Assets worth protecting

- local machine state
- operator trust in the evidence shown
- audit integrity for the demo session
- any secrets accidentally pasted into a prompt
- clarity around what the model knows versus what the model guesses

## Threat model

### 1. Prompt injection into tool execution

Attack path:
- User writes text that looks like a command or asks the model to call a tool directly.

Current mitigation:
- The model has no execution path.
- Only `ToolRegistry.execute(...)` can run a tool.
- Execution requires a previously stored proposal ID plus explicit approval.
- Proposal arguments are revalidated with `extra="forbid"` schemas before execution.

Residual risk:
- The model can still phrase a misleading proposal reason.
- Approval identity is not authenticated in this demo.

### 2. Destructive-action abuse

Attack path:
- User asks to delete, purge, destroy, disable, rotate, or modify something critical.

Current mitigation:
- `propose_for_question(...)` returns `None` for destructive language.
- `/api/chat` marks destructive questions and emits a refusal instead of a proposal.
- No destructive tool exists in the allowlist.

Residual risk:
- The destructive keyword filter is intentionally simple and should not be treated as a production policy engine.

### 3. Citation spoofing or unsupported evidence claims

Attack path:
- The model emits unsupported citations such as `[9]` even though only two chunks were retrieved.

Current mitigation:
- The backend streams tokens through a citation guard.
- Unsupported citation numbers are replaced instead of rendered as valid evidence.
- If the model emits no valid citation, the backend appends `Supporting evidence: [1]` when retrieved chunks exist.

Residual risk:
- A citation can still support a statement that is overly broad or poorly summarized; retrieval traceability is preserved, but semantic faithfulness is not mathematically guaranteed.

### 4. Secret leakage into audit history

Attack path:
- User pastes a bearer token, API key, DSN, or authorization header into the question or tool input.

Current mitigation:
- `AuditLog` redacts common bearer, token, secret, DSN, and API-key patterns before storing question text or tool results.

Residual risk:
- Pattern-based redaction is not exhaustive.
- The safest production model would combine stronger structured logging rules with auth and retention controls.

### 5. Malicious or malformed upload content

Attack path:
- User uploads binary data, huge content, or malformed text.

Current mitigation:
- Upload endpoint restricts file types to `.md` and `.txt`.
- UTF-8 decode is required.
- Size is capped at 2 MB.
- Files are ingested as plain text; no execution path exists.

Residual risk:
- The corpus can still contain misleading or poor-quality text because document trust is a product-level problem, not a parser-level one.

```inject
+----------------------- [ INJECT ] ----------------------+
| prompt text → no execute                                |
| proposal id → human yes                                 |
| schema check → local fn                                 |
+---------------------------------------------------------+
```

```block
+----------------------- [ BLOCK ] -----------------------+
| + stored proposal       required                        |
| + extra=forbid          schema                          |
| + destructive none      refuse                          |
| + cite number guard     stream                          |
| − model-run tools       blocked                         |
| − delete / purge        blocked                         |
+---------------------------------------------------------+
```

## Security controls mapped to code

| Control | Location | Type |
| --- | --- | --- |
| Strict schema validation for tool args | `backend/app/models.py`, `backend/app/tools.py` | Preventive |
| Stored-proposal requirement before execution | `backend/app/tools.py` | Preventive |
| One-time tool decision enforcement | `backend/app/tools.py` | Preventive |
| Destructive-request refusal | `backend/app/main.py`, `backend/app/tools.py` | Preventive |
| Citation-number guard | `backend/app/main.py` | Preventive |
| Health degradation instead of silent failure | `backend/app/main.py` | Detective + preventive |
| Audit redaction | `backend/app/audit.py` | Detective + preventive |
| Duplicate-ingestion hashing | `backend/app/ingestion.py` | Integrity |

```lock
+------------------------ [ LOCK ] -----------------------+
| control           type                                  |
| strict schema     prevent                               |
| one-shot decide   prevent                               |
| cite guard        prevent                               |
| health degrade    detect                                |
| audit redact      detect                                |
| hash ingest       integrity                             |
+---------------------------------------------------------+
```

## Security gaps that are intentionally left open

These are acceptable for an interview POC, but they are real gaps:

1. No authentication or authorization model.
2. Audit events are in-memory and unauthenticated.
3. No CSRF, session, or identity controls because there is no user account system.
4. No rate limiting or abuse throttling.
5. No content moderation or prompt-injection scoring beyond narrow tool boundaries.
6. No persistent tamper-evident audit store.
7. No tenant isolation because the corpus is single-user and local.

```gaps
+------------------------ [ GAPS ] -----------------------+
|                    poc     prod                         |
| auth               –       ✓                            |
| durable audit      –       ✓                            |
| rate limit         –       ✓                            |
| csrf / session     –       ✓                            |
| tenants            –       ✓                            |
| tool gate          ✓       ✓                            |
+---------------------------------------------------------+
```

## Recommended next steps

### High priority

1. Add authentication and operator identity to tool approval and audit records.
2. Persist audit and proposal state in a durable store.
3. Add request rate limiting and upload abuse controls.

### Medium priority

1. Add structured evaluation for citation faithfulness and unsupported claims.
2. Add stronger secret-scrubbing rules and test cases.
3. Add signed or append-only audit semantics if approval events become compliance-relevant.

### Low priority

1. Add richer prompt-injection analytics for research visibility.
2. Add provenance UI around uploaded versus bundled documents.

```next
+------------------------ [ NEXT ] -----------------------+
| operator identity     =====================  high       |
| durable audit         ====================   high       |
| rate limits           ==================     high       |
| cite faithfulness     ==========             mid        |
| secret scrub tests    ========               mid        |
| injection analytics   ====                   low        |
+---------------------------------------------------------+
```

## Bottom line

For a demo, the most important security property is present: the model cannot directly execute tools, and destructive operations are not available. The largest remaining risks are around missing authentication, non-durable audit storage, and heuristic rather than formal policy enforcement.

```risk
+------------------------ [ RISK ] -----------------------+
| tools      gated     human yes required                 |
| destroy    absent    not on allowlist                   |
| auth       none      interview poc                      |
| audit      memory    lost on restart                    |
+---------------------------------------------------------+
```
