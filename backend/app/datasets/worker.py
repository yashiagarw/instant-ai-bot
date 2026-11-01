"""The background worker for dataset jobs (arq on Redis). Start it next to the API:

    docker compose up -d redis
    cd backend && uv run arq app.datasets.worker.WorkerSettings

One job at a time. The embedding model loads at the first job that needs it. Jobs left running by a worker that
stopped are marked failed at start-up, and queued jobs are put back on Redis (Redis may have been restarted).
"""

from __future__ import annotations

import asyncio
import os

from arq.connections import RedisSettings

from app.config import get_settings
from app.datasets import jobs
from app.datasets.pipeline import Pipeline
from app.db import make_engine, make_session_factory


def make_pipeline(settings, factory) -> Pipeline:
    def embedder():
        from app.knowledge.importer.embed import SentenceTransformerEmbedder

        return SentenceTransformerEmbedder()

    pipe = Pipeline(diagnosis_engine=settings.diagnosis_engine, work_dir=settings.dataset_upload_dir / "work")
    pipe.embedder_factory = embedder

    def search():
        if settings.diagnosis_search != "hybrid" or pipe.embedder is None:
            return None
        from app.diagnosis.search import HybridSearch

        model = pipe.embedder
        return HybridSearch(factory.begin, lambda t: model.encode([t])[0], model.name)

    pipe.search_factory = search
    return pipe


async def startup(ctx: dict) -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the model is cached by the importer; never download in a job
    settings = get_settings()
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    factory = make_session_factory(engine)
    ctx.update(engine=engine, factory=factory, pipeline=make_pipeline(settings, factory))
    jobs.fail_stale(factory)
    for job_id in jobs.queued(factory):
        await ctx["redis"].enqueue_job(jobs.JOB_FUNCTION, job_id, _job_id=f"dataset-job-{job_id}")


async def shutdown(ctx: dict) -> None:
    if engine := ctx.get("engine"):
        engine.dispose()


async def run_dataset_job(ctx: dict, job_id: int) -> str:
    return await asyncio.to_thread(jobs.execute, ctx["factory"], ctx["pipeline"], job_id)


class WorkerSettings:
    functions = [run_dataset_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1  # one job at a time (the database allows only one active job anyway)
    max_tries = 1  # a failed job is shown as failed; the admin retries it
    job_timeout = 4 * 3600  # a full eval on a laptop takes long
    keep_result = 3600
