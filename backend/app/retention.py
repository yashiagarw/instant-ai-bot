"""Data retention (Phase 5.4): personal data past its time is removed by the worker, daily at 03:00 India time.

- **Precise location**, RETENTION_LOCATION_DAYS (90) after a job closes (completed or cancelled): the request's
  address, area text and notes (people describe where the car is) are emptied. The pincode stays (coarse, used by
  the reports), and so do the reference, the car, the diagnosis and the confirmed fault.
- **LLM call logs**, RETENTION_LLM_DAYS (30): the link to the diagnosis session and the detail text go; tokens,
  cost, model and outcome stay (spend reports).
- **Session replays** (the admin Quality page), RETENTION_REPLAY_DAYS (90) after the session started: what the
  customer typed (their first description, every message, feedback comments) is replaced by "[removed]". Answers to
  questions, results and safety alerts stay: they are not personal and the quality reports need them.
- **WhatsApp webhook messages**, RETENTION_WHATSAPP_INBOUND_DAYS (30): handled rows are deleted (they hold a keyed
  hash and a masked number only, but nothing needs them after handling).

Kept on purpose: request_outcomes and the golden set (data/eval/golden, golden_cases): no personal data, future
training data. Each run writes one audit entry with the counts.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.config import Settings

log = logging.getLogger(__name__)
REMOVED = "[removed]"
TYPED_EVENTS = ("free_text", "message_undone", "session_started")


@dataclass
class RetentionReport:
    locations: int = 0
    llm_calls: int = 0
    replay_events: int = 0
    replay_sessions: int = 0
    feedback_comments: int = 0
    whatsapp_inbound: int = 0

    def summary(self) -> str:
        return ", ".join(f"{k} {v}" for k, v in asdict(self).items())


def run(session: Session, settings: Settings, now: datetime | None = None) -> RetentionReport:
    now = now or datetime.now(UTC)
    r = RetentionReport()
    location_cutoff = now - timedelta(days=settings.retention_location_days)
    r.locations = session.execute(
        text(
            "UPDATE service_requests SET address = '', area_text = '', notes = '' "
            "WHERE status IN ('completed', 'cancelled') AND status_changed_at <= :cutoff "
            "AND (address <> '' OR area_text <> '' OR notes <> '')"
        ),
        {"cutoff": location_cutoff},
    ).rowcount
    r.llm_calls = session.execute(
        text(
            "UPDATE llm_calls SET session_id = NULL, detail = '' "
            "WHERE created_at <= :cutoff AND (session_id IS NOT NULL OR detail <> '')"
        ),
        {"cutoff": now - timedelta(days=settings.retention_llm_days)},
    ).rowcount
    replay_cutoff = now - timedelta(days=settings.retention_replay_days)
    old_sessions = "SELECT id FROM diagnosis_sessions WHERE created_at <= :cutoff"
    r.replay_events = session.execute(
        text(
            "UPDATE session_events SET payload = jsonb_set(payload, '{text}', to_jsonb(CAST(:removed AS text))) "
            f"WHERE session_id IN ({old_sessions}) AND event_type IN :types "
            "AND payload ? 'text' AND payload->>'text' <> :removed"
        ).bindparams(bindparam("types", expanding=True)),
        {"cutoff": replay_cutoff, "removed": REMOVED, "types": list(TYPED_EVENTS)},
    ).rowcount
    r.replay_sessions = session.execute(
        text(
            "UPDATE diagnosis_sessions SET entry_text = :removed "
            "WHERE created_at <= :cutoff AND entry_text IS NOT NULL AND entry_text <> '' AND entry_text <> :removed"
        ),
        {"cutoff": replay_cutoff, "removed": REMOVED},
    ).rowcount
    r.feedback_comments = session.execute(
        text(
            f"UPDATE feedback SET comment = :removed WHERE session_id IN ({old_sessions}) "
            "AND comment IS NOT NULL AND comment <> '' AND comment <> :removed"
        ),
        {"cutoff": replay_cutoff, "removed": REMOVED},
    ).rowcount
    r.whatsapp_inbound = session.execute(
        text("DELETE FROM whatsapp_inbound WHERE received_at <= :cutoff AND status <> 'pending'"),
        {"cutoff": now - timedelta(days=settings.retention_whatsapp_inbound_days)},
    ).rowcount
    from app.admin import audit

    audit.record(
        session,
        actor_id=None,
        actor_label="retention (worker)",
        action="retention.run",
        entity_type="retention",
        after=asdict(r),
    )
    log.info("Retention: %s", r.summary())
    return r
