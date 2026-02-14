.PHONY: dev test lint format

dev:
	PYTHONPATH=src python -m uca_orchestrator.api

test:
	PYTHONPATH=src pytest

lint:
	python -m ruff check .

format:
	python -m ruff format .

