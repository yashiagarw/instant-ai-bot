"""Phase 5.4: the legal pages quote our consent texts and retention periods exactly; the backup service and the
restore script keep their safety rules."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

from app.accounts import service as accounts
from app.config import Settings
from app.notify import optins
from app.requests import service as requests

ROOT = Path(__file__).resolve().parents[2]
LEGAL = (ROOT / "apps/web/src/components/legal/legal.tsx").read_text()
PRIVACY = (ROOT / "apps/web/src/app/privacy/page.tsx").read_text()


def test_the_privacy_notice_quotes_every_consent_text_and_version_exactly():
    for version, text in (
        (accounts.CONSENT_VERSION, accounts.CONSENT_TEXT),
        (requests.CONSENT_VERSION, requests.CONSENT_TEXT),
        (optins.WHATSAPP_CUSTOMER_VERSION, optins.WHATSAPP_CUSTOMER_TEXT),
        (optins.WHATSAPP_MECHANIC_VERSION, optins.WHATSAPP_MECHANIC_TEXT),
    ):
        assert f'version: "{version}"' in LEGAL, version
        assert text in LEGAL, version  # word for word: change the page when a consent text changes


def test_the_privacy_notice_states_the_retention_periods_we_apply():
    s = Settings(_env_file=None)
    assert f"{s.retention_location_days} days after the job is completed or cancelled" in PRIVACY
    assert f"removed {s.retention_replay_days} days after the diagnosis" in PRIVACY
    assert f"unlinked from you after {s.retention_llm_days} days" in PRIVACY
    assert f"deleted {s.retention_whatsapp_inbound_days} days after we handle them" in PRIVACY
    assert "Draft, pending legal review" in LEGAL and "[GRIEVANCE OFFICER NAME]" in LEGAL


def test_the_backup_service_is_encrypted_scheduled_and_private():
    prod = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())
    b = prod["services"]["backup"]
    assert "ports" not in b and b["restart"] == "unless-stopped" and b["healthcheck"]["test"]
    assert "backups:/backups" in b["volumes"] and any(v.endswith(":/data/media:ro") for v in b["volumes"])
    assert b["environment"]["BACKUP_AGE_RECIPIENT"] == "${BACKUP_AGE_RECIPIENT:-}"
    assert "backups" in prod["volumes"]


def test_backup_never_writes_unencrypted_and_restore_never_touches_live_data():
    backup = (ROOT / "docker/backup/backup.sh").read_text()
    restore = (ROOT / "docker/backup/restore.sh").read_text()
    # Every part goes through age to the recipient; without one, nothing is written.
    assert 'if [ -z "${BACKUP_AGE_RECIPIENT:-}" ]' in backup and "exit 0" in backup
    for part in ("postgres.dump.age", "photos.tar.age", "media.tar.age"):
        assert re.search(rf"\| enc \"\$DIR/{re.escape(part)}\"", backup), part
    assert "pg_dump" in backup and "| enc" in backup.split("pg_dump", 1)[1].splitlines()[0]
    assert "--min-age" in backup and "BACKUP_RETENTION_DAYS:-30" in backup
    # Restore: a new database only, never the live one or a test one; checksums first; the key is not baked in.
    assert "refusing to restore into the live database" in restore and "*_test)" in restore
    assert "already exists: restore into a new one" in restore and "sha256sum -c SHA256SUMS" in restore
    for script in ("backup.sh", "restore.sh", "schedule.sh"):
        assert subprocess.run(["sh", "-n", str(ROOT / "docker/backup" / script)]).returncode == 0, script
    assert "age1" not in (ROOT / ".env.prod.example").read_text().split("BACKUP_AGE_RECIPIENT=", 1)[1].split("\n")[0]
