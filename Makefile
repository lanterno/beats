build:
	docker compose -f ops/docker-compose.yml build

up:
	docker compose -f ops/docker-compose.yml --profile dev up --remove-orphans

shell:
	docker compose -f ops/docker-compose.yml --profile dev run --rm api bash

ops:  # use this to install packages, and run system operations
	docker compose -f ops/compose-ops.yml run --rm api bash

test:
	docker compose -f ops/docker-compose.yml --profile test build api_test
	docker compose -f ops/docker-compose.yml --profile test run --rm api_test uv run --group dev pytest -q

clean:
	uv run --group dev ruff check --fix

lint:
	uv run --group dev ruff check

run-locally:
	cd src && uv run uvicorn server:app --reload --host 0.0.0.0 --port 7999
