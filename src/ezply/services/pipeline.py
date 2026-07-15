import json

from sqlalchemy import select

from ezply.db import async_session_factory
from ezply.models import Job, ResumeProfile, ApplicationAttempt
from ezply.schemas import (
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStepResult,
    PipelineJobResult,
)
from ezply.services.fitting import FitScorer
from ezply.services.registry import get_supported_sources, resolve_source
from ezply.services.ingestion import ingest_source
from ezply.services.apply_queue import create_attempt, update_attempt_result
from ezply.services.assisted_apply import assisted_apply_greenhouse, PlaywrightNotAvailable

fit_scorer = FitScorer()


async def run_pipeline(req: PipelineRunRequest) -> PipelineRunResponse:
    steps: list[PipelineStepResult] = []
    results: list[PipelineJobResult] = []

    # Step 1: Load resume
    async with async_session_factory() as session:
        row = await session.execute(select(ResumeProfile).order_by(ResumeProfile.id.desc()).limit(1))
        resume = row.scalar_one_or_none()

    if resume is None:
        return PipelineRunResponse(
            status="error",
            total_jobs_scored=0,
            jobs_above_threshold=0,
            attempts_queued=0,
            attempts_applied=0,
            threshold=req.threshold,
            steps=[PipelineStepResult(step="load_resume", status="error", detail="No resume saved. Save a resume first.")],
            results=[],
        )
    steps.append(PipelineStepResult(step="load_resume", status="ok", detail=f"Loaded resume: {resume.display_name}"))

    # Step 2: Import from sources (optional — off by default)
    if req.import_first:
        sources_to_run = req.source_names or [s.name for s in get_supported_sources()]
        for source_name in sources_to_run:
            source = resolve_source(source_name)
            if source is None:
                steps.append(PipelineStepResult(step="import", status="skipped", detail=f"Unknown source: {source_name}"))
                continue
            try:
                import_result = await ingest_source(source)
                steps.append(PipelineStepResult(
                    step="import", status="ok",
                    detail=f"{source_name}: imported {import_result.imported_count}, skipped {import_result.skipped_count}"
                ))
            except Exception as e:
                steps.append(PipelineStepResult(step="import", status="error", detail=f"{source_name}: {e}"))
    else:
        steps.append(PipelineStepResult(step="import", status="skipped", detail="Import skipped (import_first=false). Use Import tab or set import_first=true."))

    # Step 3: Find jobs without attempts
    async with async_session_factory() as session:
        stmt = (
            select(Job)
            .outerjoin(ApplicationAttempt, Job.id == ApplicationAttempt.job_id)
            .where(ApplicationAttempt.id.is_(None))
            .order_by(Job.posted_at.desc().nulls_last(), Job.id.desc())
            .limit(req.max_jobs)
        )
        jobs = (await session.execute(stmt)).scalars().all()

    if not jobs:
        steps.append(PipelineStepResult(step="score", status="ok", detail="No un-attempted jobs to score. Import jobs first."))
        return PipelineRunResponse(
            status="ok",
            total_jobs_scored=0,
            jobs_above_threshold=0,
            attempts_queued=0,
            attempts_applied=0,
            threshold=req.threshold,
            steps=steps,
            results=[],
        )

    # Step 4: Score and queue
    queued_count = 0
    for job in jobs:
        fit = fit_scorer.score(resume.resume_text, job.description, mode="auto")
        pr = PipelineJobResult(
            job_id=job.id,
            title=job.title,
            company=job.company,
            score=fit.score,
            scoring_mode=fit.scoring_mode,
            summary=fit.summary,
        )
        if fit.score >= req.threshold:
            try:
                attempt = await create_attempt(job.id)
                pr.attempt_id = attempt.id
                queued_count += 1
            except Exception as e:
                pr.apply_status = f"queue_failed: {e}"
        results.append(pr)

    steps.append(PipelineStepResult(
        step="score", status="ok",
        detail=f"Scored {len(jobs)} jobs, {queued_count} above threshold {req.threshold}, queued as attempts."
    ))

    # Step 5: Apply (if enabled)
    applied_count = 0
    if req.apply and req.passphrase:
        for pr in results:
            if pr.attempt_id is None:
                continue
            job = next((j for j in jobs if j.id == pr.job_id), None)
            if job is None or job.source != "greenhouse":
                pr.apply_status = "skipped (non-greenhouse)"
                continue
            try:
                apply_result = await assisted_apply_greenhouse(job.source_url, req.passphrase, confirm_submit=False)
                await update_attempt_result(pr.attempt_id, "completed", json.dumps(apply_result))
                pr.applied = True
                pr.apply_status = "completed"
                applied_count += 1
            except PlaywrightNotAvailable:
                pr.apply_status = "skipped (playwright not available)"
            except Exception as e:
                pr.apply_status = f"failed: {e}"
                await update_attempt_result(pr.attempt_id, "failed", str(e))

        steps.append(PipelineStepResult(step="apply", status="ok", detail=f"Attempted apply on {applied_count} Greenhouse jobs."))
    else:
        steps.append(PipelineStepResult(step="apply", status="skipped", detail="Auto-apply disabled (set apply=true and provide passphrase)."))

    above = sum(1 for r in results if r.score >= req.threshold)
    return PipelineRunResponse(
        status="ok",
        total_jobs_scored=len(results),
        jobs_above_threshold=above,
        attempts_queued=queued_count,
        attempts_applied=applied_count,
        threshold=req.threshold,
        steps=steps,
        results=results,
    )
