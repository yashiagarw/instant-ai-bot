"""Settings loaded from environment variables (and backend/.env in development)."""

from functools import lru_cache
from typing import Literal

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
    # Diagnosis API. Embeddings load the sentence-transformers model (about 470 MB) at first use;
    # off by default because keyword matching scored as well on the dev split.
    diagnosis_embeddings: bool = False
    # Per-IP limit on new diagnosis sessions: at most N per window.
    session_rate_limit: int = 10
    session_rate_window_seconds: int = 60
    # Use the first X-Forwarded-For address as the client IP. Only enable behind a proxy you control.
    trust_forwarded_for: bool = False
    # Offline question structuring (app.knowledge.questions). Never used by the live app.
    # Empty key = the SDK's own credential lookup (ANTHROPIC_API_KEY env, `ant auth login` profile).
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str = ""
    questions_model: str = "claude-opus-5-5"
    questions_effort: str = "high"
    # OpenAI (used when LLM_PROVIDER=openai). No default model: set the one you want to pay for.
    # Empty key = the SDK's own lookup (OPENAI_API_KEY environment variable).
    openai_api_key: str = ""
    openai_model: str = ""
    openai_reasoning_effort: str = ""  # e.g. low / medium / high for reasoning models; empty = model default
    # USD per million tokens, for the cost estimate in the run log. 0 = cost not estimated.
    openai_price_input_per_m: float = 0.0
    openai_price_cached_input_per_m: float = 0.0
    openai_price_output_per_m: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
