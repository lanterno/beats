build:
	docker compose build

up:
	docker compose up --remove-orphans

shell:
	docker compose run --rm api bash

ops:  # use this to install packages, and run system operations
	docker compose -f compose-ops.yml run --rm api bash

test:
	docker compose run -e DB_NAME="ptc-test" --rm api pytest

clean:
	uv run ruff check --fix

run-locally:
	PYTHONPATH="$PYTHONPATH:src" uv run uvicorn server:app --reload --host 0.0.0.0 --port 7999 --env-file src/.env
