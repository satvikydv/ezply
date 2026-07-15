import asyncio
from sqlalchemy import select
from celery import shared_task

from ezply.db import async_session_factory
from ezply.models import Company, RawJob, ScoredJob
from ezply.services.ingestion import ingest_source
from ezply.services.registry import get_supported_sources
from ezply.services.embeddings import embedding_service
from ezply.services.fitting import FitScorer

# Need a helper to run async code in Celery which is sync by default
def run_async(coro):
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # If there's an existing running loop, use nest_asyncio or create task
        # Since celery processes usually don't have running loops, we can just run_until_complete
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    else:
        return loop.run_until_complete(coro)


@shared_task
def poll_all_companies():
    """Polls all active companies and fetches their jobs."""
    async def _poll():
        async with async_session_factory() as session:
            # For this MVP, we assume all supported sources match active companies
            sources = get_supported_sources()
            for source in sources:
                res = await ingest_source(source)
                print(f"Ingested {res['source_name']}: {res['imported_count']} new, {res['skipped_count']} skipped")
                
                # In a real app we'd dispatch filter_and_score_job for each NEW job here
                # But since ingest_source doesn't return the raw job IDs, we'll queue un-scored jobs
            
            # Find unscored jobs and queue them
            unscored = await session.execute(
                select(RawJob).outerjoin(ScoredJob).where(ScoredJob.id == None)
            )
            for job in unscored.scalars().all():
                filter_and_score_job.delay(job.id)

    run_async(_poll())


@shared_task
def filter_and_score_job(raw_job_id: int):
    """Embeds the job, filters by relevance, and scores with Claude."""
    async def _process():
        async with async_session_factory() as session:
            job = await session.get(RawJob, raw_job_id)
            if not job:
                return

            # Dummy user resume for now (we would fetch from DB)
            dummy_resume = "Software Engineer with 5 years of Python, FastAPI, and Postgres."
            
            job_emb = embedding_service.embed_job(job.title, job.description_raw)
            res_emb = embedding_service.embed_resume(dummy_resume)
            
            # Simple threshold check
            similarity = embedding_service.compute_similarity(job_emb, res_emb)
            
            if similarity < 0.2:
                # Filtered out
                sj = ScoredJob(
                    raw_job_id=job.id,
                    embedding_score=similarity,
                    status="filtered_out"
                )
                session.add(sj)
                await session.commit()
                return

            # Call Claude API
            scorer = FitScorer()
            score_res = scorer.score(dummy_resume, job.description_raw)
            
            sj = ScoredJob(
                raw_job_id=job.id,
                embedding_score=similarity,
                fit_score=score_res.get("fit_score", 0),
                reasoning=score_res.get("reasoning", ""),
                key_requirements=score_res.get("key_requirements", []),
                concerns=score_res.get("concerns", []),
                status="scored"
            )
            session.add(sj)
            await session.commit()
            
    run_async(_process())
