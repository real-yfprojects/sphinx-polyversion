.PHONY: lint docs

lint:
	poetry run ruff check .
	poetry run mypy

docs:
	poetry run sphinx-polyversion docs/poly.py -l -vvv
