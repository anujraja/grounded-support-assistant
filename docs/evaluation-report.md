# Public evaluation report

## Measured local result

The version-controlled evaluation set contains 5 retrieval-labelled cases and 3 tool-policy/escalation checks. This exact run used the corpus fingerprint `f5cea4568870dec8aa80084dfe34589d95101cccaee1c3027b0c39f2c224896d` and evaluation-set fingerprint `8bf26f21e34ed02d02e2b77184b3a5bd11d768d7239e1c6439c20dd0775acc80`.

| Metric | Semantic | BM25 | Fused |
| --- | ---: | ---: | ---: |
| Hit@1 | 1.000 | 1.000 | 1.000 |
| Hit@3 | 1.000 | 1.000 | 1.000 |

- Retrieval latency: median 18.685 ms across 5 labelled retrievals; maximum 27.49 ms.
- Citation boundary: 10/10 controlled server-filter checks passed; 0 unsupported labels rendered.
- Tool policy and escalation: 3/3 expected outcomes passed. Rejected proposals were exercised without execution where a proposal existed.
- End-to-end local HTTP/SSE latency (reranking disabled, 3 samples): median first token 309.473 ms (max 736.257 ms); median completion 2529.735 ms (max 3272.738 ms). The API process was already running. These are warm-process measurements; a separate clean-server/model-load cold-start benchmark was not run.

## Controlled failure cases and limitations

1. **Destructive request:** the destructive-refusal case is expected to yield no tool proposal and an escalation recommendation. It is a safety-control result, not a claim that the system can remediate production incidents.
2. **Out-of-corpus request:** the low-confidence case is expected to produce an escalation-summary proposal rather than an unsupported answer. It does not measure uncertainty calibration.
3. **Unsupported citation label:** the controlled `[99]` label is replaced before rendering; this is label allowlisting, not claim-level factual entailment.
4. This is a six-case fictional evaluation set, and cold means a new local vector corpus after the embedding model is available. It cannot estimate production traffic performance, clean-machine startup time, or hosted-model behaviour.

## Reproduce

```bash
conda run -n grounded-support-assistant python backend/scripts/run_evaluation.py
conda run -n grounded-support-assistant pytest -q backend/tests
```

To add actual local end-to-end streaming latency, start the demo with Ollama available and run:

```bash
conda run -n grounded-support-assistant python backend/scripts/run_evaluation.py --api-url http://127.0.0.1:8010
```

Machine, model, configuration, corpus, run-mode, and caveat fields are stored beside the figures in `docs/evaluation-results.json`.
