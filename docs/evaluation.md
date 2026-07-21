# Evaluation methodology

This repository now includes a small, repeatable, public evaluation program. It is deliberately a portfolio-scale fictional corpus, not a production benchmark. Current exact results, the machine/configuration record, and rerun commands are in [the public evaluation report](evaluation-report.md) and [the machine-readable result file](evaluation-results.json).

## Version-controlled set and harness

`backend/evaluation/cases.json` contains six representative fictional cases. Each uses expected source keys (`filename#heading`) rather than generated chunk UUIDs, plus expected escalation, tool-proposal, and destructive-refusal outcomes. `backend/scripts/run_evaluation.py` creates a new temporary Chroma corpus from `sample_docs/`, runs semantic/BM25/fused retrieval over the same complete candidate set, and writes both public artifacts.

```bash
conda run -n grounded-support-assistant python backend/scripts/run_evaluation.py
```

The harness records the host platform and Python version, configured local models, vector weight and `TOP_K`, corpus and set SHA-256 fingerprints, chunk count, run mode, sample size, and cold/warm caveats. The current cold label means a fresh temporary vector corpus after the embedding model is available; it does not include download/model-load time.

## What is measured

- Retrieval hit@1 and hit@3 for semantic, BM25, and fused score ordering.
- The citation-label filter used by `/api/chat`, using controlled valid and invalid labels to prove unsupported labels are not rendered.
- Expected destructive refusal, low-confidence escalation, expected proposal type, and denied-proposal no-execution behavior.
- Retrieval timing; end-to-end stream timing is explicitly absent until measured against a reachable local Ollama API.

The citation metric checks server-owned label correctness. It does **not** claim claim-level factual entailment, and no hosted-model comparison is made.

## Automated regression checks

```bash
conda run -n grounded-support-assistant pytest -q backend/tests
conda run -n grounded-support-assistant npm --prefix frontend run build
```

The backend tests cover the evaluation-data contract, score ordering, streamed-citation label filtering, strict schemas, stored-proposal approval, low-confidence escalation, and destructive refusal.

## Future expansion without overclaiming

Increase the set only with newly labelled fictional or permissioned material, add human claim-to-source entailment review, and record latency on each local model/configuration change. Do not describe the heuristic as calibrated, the citation filter as full factual verification, or this portfolio evaluation as production-scale evidence.
