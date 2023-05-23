# syntax = docker/dockerfile:latest
FROM python:3.11-slim as python
ENV PYTHONUNBUFFERED=true

FROM python as deps_builder
WORKDIR /deps
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_HOME=/opt/poetry
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN python -c 'from urllib.request import urlopen; print(urlopen("https://install.python-poetry.org").read().decode())' | python -
COPY . ./
RUN poetry install --no-interaction --no-ansi -vvv


FROM python as runtime
COPY --from=deps_builder /deps/.venv /deps/.venv

WORKDIR /src
COPY src/ ./src
ENV PATH="/deps/.venv/bin:$PATH"
EXPOSE $PORT
CMD uvicorn server:app --reload --host 0.0.0.0 --port $PORT
