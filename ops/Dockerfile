FROM python:3.14-slim

ENV PYTHONUNBUFFERED=true
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Install uv and minimal tooling
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy only project metadata first for better layer caching
COPY pyproject.toml ./
COPY README.md ./
COPY LICENSE ./
COPY uv.lock* ./

# Install runtime dependencies (no dev) using uv and the lock if present
RUN uv sync --no-dev --frozen || uv sync --no-dev

# Copy application source
COPY src/ ./src

# Run from app source directory
WORKDIR /app/src

EXPOSE $PORT
# Use uv to run the server with the project virtualenv
CMD uv run uvicorn server:app --host 0.0.0.0 --port $PORT
