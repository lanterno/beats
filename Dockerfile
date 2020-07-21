FROM python:3.9-rc-buster

WORKDIR /src
COPY src/ .
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock

RUN pip install 'pipenv==2018.11.26'


# TODO: read https://pythonspeed.com/articles/pipenv-docker/
RUN pipenv install --deploy --system

EXPOSE $PORT
CMD uvicorn server:app --reload --host 0.0.0.0 --port $PORT