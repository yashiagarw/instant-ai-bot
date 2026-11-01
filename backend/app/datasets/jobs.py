"""Background jobs of the dataset pipeline: a dataset_jobs row (status, progress, log) plus a message on Redis for
the arq worker (app.datasets.worker). Only one job may be queued or running at a time (a unique index), so two
publishes can never race. The worker does the work in one transaction and reports progress in its own short ones,
so the admin page can show it while the job runs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.datasets import pipeline as P
from app.datasets.steps import StepError
from app.knowledge.models import DatasetJob, DatasetVersion, JobKind, JobStatus

log = logging.getLogger(__name__)
JOB_FUNCTION = "run_dataset_job"
LOG_LINES = 40


class JobBusy(Exception):
    """Another dataset job is queued or running."""


class QueueUnavailable(Exception):
    """Redis cannot be reached."""


class JobQueue(Protocol):
    def enqueue(self, job_id: int) -> None: ...


class ArqQueue:
    """Puts the job on Redis for the worker. Fails fast when Redis is down (the API then says so)."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url

    def enqueue(self, job_id: int) -> None:
        from arq import create_pool
        from arq.connections import RedisSettings

        async def go() -> None:
            settings = RedisSettings.from_dsn(self.redis_url)
            settings.conn_timeout, settings.conn_retries = 2, 0
            pool = await create_pool(settings)
            try:
                await pool.enqueue_job(JOB_FUNCTION, job_id, _job_id=f"dataset-job-{job_id}")
            finally:
                await pool.aclose()

        try:
            asyncio.run(go())
        except Exception as e:  # redis.exceptions.ConnectionError, OSError, timeouts
            raise QueueUnavailable(str(e)) from e


def create_job(
    session: Session,
    kind: JobKind,
    version_id: int | None,
    actor_id,
    actor_label: str,
    params: dict | None = None,
) -> DatasetJob:
    """Insert a queued job (committed by the caller). Raises JobBusy while another one is queued or running."""
    active = session.scalar(select(DatasetJob).where(DatasetJob.status.in_([JobStatus.queued, JobStatus.running])))
    if active is not None:
        raise JobBusy(f"Another job is {active.status} ({active.kind}, job {active.id}). Try again when it finishes.")
    job = DatasetJob(
        kind=kind,
        dataset_version_id=version_id,
        params=params or {},
        created_by_id=actor_id,
        created_by=actor_label,
        step="waiting for the worker",
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError as e:  # two requests at the same moment
        raise JobBusy("Another job was just started. Try again when it finishes.") from e
    return job


class Reporter:
    """Writes progress to the job row in short transactions of its own."""

    def __init__(self, factory: Callable[[], Session], job_id: int):
        self.factory, self.job_id = factory, job_id
        self._last = (-1, "")

    def _update(self, **values) -> None:
        with self.factory() as s, s.begin():
            s.execute(update(DatasetJob).where(DatasetJob.id == self.job_id).values(**values))

    def progress(self, step: str, fraction: float) -> None:
        pct = max(0, min(99, int(fraction * 100)))
        if (pct, step) == self._last:
            return
        self._last = (pct, step)
        with self.factory() as s, s.begin():
            job = s.get(DatasetJob, self.job_id)
            if job is not None:
                job.progress, job.step = pct, step
                if not job.log or job.log[-1].get("step") != step:
                    stamp = datetime.now(UTC).isoformat(timespec="seconds")
                    job.log = [*job.log, {"at": stamp, "step": step}][-LOG_LINES:]

    def finish(self, result: dict) -> None:
        values = {"status": JobStatus.succeeded, "progress": 100, "step": "done", "result": result}
        if result.get("version_id"):
            values["dataset_version_id"] = result["version_id"]
        self._update(**values, finished_at=datetime.now(UTC))

    def fail(self, message: str) -> None:
        self._update(status=JobStatus.failed, error=message[:2000], finished_at=datetime.now(UTC))


def execute(factory: Callable[[], Session], pipe: P.Pipeline, job_id: int) -> str:
    """Run one queued job (the worker calls this in a thread). Returns its final status."""
    with factory() as s, s.begin():
        job = s.get(DatasetJob, job_id, with_for_update=True)
        if job is None or job.status != JobStatus.queued:
            return str(job.status) if job else "missing"
        job.status, job.started_at, job.step = JobStatus.running, datetime.now(UTC), "starting"
        kind, version_id, params = job.kind, job.dataset_version_id, dict(job.params or {})
        actor = P.Actor(job.created_by_id, job.created_by or "worker")
    reporter = Reporter(factory, job_id)
    try:
        with factory() as session, session.begin():
            version = session.get(DatasetVersion, version_id) if version_id else None
            if version is None:
                raise P.PipelineError("The dataset version of this job no longer exists.")
            if kind == JobKind.build:
                result = P.build(session, pipe, version, reporter.progress)
            elif kind == JobKind.eval:
                result = P.evaluate(session, pipe, version, bool(params.get("full")), reporter.progress)
            elif kind == JobKind.publish:
                result = P.publish(session, pipe, version, actor, reporter.progress, params.get("override_reason"))
            else:
                result = P.rollback(session, pipe, version, actor, reporter.progress, params.get("category"))
        reporter.finish(result)
        return "succeeded"
    except (P.PipelineError, StepError) as e:
        _failed(factory, kind, version_id, str(e))
        reporter.fail(str(e))
    except Exception as e:
        log.exception("dataset job %s failed", job_id)
        message = f"Unexpected error: {type(e).__name__}: {e}"
        _failed(factory, kind, version_id, message)
        reporter.fail(message)
    return "failed"


def _failed(factory: Callable[[], Session], kind: JobKind, version_id: int | None, message: str) -> None:
    """A failed build leaves its draft with the error (shown instead of a validation report)."""
    if kind != JobKind.build or version_id is None:
        return
    with factory() as s, s.begin():
        version = s.get(DatasetVersion, version_id)
        if version is not None:
            version.validation = {"upload": (version.validation or {}).get("upload"), "error": message[:2000]}


def fail_stale(factory: Callable[[], Session]) -> list[int]:
    """Jobs left running by a worker that stopped (called when the worker starts)."""
    with factory() as s, s.begin():
        jobs = s.scalars(select(DatasetJob).where(DatasetJob.status == JobStatus.running)).all()
        for job in jobs:
            job.status, job.finished_at = JobStatus.failed, datetime.now(UTC)
            job.error = "The worker stopped while this job was running. Start it again and retry."
        return [j.id for j in jobs]


def queued(factory: Callable[[], Session]) -> list[int]:
    with factory() as s:
        return list(s.scalars(select(DatasetJob.id).where(DatasetJob.status == JobStatus.queued)))
