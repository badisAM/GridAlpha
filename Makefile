# GridAlpha — common tasks (macOS / Linux / WSL). Windows: see scripts/*.ps1
PY ?= .venv/bin/python
export PYTHONPATH := $(CURDIR)/backend

.PHONY: setup pipeline pipeline-full api web dev test lint notebooks docker bench

setup:            ## create venv, install backend + frontend deps
	./scripts/setup.sh

pipeline:         ## ingest -> 90-day backtest -> train -> forecast -> bid (~2-3 min)
	$(PY) -m gridalpha.cli run --quick

pipeline-full:    ## same with the 365-day backtest (~5-8 min)
	$(PY) -m gridalpha.cli run

api:              ## FastAPI on :8000 (docs: /docs)
	$(PY) -m uvicorn gridalpha.api.main:app --app-dir backend --port 8000 --reload

web:              ## Next.js dev server on :3000
	cd frontend && npm run dev

test:             ## 50 tests: leakage, optimiser physics, API end-to-end
	cd backend && ../$(PY) -m pytest

lint:
	cd backend && ../$(PY) -m ruff check gridalpha tests
	cd frontend && npm run typecheck

notebooks:        ## regenerate + execute the analysis notebooks
	$(PY) notebooks/build_notebooks.py --execute

bench:            ## API latency benchmark (API must be running)
	$(PY) scripts/benchmark.py

docker:           ## full stack in containers
	docker compose up --build
