from fastapi.testclient import TestClient

from app.main import create_app

WEB_ORIGIN = "http://localhost:3000"


def test_health_ok_with_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_is_down(test_settings):
    # Nothing listens on port 1, so the connection fails fast.
    down = test_settings.model_copy(
        update={"database_url": "postgresql+psycopg://x:x@127.0.0.1:1/nothing_test", "db_connect_timeout": 1}
    )
    app = create_app(down)
    with TestClient(app) as c:
        response = c.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}


def test_cors_allows_the_web_origin(client, test_settings):
    assert test_settings.web_origin == WEB_ORIGIN
    response = client.get("/api/health", headers={"Origin": WEB_ORIGIN})
    assert response.headers.get("access-control-allow-origin") == WEB_ORIGIN

    preflight = client.options("/api/health", headers={"Origin": WEB_ORIGIN, "Access-Control-Request-Method": "GET"})
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == WEB_ORIGIN


def test_cors_rejects_other_origins(client):
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers

    preflight = client.options(
        "/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
