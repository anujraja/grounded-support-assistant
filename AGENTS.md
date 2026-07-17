# Grounded Support Assistant - Agent Guide

## Architecture

- `backend/app/ingestion.py`: heading-aware chunks and Chroma persistence.
- `backend/app/retrieval.py`: vector + BM25 score fusion; keep raw scores visible.
- `backend/app/generation.py`: Ollama streaming only; citations originate from retrieval.
- `backend/app/tools.py`: the sole tool authority. Never add direct side effects or bypass approval.
- `backend/app/audit.py`: intentionally local/in-memory demo audit trail.
- `frontend/src`: one React workbench; preserve the evidence-first three-pane layout.
- `docs/`: architecture, decisions, security, evaluation, API, case-study, and demo documentation. Keep claims aligned with code and verified behavior.

## Commands

```bash
conda env create -f environment.yml
cd backend && conda run -n grounded-support-assistant python -m app.ingestion --samples && cd ..
conda run -n grounded-support-assistant uvicorn app.main:app --app-dir backend --reload --port 8010
conda run -n grounded-support-assistant npm --prefix frontend ci
conda run -n grounded-support-assistant npm --prefix frontend run build
conda run -n grounded-support-assistant pytest -q backend/tests
./run-demo.sh
```

## Conventions

- Python 3.12, typed Pydantic request/response models, explicit dependencies over agent frameworks.
- All claimed facts in generated answers must map to supplied retrieval chunks; never synthesize citation IDs.
- Tools are fake/local/deterministic. Validate `extra='forbid'` argument schemas and require a persisted approved proposal.
- Keep document prose clearly fictional. Do not add real credentials, customer data, or destructive capabilities.
- Tests must avoid downloading models or calling Ollama.

## Definition of done

A change is done when the relevant tests pass, the frontend production build passes for UI work, citations remain traceable to retrieved chunks, and tool execution still requires explicit approval. Preserve the low-confidence escalation path and the destructive-action refusal.
