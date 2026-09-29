#!/usr/bin/env bash
# One-time setup (macOS / Linux / WSL). Requires Python >= 3.10 and Node >= 20.9.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# CPU-only PyTorch (small download); remove the index-url to use a CUDA build
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install -r backend/requirements-dev.txt
(cd frontend && npm ci --no-audit --no-fund)
echo "✔ setup done — next: ./scripts/run.sh"
