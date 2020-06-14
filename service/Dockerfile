FROM python:3.9-rc-buster

WORKDIR /app
RUN pip install pipenv

COPY . .

RUN pipenv install --deploy --system

CMD ["uvicorn", "server:app", "--reload", "--host", "0.0.0.0"]
