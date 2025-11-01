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

# Cloud Build targets
trigger-build:
	cd terraform && gcloud builds triggers run beats-api-build \
		--project=beats-476914 \
		--branch=main

build-status:
	gcloud builds list --project=beats-476914 --limit=5

build-logs:
	@BUILD_ID=$$(gcloud builds list --project=beats-476914 --limit=1 --format="value(id)" | head -1); \
	if [ -z "$$BUILD_ID" ]; then \
		echo "No builds found"; \
	else \
		echo "Viewing logs for build: $$BUILD_ID"; \
		gcloud builds log $$BUILD_ID --project=beats-476914; \
	fi

build-logs-follow:
	@BUILD_ID=$$(gcloud builds list --project=beats-476914 --limit=1 --format="value(id)" | head -1); \
	if [ -z "$$BUILD_ID" ]; then \
		echo "No builds found"; \
	else \
		echo "Streaming logs for build: $$BUILD_ID (Press Ctrl+C to stop)"; \
		gcloud builds log $$BUILD_ID --project=beats-476914 --stream; \
	fi

build-logs-id:
	@if [ -z "$(BUILD_ID)" ]; then \
		echo "Usage: make build-logs-id BUILD_ID=<build-id>"; \
		echo "Example: make build-logs-id BUILD_ID=7b0567e9-b97c-402b-956d-e41fc0c5d9ee"; \
	else \
		gcloud builds log $(BUILD_ID) --project=beats-476914; \
	fi

build-trigger-id:
	cd terraform && terraform output cloud_build_trigger_id
