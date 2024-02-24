FROM python:3.11-slim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the New Relic configuration file and application code
COPY ./etc/secrets/newrelic.ini /code/newrelic.ini
COPY ./app /code/app

# Expose the New Relic environment variables
ENV NEW_RELIC_CONFIG_FILE=/code/newrelic.ini
ENV NEW_RELIC_ENVIRONMENT=production

CMD ["newrelic-admin", "run-program", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
