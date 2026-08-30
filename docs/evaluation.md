# Evaluation methodology

This repository now includes a small, repeatable, public evaluation program. It is deliberately a portfolio-scale fictional corpus, not a production benchmark. Current exact results, the machine/configuration record, and rerun commands are in [the public evaluation report](evaluation-report.md) and [the machine-readable result file](evaluation-results.json).

Figures below are markdown-graphs ASCII twins (dashed `[ TITLE ]` frames). Live colored graphs live in [anuj-markdown-graphs](https://github.com/anujraja/anuj-markdown-graphs).

## Version-controlled set and harness

`backend/evaluation/cases.json` contains six representative fictional cases. Each uses expected source keys (`filename#heading`) rather than generated chunk UUIDs, plus expected escalation, tool-proposal, and destructive-refusal outcomes. `backend/scripts/run_evaluation.py` creates a new temporary Chroma corpus from `sample_docs/`, runs semantic/BM25/fused retrieval over the same complete candidate set, and writes both public artifacts.

```bash
conda run -n grounded-support-assistant python backend/scripts/run_evaluation.py
```

The harness records the host platform and Python version, configured local models, vector weight and `TOP_K`, corpus and set SHA-256 fingerprints, chunk count, run mode, sample size, and cold/warm caveats. The current cold label means a fresh temporary vector corpus after the embedding model is available; it does not include download/model-load time.

```set
+------------------------ [ SET ] ------------------------+
| 5     retrieval     labelled retrieval                  |
| 3     policy        tool + escalate                     |
| 17    chunks        fictional markdown                  |
| 5     files         portfolio scale                     |
+---------------------------------------------------------+
```

```corpus
+----------------------- [ CORPUS ] ----------------------+
| embed        all-minilm-l6-v2                           |
| generate     qwen2.5:3b                                 |
| rerank       off this run                               |
| vector wt    0.55                                       |
| top k        6                                          |
| mode         cold temp corpus                           |
+---------------------------------------------------------+
```

## What is measured

- Retrieval hit@1 and hit@3 for semantic, BM25, and fused score ordering.
- The citation-label filter used by `/api/chat`, using controlled valid and invalid labels to prove unsupported labels are not rendered.
- Expected destructive refusal, low-confidence escalation, expected proposal type, and denied-proposal no-execution behavior.
- Retrieval timing; end-to-end stream timing is explicitly absent until measured against a reachable local Ollama API.

The citation metric checks server-owned label correctness. It does **not** claim claim-level factual entailment, and no hosted-model comparison is made.

```hits
+------------------------ [ HITS ] -----------------------+
|              @1        @3                               |
| semantic     1.000     1.000                            |
| bm25         1.000     1.000                            |
| fused        1.000     1.000                            |
+---------------------------------------------------------+
```

```retrieve
+---------------------- [ RETRIEVE ] ---------------------+
| █▇▅▄▄                                                   |
| ms per labelled retrieval · median 18.7 · max 27.5      |
+---------------------------------------------------------+
```

```pass
+------------------------ [ PASS ] -----------------------+
| cite filter 10/10     █████                             |
|                       █████                             |
| policy 3/3            ███                               |
+---------------------------------------------------------+
```

```scope
+----------------------- [ SCOPE ] -----------------------+
| + label allowlist         measured                      |
| + destructive none        measured                      |
| + escalate if empty       measured                      |
| − claim entailment        not claimed                   |
| − hosted compare          not claimed                   |
| − production scale        not claimed                   |
+---------------------------------------------------------+
```

```token
+----------------------- [ TOKEN ] -----------------------+
| 309 ms                                                  |
| median first token                                      |
| warm process, n=3                                       |
+---------------------------------------------------------+
```

## Automated regression checks

```bash
conda run -n grounded-support-assistant pytest -q backend/tests
conda run -n grounded-support-assistant npm --prefix frontend run build
```

The backend tests cover the evaluation-data contract, score ordering, streamed-citation label filtering, strict schemas, stored-proposal approval, low-confidence escalation, and destructive refusal.

## Future expansion without overclaiming

Increase the set only with newly labelled fictional or permissioned material, add human claim-to-source entailment review, and record latency on each local model/configuration change. Do not describe the heuristic as calibrated, the citation filter as full factual verification, or this portfolio evaluation as production-scale evidence.
