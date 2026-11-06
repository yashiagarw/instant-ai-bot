"""Putting notifications on the worker's queue. The notifications table is the source of truth (an outbox): rows are
written in the caller's transaction, and only after that transaction commits are they put on Redis for the arq
worker (app.datasets.worker runs send_notification). If Redis is down then, nothing is lost: the worker's sweep
(every minute) puts due rows on the queue again. Job ids are "notify-<id>-<attempt>", so a row is never queued twice
for the same attempt, and the worker locks the row before sending.

Tests replace the queue with set_queue(RecordingQueue()) (or a queue that sends inline).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import event
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
SEND_FUNCTION = "send_notification"
INBOUND_FUNCTION = "handle_whatsapp_inbound"
PENDING_KEY = "notify_pending"


class NotifyQueue(Protocol):
    def enqueue(self, jobs: list[tuple[str, int, str, datetime | None]]) -> None: ...


class ArqNotifyQueue:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url

    def enqueue(self, jobs: list[tuple[str, int, str, datetime | None]]) -> None:
        from arq import create_pool
        from arq.connections import RedisSettings

        from app.observability.logs import current_request_id

        request_id = current_request_id()  # the request (or job) that queued them: the job logs under the same id

        async def go() -> None:
            settings = RedisSettings.from_dsn(self.redis_url)
            settings.conn_timeout, settings.conn_retries = 2, 0
            pool = await create_pool(settings)
            try:
                for function, arg, job_id, when in jobs:
                    await pool.enqueue_job(function, arg, request_id=request_id, _job_id=job_id, _defer_until=when)
            finally:
                await pool.aclose()

        try:
            asyncio.run(go())
        except Exception as e:  # Redis down: the worker's sweep sends them later
            log.warning("Notifications stored but not queued (Redis: %s); the worker's sweep will send them", e)


class RecordingQueue:
    """Remembers what would have been queued (tests)."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, int, str, datetime | None]] = []

    def enqueue(self, jobs: list[tuple[str, int, str, datetime | None]]) -> None:
        self.jobs.extend(jobs)


_queue: NotifyQueue | None = None


def set_queue(queue: NotifyQueue | None) -> None:
    global _queue
    _queue = queue


def get_queue() -> NotifyQueue:
    global _queue
    if _queue is None:
        from app.config import get_settings

        _queue = ArqNotifyQueue(get_settings().redis_url)
    return _queue


def send_job(notification_id: int, attempt: int, when: datetime | None = None) -> tuple[str, int, str, datetime | None]:
    if when is not None and when <= datetime.now(UTC):
        when = None
    return (SEND_FUNCTION, notification_id, f"notify-{notification_id}-{attempt}", when)


def inbound_job(inbound_id: int) -> tuple[str, int, str, None]:
    return (INBOUND_FUNCTION, inbound_id, f"wa-inbound-{inbound_id}", None)


def after_commit_enqueue(session: Session, job: tuple[str, int, str, datetime | None]) -> None:
    """Queue a job once this session's transaction commits (dropped if it rolls back)."""
    session.info.setdefault(PENDING_KEY, []).append(job)


@event.listens_for(Session, "after_commit")
def _flush_pending(session: Session) -> None:
    jobs = session.info.pop(PENDING_KEY, None)
    if jobs:
        get_queue().enqueue(jobs)


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop(PENDING_KEY, None)
