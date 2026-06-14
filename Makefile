.PHONY: test lint typecheck benchmark coverage clean

test:
	pytest -v tests/unit tests/integration

functional-test:
	pytest -v tests/functional

lint:
	ruff check src/ tests/
	ruff format src/ tests/ --check

typecheck:
	mypy src/ --ignore-missing-imports

benchmark:
	pytest tests/performance --benchmark-only

coverage:
	pytest --cov=src/iam --cov-report=term-missing --cov-report=html

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf dist
	rm -rf build
