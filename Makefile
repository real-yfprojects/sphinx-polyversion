.PHONY: lint

lint:
	ruff check .
	mypy
