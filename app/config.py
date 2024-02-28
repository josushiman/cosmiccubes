import os
from uuid import UUID
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_url: str
    env_agent: str
    env_docs: str | None = None
    env_hosts: str = ["*"]
    env_origins: str = ["*"]
    env_referer: str = ["*"]
    env_token: UUID
    ext_ynab_token: str
    ext_ynab_url: str
    newrelic_ini_path: str = os.getcwd() + '/newrelic.ini'
    newrelic_env: str = 'production'
    ynab_phrase: str
    ynab_budget_id: UUID

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
