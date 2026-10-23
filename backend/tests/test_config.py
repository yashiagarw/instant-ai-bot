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
