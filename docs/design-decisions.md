# Design Decisions

This document records the decisions that make Grounded Support Assistant explainable as an interview project. Each decision is intentionally scoped to a local proof-of-concept, not a production support platform.

## ADR 001: Use Explicit Application Code Instead Of LangChain

### Status

Accepted

### Context

The project needs to demonstrate ingestion, hybrid retrieval, citation integrity, tool approval, streaming, and audit behavior in code that can be explained during an interview.

### Options

1. Use LangChain or a similar framework.
   - Pros: faster assembly, many built-in abstractions.
   - Cons: harder to show exact retrieval, citation, and tool-approval boundaries.
2. Write explicit FastAPI modules.
   - Pros: each demo requirement maps to a small readable file.
   - Cons: more local code to maintain.

### Decision

Use explicit application code. The deciding factor is explainability: every important behavior is inspectable without teaching an agent framework first.

### Consequences

- Makes easier: interviews, debugging, safety review, test targeting.
- Makes harder: swapping providers or adding large-scale orchestration features.
- Revisit if: the project expands beyond a demo into a maintained support platform.

## ADR 002: Combine Vector Retrieval With BM25

### Status

Accepted

### Context

Support questions mix natural language with exact technical strings such as `sentry-trace`, `baggage`, SDK versions, configuration keys, and error codes. Pure vector search can miss exact-token intent; pure keyword search can miss paraphrase.

### Options

1. Vector retrieval only.
   - Pros: simple semantic matching.
   - Cons: weaker for exact technical identifiers.
2. BM25 only.
   - Pros: strong exact-term matching.
   - Cons: weaker for paraphrased questions.
3. Hybrid score fusion.
   - Pros: balances paraphrase with exact operational terms.
   - Cons: requires normalization, deduplication, and debug visibility.

### Decision

Use hybrid score fusion: normalize vector and BM25 scores, combine them with a weighted average, deduplicate by chunk id, and expose raw and fused scores.

### Consequences

- Makes easier: diagnosing why a chunk ranked highly.
- Makes harder: tuning score weights across larger corpora.
- Revisit if: evaluation shows either vector or keyword results consistently dominate incorrectly.

## ADR 003: Keep LLM Inference Local Through Ollama

### Status

Accepted

### Context

The demo should run locally, avoid API keys, and show an offline-friendly architecture for support workflows.

### Options

1. Hosted LLM API.
   - Pros: higher model quality and simpler model setup.
   - Cons: requires credentials and network dependency.
2. Local Ollama model.
   - Pros: no hardcoded secrets, local inference, straightforward failure boundary.
   - Cons: model download required and answer quality depends on local hardware/model.

### Decision

Use Ollama with configurable `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

### Consequences

- Makes easier: private local demo, no cloud keys, transparent dependency health.
- Makes harder: consistent answer quality across machines.
- Revisit if: the project becomes a hosted portfolio demo or needs stronger model outputs.

## ADR 004: Let The Server Own Citations

### Status

Accepted

### Context

The UI must never show citations that were not retrieved. The model may emit unsupported bracketed numbers, so citation integrity cannot rely only on prompt instructions.

### Options

1. Let the model generate citations freely.
   - Pros: simplest implementation.
   - Cons: high risk of invented sources.
2. Assign citation ids from retrieved chunks and filter streamed output.
   - Pros: citations map back to real chunks.
   - Cons: additional streaming guard code.

### Decision

The backend assigns citation numbers from retrieved chunks, sends source cards in SSE metadata, filters unsupported citation numbers from streamed tokens, and appends a supporting citation when a grounded answer omits one.

### Consequences

- Makes easier: source integrity and interview explanation.
- Makes harder: preserving arbitrary model formatting.
- Revisit if: a structured generation protocol replaces raw text streaming.

## ADR 005: Treat Reranking As Optional

### Status

Accepted

### Context

Cross-encoder reranking can improve relevance but adds another local model dependency.

### Options

1. Always require reranking.
   - Pros: potentially better ranking quality.
   - Cons: startup and model availability become fragile.
2. Make reranking configurable and graceful.
   - Pros: demo works without the reranker and still shows the extension point.
   - Cons: quality can vary by configuration.

### Decision

Reranking is controlled by environment configuration and gracefully falls back to hybrid ordering if the model is unavailable.

### Consequences

- Makes easier: reliable local setup and Docker/native demos.
- Makes harder: reproducing exact rankings between machines when reranking differs.
- Revisit if: reranking is promoted from demo option to required quality gate.

## ADR 006: Use A Transparent Confidence Heuristic

### Status

Accepted

### Context

The UI needs to communicate answer risk without pretending the demo has calibrated uncertainty.

### Options

1. No confidence signal.
   - Pros: avoids false precision.
   - Cons: loses a key support-safety behavior.
2. Calibrated model confidence.
   - Pros: more rigorous if trained/evaluated.
   - Cons: out of scope for a small local POC.
3. Explainable heuristic.
   - Pros: understandable and testable.
   - Cons: not statistically authoritative.

### Decision

Use a proof-of-concept heuristic based on strongest retrieval score, vector/BM25 agreement, supporting chunk count, and absent-information signals.

### Consequences

- Makes easier: low-confidence escalation and testable safety behavior.
- Makes harder: interpreting the numeric score as real probability.
- Revisit if: a labeled evaluation dataset becomes available.

## ADR 007: Require Human Approval For Tools

### Status

Accepted

### Context

The model must not directly execute tools. Tool calls should be proposed, inspected, approved or rejected, and audited.

### Options

1. Let the model call tools directly.
   - Pros: more autonomous assistant behavior.
   - Cons: weak safety boundary and poor interview story for destructive requests.
2. Server-side allowlist with explicit approval.
   - Pros: deterministic execution and clear human gate.
   - Cons: less autonomous and requires UI approval flow.

### Decision

Use exactly three deterministic local tools, strict Pydantic schemas, stored proposals, and one-time explicit approval decisions.

### Consequences

- Makes easier: safety explanation, destructive-action refusal, auditability.
- Makes harder: rapid multi-step automation.
- Revisit if: authenticated operators, RBAC, and durable audit are added.

## ADR 008: Keep Audit State In Memory For The POC

### Status

Accepted

### Context

The demo needs to show audit concepts without introducing migrations, databases, retention policies, or auth.

### Options

1. In-memory audit state.
   - Pros: simple, readable, enough for a local interview run.
   - Cons: lost on restart, not multi-user, not compliance-grade.
2. SQLite/Postgres audit store.
   - Pros: durable and closer to production.
   - Cons: extra setup and operational surface.

### Decision

Use an in-memory audit log and document it as a deliberate POC boundary.

### Consequences

- Makes easier: setup and code explanation.
- Makes harder: replaying decisions after restart.
- Revisit if: the demo needs persistent history, multiple users, or deployment.

## ADR 009: Keep Sample Support Content Fictional

### Status

Accepted

### Context

The project imitates observability support workflows but must not claim to be official vendor documentation or include real customer data.

### Options

1. Use copied real docs.
   - Pros: more realistic language.
   - Cons: attribution, freshness, and misrepresentation risk.
2. Use fictional support docs with explicit disclaimer.
   - Pros: safe for portfolio use and clear demonstration boundary.
   - Cons: less realistic coverage breadth.

### Decision

Use fictional sample documents with repeated disclaimers.

### Consequences

- Makes easier: private repo sharing and interview demo safety.
- Makes harder: benchmarking against real support corpora.
- Revisit if: real licensed documentation and clear attribution are available.
