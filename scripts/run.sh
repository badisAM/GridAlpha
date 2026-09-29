#!/usr/bin/env bash
# Runs the pipeline once (if no model yet), then the API (:8000) and the web app (:3000).
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
export PYTHONPATH="$PWD/backend"
if [ ! -f backend/data/lake/plan_latest.parquet ] || [ "${1:-}" = "--refresh" ]; then
  python -m gridalpha.cli run --quick
fi
python -m uvicorn gridalpha.api.main:app --app-dir backend --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
cd frontend && npm run build >/dev/null && npm run start
