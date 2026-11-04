"""The background worker (arq on Redis): dataset jobs and notifications. Start it next to the API:

    docker compose up -d redis
    cd backend && uv run arq app.datasets.worker.WorkerSettings

Dataset jobs: one at a time (the database allows only one queued or running job). The embedding model loads at the
first job that needs it. Jobs left running by a worker that stopped are marked failed at start-up, and queued jobs
are put back on Redis (Redis may have been restarted).

Notifications (app/notify): send_notification sends one queued notification (retries and channel fallback),
handle_whatsapp_inbound handles one WhatsApp webhook message, and every minute a sweep re-queues due notifications
and unhandled webhook messages that never reached Redis. They run beside a long dataset job (max_jobs).
"""

from __future__ import annotations

import asyncio
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
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the model is cached by the importer; never download in a job
    settings = get_settings()
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    factory = make_session_factory(engine)
    ctx.update(engine=engine, factory=factory, pipeline=make_pipeline(settings, factory))
    notify.use_settings(settings)
    notify_queue.set_queue(notify_queue.ArqNotifyQueue(settings.redis_url))
    ctx["channels"] = make_channels(settings)
    for channel, provider in ctx["channels"].items():
        if reason := provider.config_error:
            print(f"Notifications: {channel} ({provider.name}) is not usable: {reason}. Messages fall back.")
    jobs.fail_stale(factory)
    for job_id in jobs.queued(factory):
        await ctx["redis"].enqueue_job(jobs.JOB_FUNCTION, job_id, _job_id=f"dataset-job-{job_id}")


async def shutdown(ctx: dict) -> None:
    if engine := ctx.get("engine"):
        engine.dispose()


async def run_dataset_job(ctx: dict, job_id: int) -> str:
    return await asyncio.to_thread(jobs.execute, ctx["factory"], ctx["pipeline"], job_id)


def _send(ctx: dict, notification_id: int) -> str:
    with ctx["factory"].begin() as session:
        return notify.send(session, ctx["channels"], notify.current_settings(), notification_id)


async def send_notification(ctx: dict, notification_id: int) -> str:
    return await asyncio.to_thread(_send, ctx, notification_id)


def _inbound(ctx: dict, inbound_id: int) -> str:
    with ctx["factory"].begin() as session:
        return notify_inbound.handle(session, notify.current_settings(), inbound_id)


async def handle_whatsapp_inbound(ctx: dict, inbound_id: int) -> str:
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
    return await asyncio.to_thread(_sweep, ctx)


class WorkerSettings:
    functions = [
        run_dataset_job,
        func(send_notification, timeout=60, keep_result=0),
        func(handle_whatsapp_inbound, timeout=60, keep_result=0),
    ]
    cron_jobs = [cron(sweep_notifications, second=0, run_at_startup=True, timeout=60, keep_result=0)]
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
