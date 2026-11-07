"""Background jobs inside the API process (BACKGROUND_JOBS=api), for hosts without a separate worker, such as the free
demo on Render (docs/deploy-free-demo.md). The docker-compose deployments keep the arq worker (BACKGROUND_JOBS=worker,
the default) and never start this.

What the worker's cron jobs do (app/datasets/worker.py), on threads here:
- notifications: sent right after the transaction that queued them commits (InProcessQueue), and swept every minute
  for due retries and deferred ones;
- dispatch: expired offers, auto-offer, escalations, every 20 seconds;
- retention: once at start and every day at 21:30 UTC.
Each tick takes a Postgres advisory lock for its job first, so several API processes never run the same tick twice.
Dataset jobs are not run here: they need the worker (DATASET_JOBS_ENABLED=false in the demo).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.notify import inbound as notify_inbound
from app.notify import queue as notify_queue
from app.notify import service as notify

log = logging.getLogger(__name__)

SWEEP_SECONDS = 60
DISPATCH_SECONDS = 20
RETENTION_AT_UTC = (21, 30)
# pg_advisory_xact_lock keys, one per job (any constant unique to this app).
LOCK_SWEEP, LOCK_DISPATCH, LOCK_RETENTION = 73_100_501, 73_100_502, 73_100_503


class InProcessQueue:
    """The notify queue (app.notify.queue) without Redis: each job runs on a small thread pool right after the commit
    that queued it. Deferred jobs (a retry later) are left to the sweep, which sends them when they are due."""

    def __init__(self, factory: sessionmaker[Session], channels: dict, executor: ThreadPoolExecutor):
        self.factory, self.channels, self.executor = factory, channels, executor
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def enqueue(self, jobs: list[tuple[str, int, str, datetime | None]]) -> None:
        now = datetime.now(UTC)
        for function, arg, job_id, when in jobs:
            if when is not None and when > now:
                continue  # the sweep picks it up when due
            with self._lock:
                if job_id in self._running:
                    continue
                self._running.add(job_id)
            self.executor.submit(self._run, function, arg, job_id)

    def _run(self, function: str, arg: int, job_id: str) -> None:
        try:
            with self.factory.begin() as session:
                if function == notify_queue.SEND_FUNCTION:
                    notify.send(session, self.channels, notify.current_settings(), arg)
                elif function == notify_queue.INBOUND_FUNCTION:
                    notify_inbound.handle(session, notify.current_settings(), arg)
        except Exception:
            log.exception("in-process job %s failed (the sweep retries notifications)", job_id)
        finally:
            with self._lock:
                self._running.discard(job_id)


def _locked(session: Session, key: int) -> bool:
    return bool(session.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": key}))


def sweep(factory: sessionmaker[Session]) -> str:
    """Due notifications and pending webhook messages (as the worker's sweep_notifications)."""
    with factory.begin() as session:
        if not _locked(session, LOCK_SWEEP):
            return "another process is sweeping"
        rows = notify.due(session)
        ids = notify_inbound.pending(session)
        jobs = [notify_queue.send_job(r.id, r.attempts) for r in rows] + [notify_queue.inbound_job(i) for i in ids]
        for job in jobs:
            notify_queue.after_commit_enqueue(session, job)
    return f"{len(rows)} notifications, {len(ids)} webhook messages queued"


def dispatch_tick(factory: sessionmaker[Session]) -> str:
    """Expired offers, auto-offer, escalations (as the worker's dispatch_requests)."""
    from app.requests import dispatch

    with factory.begin() as session:
        if not _locked(session, LOCK_DISPATCH):
            return "another process is dispatching"
        r = dispatch.sweep(session, notify.current_settings())
    return f"{r.started} auto-offered, {r.expired} offers expired, {r.escalated} escalated"


def retention_tick(factory: sessionmaker[Session]) -> str:
    """Personal data past its retention period (as the worker's apply_retention)."""
    from app import retention

    with factory.begin() as session:
        if not _locked(session, LOCK_RETENTION):
            return "another process is applying retention"
        return retention.run(session, notify.current_settings()).summary()


class BackgroundRunner:
    """Runs the ticks on one daemon thread until stop(). Errors are logged and the loop goes on."""

    def __init__(self, settings: Settings, factory: sessionmaker[Session]):
        from app.notify.channels import make_channels

        self.settings, self.factory = settings, factory
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notify")
        self.queue = InProcessQueue(factory, make_channels(settings), self.executor)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        notify_queue.set_queue(self.queue)
        self._thread = threading.Thread(target=self._loop, name="background-jobs", daemon=True)
        self._thread.start()
        log.info("background jobs run in the API process (BACKGROUND_JOBS=api)")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _tick(self, name: str, fn: Callable[[sessionmaker[Session]], str]) -> None:
        try:
            result = fn(self.factory)
            log.debug("%s: %s", name, result)
        except Exception:
            log.exception("background %s failed", name)

    def _loop(self) -> None:
        self._tick("retention", retention_tick)  # also at start: a free server sleeps and may miss 21:30
        last_sweep = last_dispatch = 0.0
        last_retention_day = datetime.now(UTC).date()
        clock = 0.0
        while not self._stop.wait(timeout=5):
            clock += 5
            if clock - last_dispatch >= DISPATCH_SECONDS:
                last_dispatch = clock
                self._tick("dispatch", dispatch_tick)
            if clock - last_sweep >= SWEEP_SECONDS:
                last_sweep = clock
                self._tick("notification sweep", sweep)
            now = datetime.now(UTC)
            if now.date() != last_retention_day and (now.hour, now.minute) >= RETENTION_AT_UTC:
                last_retention_day = now.date()
                self._tick("retention", retention_tick)
