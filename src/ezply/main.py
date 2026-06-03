from sqlalchemy import select
from fastapi import FastAPI, HTTPException

from ezply.db import async_session_factory, init_db
from ezply.models import Job, ResumeProfile
from ezply.schemas import (
    FitScoreRequest,
    FitScoreResponse,
    ImportJobsResponse,
    JobListResponse,
    JobRankRequest,
    JobRankResponse,
    JobResponse,
    RankedJobResponse,
    ResumeProfileRequest,
    ResumeProfileResponse,
    ResumeProfileUpsertResponse,
    AutofillProfileRequest,
    AutofillProfileResponse,
    AutofillExportRequest,
    AutofillExportResponse,
    AssistedApplyRequest,
    AssistedApplyResponse,
    SourceListResponse,
    SourceResponse,
)
from ezply.services.ingestion import ingest_source
from ezply.services.fitting import FitScorer
from ezply.services.registry import get_supported_sources, resolve_source
from ezply.settings import get_settings
from ezply.services.autofill import save_autofill_profile, load_autofill_profile
from ezply.services.assisted_apply import assisted_apply_greenhouse, PlaywrightNotAvailable

app = FastAPI(title="Ezply", version="0.1.0")
fit_scorer = FitScorer()


def _serialize_resume(resume: ResumeProfile) -> ResumeProfileResponse:
    return ResumeProfileResponse(id=resume.id, display_name=resume.display_name, resume_text=resume.resume_text)


def _serialize_autofill(autofill: "AutofillProfile") -> AutofillProfileResponse:
    return AutofillProfileResponse(id=autofill.id, display_name=autofill.display_name, created_at=autofill.created_at.isoformat())


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "environment": settings.environment}


@app.get("/sources", response_model=SourceListResponse)
def list_sources() -> SourceListResponse:
    return SourceListResponse(sources=[SourceResponse.model_validate(source) for source in get_supported_sources()])


@app.post("/jobs/import/{source_name}", response_model=ImportJobsResponse)
async def import_jobs(source_name: str) -> ImportJobsResponse:
    source = resolve_source(source_name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Unsupported source: {source_name}")

    return await ingest_source(source)


@app.get("/jobs", response_model=JobListResponse)
async def list_jobs() -> JobListResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(Job).order_by(Job.id.desc()))
        jobs = result.scalars().all()

    return JobListResponse(
        jobs=[
            JobResponse(
                id=job.id,
                title=job.title,
                company=job.company,
                location=job.location,
                seniority=job.seniority,
                source=job.source,
                source_url=job.source_url,
                description=job.description,
            )
            for job in jobs
        ]
    )


@app.get("/resume", response_model=ResumeProfileResponse)
async def get_resume() -> ResumeProfileResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(ResumeProfile).order_by(ResumeProfile.id.desc()).limit(1))
        resume = result.scalar_one_or_none()

    if resume is None:
        raise HTTPException(status_code=404, detail="No resume profile saved yet")

    return _serialize_resume(resume)


@app.put("/resume", response_model=ResumeProfileUpsertResponse)
async def upsert_resume(request: ResumeProfileRequest) -> ResumeProfileUpsertResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(ResumeProfile).order_by(ResumeProfile.id.desc()).limit(1))
        resume = result.scalar_one_or_none()

        if resume is None:
            resume = ResumeProfile(display_name=request.display_name, resume_text=request.resume_text)
            session.add(resume)
        else:
            resume.display_name = request.display_name
            resume.resume_text = request.resume_text

        await session.commit()
        await session.refresh(resume)

    return ResumeProfileUpsertResponse(resume=_serialize_resume(resume))


@app.put("/autofill", response_model=AutofillProfileResponse)
async def upsert_autofill(request: AutofillProfileRequest) -> AutofillProfileResponse:
    try:
        autofill = await save_autofill_profile(request.display_name, request.profile, request.passphrase)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _serialize_autofill(autofill)


@app.post("/autofill/export", response_model=AutofillExportResponse)
async def export_autofill(request: AutofillExportRequest) -> AutofillExportResponse:
    try:
        profile = await load_autofill_profile(request.passphrase)
    except ValueError:
        raise HTTPException(status_code=404, detail="No autofill profile saved")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid passphrase or corrupt data")

    return AutofillExportResponse(profile=profile)


@app.post("/fit/score", response_model=FitScoreResponse)
def score_fit(request: FitScoreRequest) -> FitScoreResponse:
    result = fit_scorer.score(request.resume_text, request.job_text)
    return FitScoreResponse(
        score=result.score,
        summary=result.summary,
        matched_keywords=result.matched_keywords,
        missing_keywords=result.missing_keywords,
    )


@app.post("/jobs/rank", response_model=JobRankResponse)
async def rank_jobs(request: JobRankRequest) -> JobRankResponse:
    resume_text = request.resume_text
    if resume_text is None or not resume_text.strip():
        async with async_session_factory() as session:
            result = await session.execute(select(ResumeProfile).order_by(ResumeProfile.id.desc()).limit(1))
            saved_resume = result.scalar_one_or_none()

        if saved_resume is None:
            raise HTTPException(status_code=400, detail="Provide resume_text or save a resume profile first")

        resume_text = saved_resume.resume_text

    async with async_session_factory() as session:
        result = await session.execute(select(Job).order_by(Job.id.desc()).limit(request.limit))
        jobs = result.scalars().all()

    ranked_jobs = []
    for job in jobs:
        result = fit_scorer.score(resume_text, job.description)
        ranked_jobs.append(
            RankedJobResponse(
                job=JobResponse(
                    id=job.id,
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    seniority=job.seniority,
                    source=job.source,
                    source_url=job.source_url,
                    description=job.description,
                ),
                fit_score=FitScoreResponse(
                    score=result.score,
                    summary=result.summary,
                    matched_keywords=result.matched_keywords,
                    missing_keywords=result.missing_keywords,
                ),
            )
        )

    ranked_jobs.sort(key=lambda item: item.fit_score.score, reverse=True)
    return JobRankResponse(ranked_jobs=ranked_jobs)


@app.post("/apply/assist", response_model=AssistedApplyResponse)
async def assist_apply(request: AssistedApplyRequest) -> AssistedApplyResponse:
    async with async_session_factory() as session:
        job = await session.get(Job, request.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

    try:
        result = await assisted_apply_greenhouse(job.source_url, request.passphrase, confirm_submit=request.confirm_submit)
    except PlaywrightNotAvailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AssistedApplyResponse(job_id=request.job_id, job_url=job.source_url, filled=result.get("filled", {}), ready_to_submit=result.get("ready_to_submit", False))
