"""Settings loaded from environment variables (and backend/.env in development)."""

from functools import lru_cache
from pathlib import Path
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
    # Free-text matching: hybrid (Postgres full-text + vector similarity + typo correction, merged with RRF, over
    # the embeddings table; loads the local multilingual MiniLM model, about 470 MB, at first use) or keyword
    # (the engine's built-in keyword index, no model).
    diagnosis_search: Literal["hybrid", "keyword"] = "hybrid"
    # Diagnosis engine: v2 (Bayesian posterior, information gain; the default since the 2.3 test-split comparison)
    # or v1 (scores and fixed rules).
    diagnosis_engine: Literal["v1", "v2"] = "v2"
    # Per-IP limit on new diagnosis sessions: at most N per window.
    session_rate_limit: int = 10
    session_rate_window_seconds: int = 60
    # Use the first X-Forwarded-For address as the client IP. Only enable behind a proxy you control.
    trust_forwarded_for: bool = False
    # Request a Mechanic. The helpline is shown to customers; no real number is built in.
    helpline_number: str = ""
    # New requests are emailed here. Empty = no alert is sent (the request is still stored).
    support_email: str = ""
    # Email provider: console (prints the alert, for development), smtp or resend.
    email_provider: Literal["console", "smtp", "resend"] = "console"
    email_from: str = "Instant Mechanic <alerts@example.com>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    resend_api_key: str = ""
    # Per-IP limit on new service requests: at most N per window.
    request_rate_limit: int = 5
    request_rate_window_seconds: int = 600
    # Fault pictures (drawn guides) served at /media; result `media[].file` paths are relative to it.
    media_dir: Path = Path(__file__).resolve().parents[2] / "data" / "media"
    # LLM provider. none (default): every live LLM step uses its non-LLM fallback (engine + hybrid search for
    # extraction, the original question text for phrasing). anthropic: the live layer (app.llm) calls Claude, but
    # only when ANTHROPIC_API_KEY is set. openai: offline question drafting only (the live layer falls back).
    # Offline question structuring (app.knowledge.questions) uses anthropic or openai (or --provider); there an
    # empty key means the SDK's own credential lookup.
    llm_provider: Literal["none", "anthropic", "openai"] = "none"
    anthropic_api_key: str = ""
    # Live LLM layer (app.llm): extraction of symptoms / answers from free text, and question phrasing.
    llm_extraction_model: str = "claude-haiku-5-5"
    llm_phrasing_model: str = "claude-haiku-5-5"
    llm_explanation_model: str = "claude-haiku-5-5"
    llm_effort: str = "low"  # output_config.effort for live calls
    llm_timeout_seconds: float = 4.0  # wall clock per call; slower calls fall back
    # Estimated USD per day (India time) across all live calls; once reached, every step falls back.
    llm_daily_spend_cap_usd: float = 2.0
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
