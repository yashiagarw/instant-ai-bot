from app.config import Settings


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/prod")
    monkeypatch.setenv("WEB_ORIGIN", "https://instantmechanic.online")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "7")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@db:5432/prod"
    assert s.web_origin == "https://instantmechanic.online"
    assert s.db_connect_timeout == 7


def test_defaults_match_env_example(monkeypatch):
    for name in ("DATABASE_URL", "TEST_DATABASE_URL", "WEB_ORIGIN", "ENVIRONMENT", "DB_CONNECT_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert s.web_origin == "http://localhost:3000"
    assert s.test_database_url.endswith("/autocare_test")


def test_env_example_keeps_the_llm_off_and_holds_no_key():
    from pathlib import Path

    lines = (Path(__file__).resolve().parents[1] / ".env.example").read_text().splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    assert values["LLM_PROVIDER"] == "none" and values["ANTHROPIC_API_KEY"] == ""
    s = Settings(_env_file=None)
    assert values["LLM_EXTRACTION_MODEL"] == s.llm_extraction_model and values["LLM_EFFORT"] == s.llm_effort
    assert float(values["LLM_TIMEOUT_SECONDS"]) == s.llm_timeout_seconds
    assert float(values["LLM_DAILY_SPEND_CAP_USD"]) == s.llm_daily_spend_cap_usd
