# Engineering case study

## Problem

A useful support assistant must do more than produce plausible text. It needs to retrieve exact technical details, show where claims came from, admit uncertainty, and keep operational actions outside the model's direct control.

This project explores that problem in a form that can be understood and demonstrated in minutes.

## Constraints

- Local inference and embeddings; no hosted AI dependency or API secret.
- A small codebase that can be explained during an interview.
- Exact version strings, header names, and configuration keys must remain searchable.
- Citations must refer only to retrieved evidence.
- Tools must be deterministic, allowlisted, schema-validated, and human-approved.
- Out-of-corpus and destructive requests must fail safely.
- Tests must not download models or call Ollama.

## Solution

### Evidence pipeline

Markdown files are split into overlapping, heading-aware chunks. A content hash prevents duplicate ingestion. Each chunk keeps its filename, heading, identifier, and timestamp so evidence remains traceable.

The retriever runs two complementary searches:

- ChromaDB vector similarity handles paraphrases and conceptual matches.
- BM25 preserves precision for tokens such as `sentry-trace`, `tracePropagationTargets`, and `8.25.0`.

Each score family is normalized independently, fused with an explicit weighting, and deduplicated by chunk ID. An optional cross-encoder can rerank the candidates without becoming a hard dependency.

### Grounded generation

FastAPI constructs a numbered evidence context and streams the Ollama response using server-sent events. Citation labels are validated by the server rather than trusted blindly from the model. The UI displays the answer and the same retrieved source objects side by side.

### Bounded agency

The application exposes exactly three deterministic local tools. The model-facing policy can propose a tool, but only a stored proposal ID can reach the execution endpoint. The user must approve or reject it, argument schemas forbid extra fields, and the proposal becomes single-use after the decision.

### Explainable uncertainty

Confidence combines the best fused score, agreement between retrieval methods, the number of supporting chunks, and out-of-corpus language. The UI explicitly labels this as a POC heuristic and recommends a human engineer when it is low.

## Engineering outcomes

The verified local demonstration includes:

- 17 chunks indexed from five fictional documents;
- progressive Ollama streaming with source cards;
- independently visible vector, BM25, and fused scores;
- a successful approval-gated tool execution;
- deterministic refusal of unknown and destructive actions;
- low-confidence escalation;
- nine backend behavior tests and a successful frontend production build.

These are demonstration results from the bundled corpus, not production quality or performance claims.

## Deliberate tradeoffs

- Plain application modules were chosen over an agent framework to keep control flow inspectable.
- BM25 is rebuilt from the small local corpus; a larger system would use a dedicated searchable index.
- Audit and proposal state are in memory to keep setup small; production would use durable, append-only records.
- Confidence is a transparent ruleset rather than an unvalidated probability.
- The browser is intentionally not trusted with citation creation or tool authority.

## Production roadmap

1. Add authentication, authorization, tenant boundaries, and rate limiting.
2. Move proposals and audit events to durable append-only storage.
3. Build a labeled retrieval and answer-quality evaluation set.
4. Add claim-level citation entailment checks and calibrated abstention.
5. Add tracing, latency budgets, model/runtime telemetry, and structured error reporting.
6. Separate read-only diagnostics from higher-risk actions with scoped approval policies.
7. Add deployment hardening, dependency scanning, and signed release artifacts.
