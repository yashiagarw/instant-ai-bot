"""Settings loaded from environment variables (and backend/.env in development)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    # SQLAlchemy URL, psycopg 3 driver.
    database_url: str = "postgresql+psycopg://autocare:autocare@localhost:5432/autocare"
    # Separate database used only by pytest. Tests drop and recreate its tables.
    test_database_url: str = "postgresql+psycopg://autocare:autocare@localhost:5432/autocare_test"
    # The only origin allowed by CORS: the customer web app.
    web_origin: str = "http://localhost:3000"
    # Seconds to wait for Postgres before the health check reports it unavailable.
    db_connect_timeout: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
