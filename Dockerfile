FROM python:3.9-rc-buster

WORKDIR /src
RUN pip install 'pipenv==2018.11.26'

COPY . .
ENV PYTHONPATH "${PYTHONPATH}:/src/ptc"

# TODO: read https://pythonspeed.com/articles/pipenv-docker/
RUN pipenv install --deploy --system

EXPOSE 8000
CMD ["uvicorn", "server:app", "--reload", "--host", "0.0.0.0"]
