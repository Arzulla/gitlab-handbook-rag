.PHONY: setup data ingest app test lint format eval

SPLIT ?= dev

setup:
	uv sync

data:
	uv run python scripts/download_handbook.py

ingest:
	uv run python scripts/ingest.py

app:
	@echo "make app: not implemented yet (handbook_rag.app)" && exit 1

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format:
	uv run ruff format .
	uv run ruff check --fix .

eval:
	@test -n "$(LABEL)" || (echo "usage: make eval LABEL=<name> SPLIT=dev|test" && exit 1)
	@echo "make eval: not implemented yet (eval/run_eval.py)" && exit 1
