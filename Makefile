.PHONY: lint docs test

lint:
	poetry run ruff check .
	poetry run mypy

docs:
	poetry run sphinx-polyversion docs/poly.py -l -vvv

test:
	poetry run pytest --cov=sphinx_polyversion/ --cov-report=term-missing --cov-report=lcov --numprocesses=auto
