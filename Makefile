.PHONY: venv install run lint test

venv:
	python3 -m venv .venv

install:
	. .venv/bin/activate && pip install -e .[dev]

run:
	. .venv/bin/activate && uvicorn ezply.main:app --reload

lint:
	. .venv/bin/activate && ruff check src

test:
	. .venv/bin/activate && pytest
