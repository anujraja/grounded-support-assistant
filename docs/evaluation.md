# Evaluation Plan

This repository includes automated checks and a live demo path, but it does not yet claim a fully benchmarked RAG evaluation suite. This document separates what is already verified from what should be added next.

## What is verified today

### Automated checks

Backend tests currently cover:
- chunking with heading preservation and overlap
- duplicate ingestion via content hash
- BM25 retrieval of exact technical tokens
- hybrid score fusion behavior
- citation prompt integrity
- unknown tool rejection
- approval requirement and one-time decision enforcement
- low-confidence escalation
- destructive-request refusal

Command:

```bash
conda run -n grounded-support-assistant pytest -q backend/tests
```

### Build verification

Frontend production build is verified with:

```bash
conda run -n grounded-support-assistant npm --prefix frontend run build
```

### Manual smoke checks already designed into the demo

1. ask a header question and inspect citations
2. ask a version-support question and approve the tool
3. ask an uncovered question and observe low-confidence escalation
4. ask a destructive question and observe refusal

## What a stronger demo should measure

The strongest AI demos do not just "work once." They make quality visible. For this project, the most valuable measurements are retrieval quality, grounding fidelity, safety-gate correctness, and operator experience.

## Recommended scorecard

| Area | Metric | Success criterion | How to measure |
| --- | --- | --- | --- |
| Retrieval exactness | exact-term hit rate | Queries containing version numbers, headers, and config names retrieve the expected chunk in top 3 | Curated test dataset with labeled relevant chunks |
| Retrieval fusion quality | fused rank improvement | Hybrid ranking beats vector-only and BM25-only on mixed paraphrase-plus-keyword queries | Offline comparison on a gold set |
| Citation integrity | unsupported citation rate | 0 unsupported citations rendered in UI | Stream parser tests + runtime logging |
| Answer grounding | claim support ratio | Every factual claim maps to at least one retrieved chunk | Human review rubric or claim-to-source annotation |
| Safety gating | unauthorized tool execution rate | 0 tool executions without stored proposal + approval | Unit/integration tests |
| Refusal behavior | destructive-request refusal rate | 100% of destructive requests refused | Safety regression suite |
| Escalation quality | low-confidence recall | Uncovered queries are flagged low confidence at a high rate | Curated out-of-scope dataset |
| UX latency | first token time | Stable, explainable first token time on local hardware | Client-side timing instrumentation |
| End-to-end latency | answer completion time | Acceptable for live demo, tracked per model size | Client-side timing instrumentation |

## Suggested evaluation datasets

### Retrieval set

Build a small labeled file of 30 to 50 questions:
- 10 exact-term questions
- 10 paraphrased support questions
- 5 mixed questions with both exact tokens and context
- 5 out-of-scope questions
- optional adversarial phrasing for safety checks

Each question should include:
- expected relevant chunk IDs
- expected top-1 or top-3 threshold
- expected confidence class
- whether a tool proposal is expected

### Safety set

Curate requests for:
- destructive actions
- unknown tool names
- extra arguments
- secret-bearing prompts
- tool-like text embedded in ordinary chat

### Demo UX set

Track:
- first token time
- total response time
- number of citations
- whether approval UI appeared when expected
- whether escalation banner appeared when expected

## Practical measurement methods

### 1. Retrieval quality harness

Add an offline script that:
- loads a curated JSONL file of questions and expected chunk IDs
- runs retrieval with vector-only, BM25-only, and fused ranking
- reports recall at `k`

### 2. Citation faithfulness review

For a small benchmark set, review:
- whether citations point to retrieved chunks
- whether the cited excerpt actually supports the sentence
- whether the answer clearly separates verified findings from hypotheses

### 3. Latency instrumentation

Capture:
- request start time
- retrieval completion time
- rerank completion time
- first streamed token
- final token

This is especially useful when comparing Ollama models such as `qwen2.5:3b` versus a larger local model.

## What not to overclaim

Avoid saying:
- "hallucinations are solved"
- "confidence is calibrated"
- "the system is secure"
- "tool use is production-ready"

Prefer saying:
- "citation integrity is enforced at the rendering boundary"
- "tool execution is explicitly gated by the backend"
- "confidence is a transparent heuristic"
- "the demo is instrumented for expansion into a more rigorous evaluation program"

## Portfolio framing

For a portfolio reviewer, the most convincing move is not a giant benchmark table. It is a clean explanation that:
- quality dimensions were identified
- current checks are honest and reproducible
- the next evaluation layers are already designed in a measurable way
