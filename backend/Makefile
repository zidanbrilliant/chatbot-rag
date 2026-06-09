.PHONY: lint format typecheck test test-cov check

lint:
	ruff check .

format:
	ruff check --fix .
	black .

typecheck:
	mypy app/

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

check: lint typecheck test
