"""Phase 5.1 container setup: the rules docker-compose.prod.yml, docker-compose.yml and the Dockerfiles must keep
(own production database volume, migrations before the API, nothing but Caddy published, non-root images, data
mounted not baked, placeholders only in the committed env examples). No Docker needed: the files are parsed."""

import re
from pathlib import Path

import pytest
import yaml

from app.datasets.worker import WorkerSettings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def prod() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())


@pytest.fixture(scope="module")
def dev() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_prod_has_its_own_project_and_database_volume(prod, dev):
    assert prod["name"] == "autocare-prod"
    db_volumes = prod["services"]["db"]["volumes"]
    assert db_volumes == ["pgdata_prod:/var/lib/postgresql/data"]
    assert "pgdata" in dev["volumes"] and "pgdata" not in prod["volumes"]


def test_prod_services(prod):
    services = prod["services"]
    for name in ("caddy", "web", "admin", "api", "worker", "db", "redis", "migrate", "storage"):
        assert name in services, name
    assert not any("minio" in name or "minio" in str(s.get("image", "")) for name, s in services.items())
    # SeaweedFS only for a single server; a cloud bucket needs no change but leaving the profile off.
    assert services["storage"]["profiles"] == ["storage"]
    assert services["setup"]["profiles"] == ["setup"]


def test_only_caddy_publishes_ports(prod):
    published = {name for name, s in prod["services"].items() if s.get("ports")}
    assert published == {"caddy"}


def test_migrations_run_once_before_the_api_and_the_worker(prod):
    services = prod["services"]
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["migrate"]["restart"] == "no"
    for name in ("api", "worker"):
        assert services[name]["depends_on"]["migrate"] == {"condition": "service_completed_successfully"}


def test_api_and_worker_share_one_image_and_redis(prod):
    api, worker = prod["services"]["api"], prod["services"]["worker"]
    assert api["image"] == worker["image"]
    assert worker["command"][:2] == ["arq", "app.datasets.worker.WorkerSettings"]
    assert worker["environment"]["REDIS_URL"].startswith("redis://redis:")
    assert worker["depends_on"]["redis"] == {"condition": "service_healthy"}


def test_long_running_services_restart_and_have_health_checks(prod):
    for name in ("caddy", "web", "admin", "api", "worker", "db", "redis", "storage"):
        service = prod["services"][name]
        assert service["restart"] == "unless-stopped", name
        assert service["healthcheck"]["test"], name


def test_worker_health_check_key_is_fresh():
    # `arq --check` reads a Redis key refreshed every health_check_interval seconds (arq's default is an hour).
    assert WorkerSettings.health_check_interval <= 60


def test_raw_files_and_pictures_are_mounted_not_baked(prod):
    mounts = prod["services"]["worker"]["volumes"]
    assert any(m.endswith(":/app/data/raw:ro") for m in mounts)
    assert any(m.endswith(":/app/data/media") for m in mounts)
    ignore = (ROOT / "backend" / "Dockerfile.dockerignore").read_text().splitlines()
    for path in ("data/raw", "data/media", "data/models", "data/uploads"):
        assert path in ignore, path


def test_next_public_values_are_build_args(prod):
    for name in ("web", "admin"):
        args = prod["services"][name]["build"]["args"]
        assert args["APP"] == name
        assert args["NEXT_PUBLIC_API_URL"] == "https://${API_DOMAIN}"
    assert "NEXT_PUBLIC_MAP_TILE_URL" in prod["services"]["admin"]["build"]["args"]


@pytest.mark.parametrize("dockerfile", ["backend/Dockerfile", "apps/Dockerfile"])
def test_images_are_multi_stage_and_run_as_a_non_root_user(dockerfile):
    text = (ROOT / dockerfile).read_text()
    assert len(re.findall(r"^FROM ", text, re.M)) >= 3
    runtime = text.split(" AS runtime", 1)[1].split("\nFROM ", 1)[0]
    user = re.search(r"^USER (\S+)", runtime, re.M)
    assert user and user.group(1) not in ("root", "0")


def test_backend_image_is_cpu_only_and_offline():
    text = (ROOT / "backend" / "Dockerfile").read_text()
    assert "HF_HUB_OFFLINE=1" in text and "ARG EMBEDDING_MODEL" in text
    pyproject = (ROOT / "backend" / "pyproject.toml").read_text()
    assert "download.pytorch.org/whl/cpu" in pyproject
    lock = (ROOT / "backend" / "uv.lock").read_text()
    assert 'name = "nvidia-' not in lock and 'name = "triton"' not in lock


def test_dev_compose_keeps_the_host_workflow(dev):
    # `docker compose up -d` still starts only the local services; the app containers are opt-in.
    default = {name for name, s in dev["services"].items() if not s.get("profiles")}
    assert default == {"db", "storage", "redis"}
    assert dev["services"]["api"]["profiles"] == ["app"]


@pytest.mark.parametrize("example", [".env.prod.example", "backend/.env.prod.example"])
def test_committed_env_examples_hold_placeholders_only(example):
    secret_names = ("PASSWORD", "SECRET", "KEY", "TOKEN")
    for line in (ROOT / example).read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if any(s in name for s in secret_names) and not name.startswith(("EMBEDDING", "NEXT_PUBLIC")):
            assert value in ("", "change-me") or value.startswith("change-me"), f"{example}: {name} looks real"


def test_real_env_files_are_ignored():
    ignore = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env.prod" in ignore and "backend/.env.prod" in ignore and "!.env.prod.example" in ignore
