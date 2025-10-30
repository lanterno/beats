build:
	docker compose build

up:
	docker compose --profile dev up --remove-orphans

down:
	docker compose --profile dev down

shell:
	docker compose --profile dev run --rm api bash

test:
	docker compose --profile test build api_test
	docker compose --profile test run --rm api_test uv run --group dev pytest -q

test-cov:
	docker compose --profile test run --rm api_test uv run --group dev pytest --cov=beats --cov-report=term-missing

clean:
	uv run --group dev ruff check --fix

lint:
	uv run --group dev ruff check

run-locally:
	cd src && uv run uvicorn server:app --reload --host 0.0.0.0 --port 7999
