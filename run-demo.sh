#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
OLLAMA_PID=""
OLLAMA_URL="http://localhost:11434"
if [[ -f "$ROOT_DIR/.env" ]]; then
  CONFIGURED_OLLAMA_URL="$(sed -n 's/^OLLAMA_BASE_URL=//p' "$ROOT_DIR/.env" | tail -n 1)"
  OLLAMA_URL="${CONFIGURED_OLLAMA_URL:-$OLLAMA_URL}"
fi

if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  if [[ "$OLLAMA_URL" == http://localhost:* || "$OLLAMA_URL" == http://127.0.0.1:* ]] && command -v ollama >/dev/null 2>&1; then
    ollama serve >"$ROOT_DIR/.ollama-demo.log" 2>&1 &
    OLLAMA_PID=$!
    for _ in {1..20}; do
      curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1 && break
      sleep 0.5
    done
  fi
fi

(cd "$ROOT_DIR/backend" && conda run --no-capture-output -n grounded-support-assistant uvicorn app.main:app --reload --port 8010) &
API_PID=$!
cleanup() {
  kill "$API_PID" 2>/dev/null || true
  if [[ -n "$OLLAMA_PID" ]]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
cd "$ROOT_DIR/frontend"
conda run --no-capture-output -n grounded-support-assistant npm run dev
