# Evaluation truth handoff

This file lists only facts verified by the checked-in local evaluation artifacts. Source of record: `docs/evaluation-results.json` and `docs/evaluation-report.md`.

## Resume-safe facts

- Implemented a version-controlled, six-case fictional evaluation set covering hybrid retrieval, citation-label filtering, tool-policy outcomes, and low-confidence escalation.
- On the bundled five-file, 17-chunk fictional corpus (SHA-256 `f5cea4568870dec8aa80084dfe34589d95101cccaee1c3027b0c39f2c224896d`), semantic, BM25, and fused retrieval each recorded Hit@1 = 1.000 and Hit@3 = 1.000 across five labelled retrieval cases.
- The server citation-label boundary passed 10/10 controlled checks and rendered 0 unsupported labels; this verifies label allowlisting, not claim-level entailment.
- Tool-policy and escalation checks passed 3/3 expected outcomes, including denied-proposal no-execution behaviour, destructive-request refusal, and low-confidence escalation.
- On macOS 26.5.1 / Python 3.12.13 with `all-MiniLM-L6-v2`, local `qwen2.5:3b`, reranking disabled, and three warm FastAPI/Ollama HTTP/SSE samples, median first-token latency was 309.473 ms and median completion latency was 2529.735 ms.

## Must keep the qualifiers

- These are local, warm-process measurements on a deliberately small fictional corpus. They are not production-load, clean-start, hosted-model, or user-traffic benchmarks.
- The confidence heuristic is not calibrated, and citation filtering is not full factual-verification or answer-quality evaluation.
- Do not claim enterprise deployment, external users, model training, production scale, or hosted-model comparisons from this work.

## Candidate resume wording

> Built a local RAG support workbench with version-controlled retrieval, citation-boundary, latency, and tool-safety evaluations; on a six-case fictional corpus, recorded traceable hybrid retrieval and warm local streaming measurements with explicit scope limits.
