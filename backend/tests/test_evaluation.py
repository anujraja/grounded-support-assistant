from __future__ import annotations

import json
from pathlib import Path

from test_backend_behaviors import make_chunk

from app.citations import filter_citation_labels, finish_citation_filter
from app.evaluation import hit_at_k, load_cases, rank_chunks, source_key


def test_versioned_evaluation_cases_define_expected_outcomes():
    cases_path = Path(__file__).resolve().parents[1] / "evaluation/cases.json"
    cases = load_cases(cases_path)

    assert len(cases) == 6
    assert {"expected_sources", "expected_escalation", "expected_tool", "expected_destructive_refusal"} <= set(cases[0])
    assert any(case["expected_destructive_refusal"] for case in cases)
    assert any(case["expected_tool"] == "create_escalation_summary" for case in cases)
    assert json.loads(cases_path.read_text(encoding="utf-8"))["version"] == 1


def test_evaluation_ranking_reports_each_retrieval_method_without_synthesizing_sources():
    expected = make_chunk("expected", "trace evidence", filename="trace.md", heading="Headers", vector_score=0.2, bm25_score=1.0, combined_score=0.56, final_rank=2)
    semantic = make_chunk("semantic", "other", filename="other.md", heading="Other", vector_score=1.0, bm25_score=0.0, combined_score=0.55, final_rank=1)

    assert source_key(expected) == "trace.md#Headers"
    assert rank_chunks([expected, semantic], "semantic")[0].id == "semantic"
    assert rank_chunks([expected, semantic], "bm25")[0].id == "expected"
    assert hit_at_k(rank_chunks([expected, semantic], "bm25"), [source_key(expected)], 1) is True
    assert hit_at_k(rank_chunks([expected, semantic], "semantic"), [source_key(expected)], 1) is False


def test_server_citation_filter_removes_unsupported_labels_across_streamed_tokens():
    first, pending, seen = filter_citation_labels("Verified [", 1)
    second, pending, next_seen = filter_citation_labels("1] and [99]", 1, pending)

    assert first == "Verified "
    assert pending == ""
    assert seen is False
    assert next_seen is True
    assert second == "[1] and [unsupported citation removed]"
    assert finish_citation_filter("[99") == "[unsupported citation removed]"
