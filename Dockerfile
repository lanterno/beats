FROM python:3.14-slim

# Prevents Python from writing pyc files and buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Install uv package manager
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy dependency files first for better layer caching
COPY pyproject.toml ./
COPY README.md ./

# Copy uv.lock if it exists (using wildcard to make it optional)
COPY uv.lock* ./

# Install runtime dependencies (no dev) using uv
# --frozen uses exact versions from lock file, fallback to --no-dev if no lock
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Copy application source
COPY src/ ./src/

# Set working directory to app root (not src)
WORKDIR /app

# Default port
ENV PORT=8000

EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Use uv to run the server with the project virtualenv
CMD uv run uvicorn server:app --host 0.0.0.0 --port ${PORT} --app-dir src
