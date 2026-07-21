from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.evaluation import build_results, load_cases, measure_end_to_end_response, render_report
from app.ingestion import DocumentStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local, fictional Grounded Support Assistant evaluation set.")
    parser.add_argument("--cases", type=Path, default=PROJECT_ROOT / "backend/evaluation/cases.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs/evaluation-results.json")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "docs/evaluation-report.md")
    parser.add_argument("--api-url", help="Optional reachable local FastAPI URL for real HTTP/SSE latency measurement.")
    parser.add_argument("--latency-samples", type=int, default=3, help="Number of retrieval cases to stream when --api-url is set.")
    args = parser.parse_args()
    temporary_root = Path(tempfile.mkdtemp(prefix="grounded-support-eval-"))
    try:
        store = DocumentStore(app_settings=Settings(chroma_path=temporary_root / "chroma"))
        sample_paths = sorted((PROJECT_ROOT / "sample_docs").glob("*"))
        store.ingest_paths(sample_paths)
        results = build_results(args.cases, sample_paths, store, run_mode="cold-temporary-corpus")
        if args.api_url:
            results["response_latency"] = measure_end_to_end_response(
                args.api_url, load_cases(args.cases), max(1, args.latency_samples)
            )
        args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        args.report.write_text(render_report(results), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "report": str(args.report)}, indent=2))
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    main()
