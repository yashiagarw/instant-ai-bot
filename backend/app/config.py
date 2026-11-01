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
    # The origins allowed by CORS (with credentials): the customer web app and the staff admin app.
    web_origin: str = "http://localhost:3000"
    admin_origin: str = "http://localhost:3001"
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
    # Customer accounts (app.accounts). AUTH_SECRET keys the OTP hashes: set a long random value in production
    # (python -c "import secrets; print(secrets.token_urlsafe(48))"); the API refuses to start there without one.
    auth_secret: str = "dev-only-auth-secret-change-me"
    # SMS for login codes: console (prints the code, development and tests only) or msg91 (needs the MSG91 keys).
    sms_provider: Literal["console", "msg91"] = "console"
    msg91_auth_key: str = ""
    msg91_template_id: str = ""  # DLT-approved OTP template registered in MSG91
    msg91_sender_id: str = ""  # 6-letter DLT sender ID (header)
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    # Codes sent to one phone: at most N per window (counted in the database, so it holds across workers).
    otp_phone_limit: int = 3
    otp_phone_window_seconds: int = 900
    # Per-IP limits on asking for a code and on checking one.
    otp_ip_limit: int = 10
    otp_ip_window_seconds: int = 3600
    otp_verify_ip_limit: int = 20
    otp_verify_ip_window_seconds: int = 900
    auth_session_days: int = 30
    # Login cookies are HttpOnly, SameSite=Lax and Secure. Browsers accept Secure cookies on http://localhost;
    # set false only if yours does not (never in production).
    cookie_secure: bool = True
    # Staff login (/api/admin): email + password + TOTP, its own cookie and shorter sessions than customers.
    # STAFF_TOTP_KEY encrypts TOTP secrets (a Fernet key); empty = derived from AUTH_SECRET (development only).
    staff_totp_key: str = ""
    staff_totp_issuer: str = "Instant Mechanic"
    staff_session_hours: int = 8  # absolute
    staff_idle_minutes: int = 30  # without a request
    staff_max_failed_logins: int = 5  # then locked for staff_lockout_minutes
    staff_lockout_minutes: int = 15
    staff_login_ip_limit: int = 20
    staff_login_ip_window_seconds: int = 900
    # Customer photos: an S3-compatible private bucket (the docker-compose `storage` service locally). The endpoint is
    # where the API reaches the storage; the public endpoint is the address in presigned links given to browsers.
    s3_endpoint_url: str = "http://localhost:8333"
    s3_public_endpoint_url: str = ""  # empty = s3_endpoint_url
    s3_region: str = "ap-south-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "autocare-uploads"
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_max_px: int = 2000  # longest side after resizing
    upload_url_ttl_seconds: int = 600  # presigned upload form
    upload_view_ttl_seconds: int = 300  # signed link to see a photo
    uploads_per_session: int = 5
    upload_rate_limit: int = 20  # new uploads per IP per window
    upload_rate_window_seconds: int = 600
    # Files customers upload outside the bucket (none yet): deleted with the account, one folder per user id.
    uploads_dir: Path = Path(__file__).resolve().parents[2] / "data" / "uploads"
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
    # Photo analysis (app.vision): reads a customer photo as labels from image_labels. Images take longer.
    llm_vision_model: str = "claude-opus-5-5"
    llm_vision_timeout_seconds: float = 20.0
    # Photo findings at or above this confidence (0-1) are shown and used as evidence; below: "unclear".
    vision_min_confidence: float = 0.6
    # Estimated USD per day (India time) across all live calls; once reached, every step falls back.
    llm_daily_spend_cap_usd: float = 2.0
    # Dataset publish pipeline (app.datasets): jobs go through Redis to the arq worker
    # (uv run arq app.datasets.worker.WorkerSettings). docker compose up -d redis starts Redis on 6379.
    redis_url: str = "redis://localhost:6379/0"
    # Uploaded dataset files are kept here: a version is rebuilt from its files (rollback, rebuild). Not committed.
    dataset_upload_dir: Path = Path(__file__).resolve().parents[2] / "data" / "uploads" / "datasets"
    dataset_upload_max_mb: int = 25
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
