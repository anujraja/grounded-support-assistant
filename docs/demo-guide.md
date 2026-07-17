# Demo Guide

This is the operator runbook for showing the project in an interview or portfolio walkthrough.

## Goal of the demo

Show that the application is not just "chat with docs." The demo should make four things obvious:

1. retrieval is inspectable
2. answers are grounded with citations
3. tools are approval-gated and deterministic
4. low confidence leads to escalation instead of bluffing

## Before the interview

### Startup

```bash
cd "/Users/macbookpro/Developer/Grounded Support Assistant"
./run-demo.sh
```

Expected endpoints:
- UI: `http://localhost:5173`
- API: `http://localhost:8010`

### Quick readiness check

Confirm:
- health pill shows system ready or at least identifies the degraded dependency clearly
- left sidebar lists sample documents
- right panel tabs switch cleanly
- sample questions are loaded

## Recommended three-minute script

### 1. Open with the architecture in one sentence

Use:

> This is a local support assistant that combines vector retrieval and BM25, streams an Ollama answer with citations, and keeps tool execution behind explicit human approval.

### 2. Show grounded retrieval

Ask:

> What does the `sentry-trace` header do?

What to point at:
- streamed answer in the center panel
- citation pills in the answer
- source cards in the right pane
- retrieval debug showing vector, BM25, and fused ranking

What the interviewer should notice:
- exact technical language is traceable to retrieved chunks
- the demo exposes why a chunk ranked highly

### 3. Show deterministic tool approval

Ask:

> Is JavaScript SDK version 99.0 supported?

What to point at:
- proposed tool in the approval tab
- explicit arguments and reason
- manual approve button
- deterministic result after approval
- audit entry showing the full path

What the interviewer should notice:
- the model did not execute anything on its own
- the tool is narrow, local, and explainable

### 4. Show uncertainty handling

Ask:

> Diagnose a problem that is not covered by the provided documents.

What to point at:
- low-confidence badge
- escalation banner
- optional escalation-summary tool proposal

What the interviewer should notice:
- the system does not bluff when the corpus is weak

### 5. Show destructive refusal

Ask:

> Delete the customer’s production project.

What to point at:
- refusal in the answer stream
- no destructive tool proposal
- audit entry still recording the request and refusal path

What the interviewer should notice:
- the system has hard capability boundaries, not just polite wording

## Expected visual checkpoints

### Left pane

- document count visible
- upload and ingest actions obvious
- sample prompts easy to trigger

### Center pane

- streamed answer feels live
- confidence badge stays visible
- inline citations are clickable
- the input area remains visible without scrolling gymnastics

### Right pane

- Sources tab shows excerpt plus scores
- Retrieval tab shows fused ranking details
- Approval tab shows proposed tool, arguments, and reason
- Audit tab shows the operator trail

## Fallback plan if something goes wrong live

### Ollama is not running

What happens:
- health endpoint reports degraded
- chat explains that Ollama is unavailable

What to say:

> The model dependency is intentionally explicit. The health check reports the failure instead of hiding it or fabricating an answer.

### Reranker model is unavailable

What happens:
- hybrid retrieval still works
- reranker error is surfaced in metadata

What to say:

> Reranking is optional by design. The system degrades to the fused hybrid ranker instead of failing the request.

### A tool proposal is rejected

What to say:

> Rejection is part of the demo. The point is to show that approval is a real control point, not a cosmetic prompt.

## Troubleshooting

### Health says the model is unavailable

Run:

```bash
ollama serve
ollama pull qwen2.5:3b
```

### Frontend does not connect to the API

Check:
- backend is on port `8010`
- Vite is on `5173`
- `.env` did not override the API base incorrectly

### Documents are missing

Run:

```bash
cd backend
conda run -n grounded-support-assistant python -m app.ingestion --samples
cd ..
```

### Tests before a portfolio handoff

Run:

```bash
conda run -n grounded-support-assistant pytest -q backend/tests
conda run -n grounded-support-assistant npm --prefix frontend run build
```

## How to answer “why is this a strong demo?”

Use:

> The demo makes the risky parts visible. Retrieval is inspectable, citations are traceable, tool execution is gated by the backend, and low-confidence paths escalate instead of pretending certainty.
