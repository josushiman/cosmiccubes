Used https://docs.pydantic.dev/latest/integrations/datamodel_code_generator/
To convert the ynab openapi schema to pydantic models.
`datamodel-codegen --input app/ynab_openapi.yaml --input-file-type openapi --output app/ynab_models.py`

Change the logging values in the [logging.yaml] file. It's been commented to specify what parts need to be changed in order to see DEBUG commits.

Update requirements .txt
`pipenv requirements > requirements.txt`

Run with New Relic
`NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program uvicorn app.main:app --reload --log-config=logging.yml`
