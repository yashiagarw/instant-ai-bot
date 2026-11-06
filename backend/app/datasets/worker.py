"""The background worker (arq on Redis): dataset jobs and notifications. Start it next to the API:

    docker compose up -d redis
    cd backend && uv run arq app.datasets.worker.WorkerSettings

Dataset jobs: one at a time (the database allows only one queued or running job). The embedding model loads at the
first job that needs it. Jobs left running by a worker that stopped are marked failed at start-up, and queued jobs
are put back on Redis (Redis may have been restarted).

Dispatch (app/requests/dispatch.py, Phase 5.3): every 20 seconds, offers that expired go to the next suggestion
(where auto-offer is on), new requests are auto-offered where it is switched on, and requests nobody accepted in time
are escalated to support.

Retention (app/retention.py, Phase 5.4): daily at 03:00 India time.

Every job logs under the request id of whatever queued it (X-Request-ID, passed as the job's request_id).

Notifications (app/notify): send_notification sends one queued notification (retries and channel fallback),
handle_whatsapp_inbound handles one WhatsApp webhook message, and every minute a sweep re-queues due notifications
and unhandled webhook messages that never reached Redis. They run beside a long dataset job (max_jobs).
"""

from __future__ import annotations

import asyncio
import logging
import os

from arq import cron, func
from arq.connections import RedisSettings

from app.config import get_settings
from app.datasets import jobs
from app.datasets.pipeline import Pipeline
from app.db import make_engine, make_session_factory
from app.notify import inbound as notify_inbound
from app.notify import queue as notify_queue
from app.notify import service as notify
from app.notify.channels import make_channels
from app.observability import logs
from app.observability.errors import init_sentry
from app.observability.logs import clean_request_id, new_request_id, request_id_var

log = logging.getLogger(__name__)


def make_pipeline(settings, factory) -> Pipeline:
    """New builds embed with EMBEDDING_MODEL; evaluating and publishing a version use the model it was built with."""
    from app.knowledge.importer.embed import load_embedder

    def embedder():
        return load_embedder(settings.embedding_model)

    pipe = Pipeline(
        diagnosis_engine=settings.diagnosis_engine,
        work_dir=settings.dataset_upload_dir / "work",
        real_cases_dir=settings.golden_cases_dir,
    )
    pipe.embedder_factory = embedder
    pipe.embedder_loader = load_embedder

    def search(model_name: str):
        if settings.diagnosis_search != "hybrid":
            return None
        from app.diagnosis.search import HybridSearch

        model = pipe.embedder_named(model_name)
        if model is None:
            return None
        return HybridSearch(factory.begin, lambda t: model.encode([t])[0], model.name)

    pipe.search_factory = search
    return pipe


async def startup(ctx: dict) -> None:
    settings = get_settings()
    logs.configure("worker", settings.log_format, settings.log_level)
    init_sentry(settings, "worker")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the model is cached by the importer; never download in a job
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    factory = make_session_factory(engine)
    ctx.update(engine=engine, factory=factory, pipeline=make_pipeline(settings, factory))
    notify.use_settings(settings)
    notify_queue.set_queue(notify_queue.ArqNotifyQueue(settings.redis_url))
    ctx["channels"] = make_channels(settings)
    for channel, provider in ctx["channels"].items():
        if reason := provider.config_error:
            log.warning("Notifications: %s (%s) is not usable: %s. Messages fall back.", channel, provider.name, reason)
    jobs.fail_stale(factory)
    for job_id in jobs.queued(factory):
        await ctx["redis"].enqueue_job(jobs.JOB_FUNCTION, job_id, _job_id=f"dataset-job-{job_id}")


async def shutdown(ctx: dict) -> None:
    if engine := ctx.get("engine"):
        engine.dispose()


def _traced(request_id: str | None, prefix: str) -> None:
    """The job logs under the id of the request that queued it (or a new one for cron runs)."""
    request_id_var.set(clean_request_id(request_id) or new_request_id(prefix))


async def run_dataset_job(ctx: dict, job_id: int, request_id: str | None = None) -> str:
    _traced(request_id, "job-")
    return await asyncio.to_thread(jobs.execute, ctx["factory"], ctx["pipeline"], job_id)


def _send(ctx: dict, notification_id: int) -> str:
    with ctx["factory"].begin() as session:
        return notify.send(session, ctx["channels"], notify.current_settings(), notification_id)


async def send_notification(ctx: dict, notification_id: int, request_id: str | None = None) -> str:
    _traced(request_id, "job-")
    return await asyncio.to_thread(_send, ctx, notification_id)


def _inbound(ctx: dict, inbound_id: int) -> str:
    with ctx["factory"].begin() as session:
        return notify_inbound.handle(session, notify.current_settings(), inbound_id)


async def handle_whatsapp_inbound(ctx: dict, inbound_id: int, request_id: str | None = None) -> str:
    _traced(request_id, "job-")
    return await asyncio.to_thread(_inbound, ctx, inbound_id)


def _sweep(ctx: dict) -> str:
    """Due notifications and pending webhook messages that are not on Redis (it was down, or restarted)."""
    with ctx["factory"].begin() as session:
        rows = notify.due(session)
        ids = notify_inbound.pending(session)
        jobs = [notify_queue.send_job(r.id, r.attempts) for r in rows] + [notify_queue.inbound_job(i) for i in ids]
        for job in jobs:
            notify_queue.after_commit_enqueue(session, job)
    return f"{len(rows)} notifications, {len(ids)} webhook messages queued again"


async def sweep_notifications(ctx: dict) -> str:
    _traced(None, "cron-sweep-")
    return await asyncio.to_thread(_sweep, ctx)


def _dispatch(ctx: dict) -> str:
    """Offers that expired (next suggestion where auto-offer is on), auto-offer for new requests, escalations."""
    from app.requests import dispatch

    with ctx["factory"].begin() as session:
        r = dispatch.sweep(session, notify.current_settings())
    return f"{r.started} auto-offered, {r.expired} offers expired, {r.escalated} escalated"


async def dispatch_requests(ctx: dict) -> str:
    _traced(None, "cron-dispatch-")
    return await asyncio.to_thread(_dispatch, ctx)


def _retention(ctx: dict) -> str:
    """Personal data past its retention period (app/retention.py)."""
    from app import retention

    with ctx["factory"].begin() as session:
        return retention.run(session, notify.current_settings()).summary()


async def apply_retention(ctx: dict) -> str:
    _traced(None, "cron-retention-")
    return await asyncio.to_thread(_retention, ctx)


class WorkerSettings:
    functions = [
        run_dataset_job,
        func(send_notification, timeout=60, keep_result=0),
        func(handle_whatsapp_inbound, timeout=60, keep_result=0),
    ]
    cron_jobs = [
        cron(sweep_notifications, second=0, run_at_startup=True, timeout=60, keep_result=0),
        # Phase 5.3: offer expiry (OFFER_EXPIRY_SECONDS), auto-offer and escalation, every 20 seconds.
        cron(dispatch_requests, second={5, 25, 45}, timeout=60, keep_result=0, unique=True),
        # Phase 5.4: retention, daily at 03:00 India time (21:30 UTC).
        cron(apply_retention, hour=21, minute=30, timeout=600, keep_result=0, unique=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Dataset jobs never run two at a time (a unique index allows one queued or running job); the other slots are
    # for notifications, which must not wait hours behind a full evaluation.
    max_jobs = 4
    max_tries = 1  # a failed job is shown as failed; the admin retries it
    job_timeout = 4 * 3600  # a full eval on a laptop takes long
    keep_result = 3600
    # Liveness key in Redis, refreshed every minute: `arq --check app.datasets.worker.WorkerSettings` (the container
    # health check) fails once the worker stops polling.
    health_check_interval = 60
