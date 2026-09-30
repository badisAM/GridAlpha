#!/usr/bin/env bash
set -e
python -m gridalpha.cli run --quick
exec uvicorn gridalpha.api.main:app --host 0.0.0.0 --port 7860