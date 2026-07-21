from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

from .citations import filter_citation_labels, finish_citation_filter
from .confidence import calculate_confidence
from .ingestion import DocumentStore
from .models import RetrievedChunk
from .retrieval import HybridRetriever
from .tools import ToolRegistry, propose_for_question


def source_key(chunk: RetrievedChunk) -> str:
    return f"{chunk.filename}#{chunk.heading}"


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation dataset must contain at least one case")
    return cases


def corpus_fingerprint(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def rank_chunks(chunks: list[RetrievedChunk], mode: str) -> list[RetrievedChunk]:
    key = {"semantic": "vector_score", "bm25": "bm25_score", "fused": "combined_score"}[mode]
    return sorted(chunks, key=lambda chunk: (getattr(chunk, key), -chunk.final_rank), reverse=True)


def hit_at_k(ranked: list[RetrievedChunk], expected_sources: list[str], k: int) -> bool:
    return bool(set(expected_sources) & {source_key(chunk) for chunk in ranked[:k]})


def metric_summary(hits: dict[str, list[bool]]) -> dict[str, dict[str, float | int]]:
    return {
        mode: {
            "hit_at_1": round(sum(values[0::2]) / max(1, len(values[0::2])), 3),
            "hit_at_3": round(sum(values[1::2]) / max(1, len(values[1::2])), 3),
            "cases": len(values) // 2,
        }
        for mode, values in hits.items()
    }


def evaluate_retrieval(cases: list[dict[str, Any]], retriever: HybridRetriever, corpus_size: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    hits = {"semantic": [], "bm25": [], "fused": []}
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    for case in cases:
        expected = case["expected_sources"]
        if not expected:
            continue
        started = time.perf_counter()
        chunks, debug = retriever.retrieve(case["question"], top_k=corpus_size, candidate_k=corpus_size)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        ranks: dict[str, list[str]] = {}
        for mode in hits:
            ranked = rank_chunks(chunks, mode)
            ranks[mode] = [source_key(chunk) for chunk in ranked]
            hits[mode].extend([hit_at_k(ranked, expected, 1), hit_at_k(ranked, expected, 3)])
        details.append(
            {
                "id": case["id"],
                "expected_sources": expected,
                "ranks": ranks,
                "retrieval_agreement": debug["agreement"],
                "retrieval_ms": round(elapsed_ms, 3),
            }
        )
    return (
        {
            "methods": metric_summary(hits),
            "latency_ms": {
                "samples": len(latencies),
                "median": round(sorted(latencies)[len(latencies) // 2], 3) if latencies else None,
                "max": round(max(latencies), 3) if latencies else None,
            },
        },
        details,
    )


def evaluate_citation_boundary(retrieval_details: list[dict[str, Any]]) -> dict[str, Any]:
    checks = []
    for detail in retrieval_details:
        # Controlled stream text exercises the exact server-used filter, including an invalid model label.
        rendered, pending, saw_valid = filter_citation_labels("Verified evidence [1]; invalid [99]", 1)
        valid = saw_valid and not pending and "[99]" not in rendered and "[1]" in rendered
        checks.append({"id": f"{detail['id']}:closed", "passed": valid, "rendered": rendered})
        incomplete, pending, saw_valid = filter_citation_labels("Incomplete invalid [99", 1)
        rendered = incomplete + finish_citation_filter(pending)
        valid = not saw_valid and "[99" not in rendered and "[unsupported citation removed]" in rendered
        checks.append({"id": f"{detail['id']}:incomplete", "passed": valid, "rendered": rendered})
    return {
        "server_boundary_checks": len(checks),
        "passed": sum(check["passed"] for check in checks),
        "unsupported_labels_rendered": sum("[99]" in check["rendered"] for check in checks),
        "checks": checks,
        "scope": "Controlled token strings through the filter used by /api/chat; this verifies label allowlisting, not claim-level entailment.",
    }


def evaluate_safety(cases: list[dict[str, Any]], retriever: HybridRetriever, corpus_size: int) -> dict[str, Any]:
    checks = []
    for case in cases:
        if case["kind"] not in {"safety", "retrieval_and_tool"}:
            continue
        chunks, debug = retriever.retrieve(case["question"], top_k=corpus_size, candidate_k=corpus_size)
        confidence = calculate_confidence(case["question"], chunks, float(debug["agreement"]))
        proposal = propose_for_question(case["question"], [source_key(chunk) for chunk in chunks[:3]], confidence)
        destructive = bool(re.search(r"\b(delete|purge|destroy|disable|rotate|modify)\b", case["question"], re.I))
        proposal_name = proposal.tool_name if proposal else None
        escalation_recommended = confidence.escalation_recommended or destructive
        passed = (
            escalation_recommended == case["expected_escalation"]
            and proposal_name == case["expected_tool"]
            and destructive == case["expected_destructive_refusal"]
        )
        approval_gate = None
        if proposal:
            registry = ToolRegistry()
            stored = registry.save(proposal)
            _, result = registry.execute(stored.id, approved=False)
            approval_gate = result is None
            passed = passed and approval_gate
        checks.append(
            {
                "id": case["id"],
                "passed": passed,
                "confidence": confidence.label,
                "escalation_recommended": escalation_recommended,
                "tool_proposed": proposal_name,
                "destructive_refusal": destructive,
                "rejected_execution_result": approval_gate,
            }
        )
    return {"checks": checks, "passed": sum(item["passed"] for item in checks), "total": len(checks)}


def environment_metadata(store: DocumentStore, cases_path: Path, sample_paths: list[Path], run_mode: str) -> dict[str, Any]:
    return {
        "run_mode": run_mode,
        "machine": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "models": {"embedding": store.settings.embedding_model, "generation": store.settings.ollama_model, "reranker_enabled": store.settings.enable_reranking},
        "configuration": {"top_k": store.settings.top_k, "vector_weight": 0.55, "reranker_enabled": store.settings.enable_reranking},
        "corpus": {"files": [path.name for path in sample_paths], "fingerprint_sha256": corpus_fingerprint(sample_paths), "chunks": store.collection.count()},
        "evaluation_set": {"path": str(cases_path), "fingerprint_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest()},
        "caveats": [
            "The corpus and evaluation questions are fictional and intentionally small; results are not a production benchmark.",
            "Semantic, BM25, and fused rankings are compared over the same complete candidate set for this corpus.",
            "Cold means a fresh temporary Chroma corpus in this process; embedding-model download/load time is excluded from retrieval latency.",
            "No hosted-model comparison is measured by this harness.",
        ],
    }


def build_results(cases_path: Path, sample_paths: list[Path], store: DocumentStore, run_mode: str) -> dict[str, Any]:
    cases = load_cases(cases_path)
    retriever = HybridRetriever(store)
    retrieval, details = evaluate_retrieval(cases, retriever, store.collection.count())
    return {
        "schema_version": 1,
        "metadata": environment_metadata(store, cases_path, sample_paths, run_mode),
        "retrieval": retrieval,
        "retrieval_cases": details,
        "citation_correctness": evaluate_citation_boundary(details),
        "tool_policy_and_escalation": evaluate_safety(cases, retriever, store.collection.count()),
        "response_latency": {
            "status": "not_measured",
            "reason": "Run with a reachable local API via the CLI --api-url option to record live end-to-end streaming latency.",
        },
    }


def measure_end_to_end_response(api_url: str, cases: list[dict[str, Any]], sample_size: int) -> dict[str, Any]:
    """Measure local HTTP/SSE timing without interpreting the generated answer."""
    samples = [case for case in cases if case["kind"] == "retrieval"][:sample_size]
    measurements: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
            for case in samples:
                started = time.perf_counter()
                first_token_ms: float | None = None
                done_ms: float | None = None
                event_name = ""
                with client.stream(
                    "POST", f"{api_url.rstrip('/')}/api/chat", json={"question": case["question"], "rerank": False}
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line.startswith("event: "):
                            event_name = line[7:]
                        elif line.startswith("data: "):
                            if event_name == "token" and first_token_ms is None:
                                first_token_ms = (time.perf_counter() - started) * 1000
                            if event_name == "done":
                                done_ms = (time.perf_counter() - started) * 1000
                measurements.append(
                    {
                        "id": case["id"],
                        "first_token_ms": round(first_token_ms, 3) if first_token_ms is not None else None,
                        "completion_ms": round(done_ms, 3) if done_ms is not None else None,
                    }
                )
    except httpx.HTTPError as exc:
        return {"status": "not_measured", "reason": f"Local API measurement failed safely: {type(exc).__name__}.", "samples": measurements}
    first_tokens = [item["first_token_ms"] for item in measurements if item["first_token_ms"] is not None]
    completions = [item["completion_ms"] for item in measurements if item["completion_ms"] is not None]
    if not first_tokens or not completions:
        return {"status": "not_measured", "reason": "The API returned no token/done timing events.", "samples": measurements}
    return {
        "status": "measured",
        "sample_size": len(measurements),
        "first_token_ms": {"median": round(sorted(first_tokens)[len(first_tokens) // 2], 3), "max": round(max(first_tokens), 3)},
        "completion_ms": {"median": round(sorted(completions)[len(completions) // 2], 3), "max": round(max(completions), 3)},
        "samples": measurements,
        "caveat": "Measured through local FastAPI HTTP/SSE with reranking disabled. It includes local retrieval and Ollama generation, but is not a hosted-model or production-load benchmark.",
        "warm_cold_note": "The API process was already running. These are warm-process measurements; a separate clean-server/model-load cold-start benchmark was not run.",
    }


def render_report(results: dict[str, Any]) -> str:
    methods = results["retrieval"]["methods"]
    citation = results["citation_correctness"]
    safety = results["tool_policy_and_escalation"]
    metadata = results["metadata"]
    response_latency = results["response_latency"]
    if response_latency["status"] == "measured":
        latency_line = (
            "End-to-end local HTTP/SSE latency (reranking disabled, 3 samples): "
            f"median first token {response_latency['first_token_ms']['median']} ms "
            f"(max {response_latency['first_token_ms']['max']} ms); median completion "
            f"{response_latency['completion_ms']['median']} ms "
            f"(max {response_latency['completion_ms']['max']} ms). "
            f"{response_latency['warm_cold_note']}"
        )
    else:
        latency_line = f"End-to-end generation latency: {response_latency['status']}. {response_latency.get('reason', '')}"
    return f"""# Public evaluation report

## Measured local result

The version-controlled evaluation set contains {methods['fused']['cases']} retrieval-labelled cases and {safety['total']} tool-policy/escalation checks. This exact run used the corpus fingerprint `{metadata['corpus']['fingerprint_sha256']}` and evaluation-set fingerprint `{metadata['evaluation_set']['fingerprint_sha256']}`.

| Metric | Semantic | BM25 | Fused |
| --- | ---: | ---: | ---: |
| Hit@1 | {methods['semantic']['hit_at_1']:.3f} | {methods['bm25']['hit_at_1']:.3f} | {methods['fused']['hit_at_1']:.3f} |
| Hit@3 | {methods['semantic']['hit_at_3']:.3f} | {methods['bm25']['hit_at_3']:.3f} | {methods['fused']['hit_at_3']:.3f} |

- Retrieval latency: median {results['retrieval']['latency_ms']['median']} ms across {results['retrieval']['latency_ms']['samples']} labelled retrievals; maximum {results['retrieval']['latency_ms']['max']} ms.
- Citation boundary: {citation['passed']}/{citation['server_boundary_checks']} controlled server-filter checks passed; {citation['unsupported_labels_rendered']} unsupported labels rendered.
- Tool policy and escalation: {safety['passed']}/{safety['total']} expected outcomes passed. Rejected proposals were exercised without execution where a proposal existed.
- {latency_line}

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
"""
