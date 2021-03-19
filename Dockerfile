# syntax = docker/dockerfile:latest
FROM python:3.9-slim-buster

WORKDIR /src
COPY src/ .
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock

RUN pip install pipenv

# TODO: read https://pythonspeed.com/articles/pipenv-docker/
RUN pipenv install --dev --system

EXPOSE $PORT
CMD uvicorn server:app --reload --host 0.0.0.0 --port $PORT
