from sqlalchemy import select
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

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
    AttemptCreateRequest,
    AttemptResponse,
    AttemptListResponse,
    SourceListResponse,
    SourceResponse,
)
from ezply.services.ingestion import ingest_source
from ezply.services.fitting import FitScorer
from ezply.services.registry import get_supported_sources, resolve_source
from ezply.settings import get_settings
from ezply.services.autofill import save_autofill_profile, load_autofill_profile
from ezply.services.assisted_apply import assisted_apply_greenhouse, PlaywrightNotAvailable
from ezply.services.apply_queue import create_attempt, list_attempts, get_attempt, update_attempt_result

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


    @app.get("/jobs/search", response_model=JobListResponse)
    async def search_jobs(role: str | None = None, location: str | None = None, limit: int = 100) -> JobListResponse:
            async with async_session_factory() as session:
                    result = await session.execute(select(Job).order_by(Job.id.desc()).limit(limit))
                    jobs = result.scalars().all()

            if not role and not location:
                    return JobListResponse(jobs=[
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
                    ])

            role_terms = [t.strip().lower() for t in role.split(",") if t.strip()] if role else []

            def matches(job):
                    text = " ".join([job.title or "", job.company or "", job.description or ""]).lower()
                    if location and job.location:
                            if location.lower() not in (job.location or "").lower():
                                    return False
                    if not role_terms:
                            return True
                    return any(term in text for term in role_terms)

            filtered = [job for job in jobs if matches(job)]

            return JobListResponse(jobs=[
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
                    for job in filtered
            ])


    @app.get("/ui", response_class=HTMLResponse)
    def ui() -> HTMLResponse:
            html = """
            <!doctype html>
            <html>
                <head>
                    <meta charset="utf-8" />
                    <title>Ezply — Jobs UI</title>
                    <style>
                        body { font-family: system-ui, sans-serif; padding: 20px; }
                        input, button { padding: 8px; margin: 4px; }
                        .job { border: 1px solid #eee; padding: 8px; margin: 8px 0; }
                    </style>
                </head>
                <body>
                    <h1>Ezply — Search Jobs</h1>
                    <div>
                        <label>Role keywords (comma-separated):</label>
                        <input id="role" placeholder="e.g. data engineer, frontend" size="40" />
                        <label>Location:</label>
                        <input id="location" placeholder="optional" size="20" />
                        <button id="search">Search</button>
                    </div>
                    <div>
                        <label>Passphrase (optional for enqueue):</label>
                        <input id="passphrase" type="password" size="30" />
                    </div>
                    <div id="results"></div>

                    <script>
                    async function search() {
                        const role = document.getElementById('role').value;
                        const location = document.getElementById('location').value;
                        const q = new URLSearchParams();
                        if (role) q.set('role', role);
                        if (location) q.set('location', location);
                        const res = await fetch('/jobs/search?' + q.toString());
                        const data = await res.json();
                        const container = document.getElementById('results');
                        container.innerHTML = '';
                        for (const job of data.jobs) {
                            const div = document.createElement('div');
                            div.className = 'job';
                            div.innerHTML = `<strong>${job.title}</strong> — ${job.company} <br/> <small>${job.location || ''} • ${job.source}</small><p>${job.description.slice(0,300).replace(/\n/g,' ')}...</p>`;
                            const btn = document.createElement('button');
                            btn.textContent = 'Enqueue Apply';
                            btn.onclick = async () => {
                                const pass = document.getElementById('passphrase').value || '';
                                const r = await fetch('/apply/queue', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: job.id, passphrase: pass})});
                                if (r.ok) {
                                    alert('Enqueued attempt for job ' + job.id);
                                } else {
                                    alert('Failed to enqueue: ' + r.statusText);
                                }
                            };
                            div.appendChild(btn);
                            container.appendChild(div);
                        }
                    }
                    document.getElementById('search').addEventListener('click', search);
                    </script>
                </body>
            </html>
            """
            return HTMLResponse(content=html)


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


@app.post("/apply/queue", response_model=AttemptResponse)
async def enqueue_apply(request: AttemptCreateRequest) -> AttemptResponse:
    async with async_session_factory() as session:
        job = await session.get(Job, request.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

    attempt = await create_attempt(request.job_id)
    return AttemptResponse(
        id=attempt.id,
        job_id=attempt.job_id,
        status=attempt.status,
        created_at=attempt.created_at.isoformat(),
        updated_at=attempt.updated_at.isoformat() if attempt.updated_at else None,
        result=None,
    )


@app.get("/apply/attempts", response_model=AttemptListResponse)
async def list_apply_attempts() -> AttemptListResponse:
    attempts = await list_attempts()
    return AttemptListResponse(
        attempts=[
            AttemptResponse(
                id=a.id,
                job_id=a.job_id,
                status=a.status,
                created_at=a.created_at.isoformat(),
                updated_at=a.updated_at.isoformat() if a.updated_at else None,
                result=None,
            )
            for a in attempts
        ]
    )


@app.post("/apply/attempts/{attempt_id}/run", response_model=AttemptResponse)
async def run_attempt(attempt_id: int, passphrase: str | None = None) -> AttemptResponse:
    attempt = await get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    async with async_session_factory() as session:
        job = await session.get(Job, attempt.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

    try:
        # run assisted apply and persist result
        result = await assisted_apply_greenhouse(job.source_url, passphrase or "", confirm_submit=False)
        result_text = str(result)
        updated = await update_attempt_result(attempt.id, "completed", result_text)
    except PlaywrightNotAvailable as e:
        updated = await update_attempt_result(attempt.id, "error", str(e))
    except Exception as e:
        updated = await update_attempt_result(attempt.id, "failed", str(e))

    return AttemptResponse(
        id=updated.id,
        job_id=updated.job_id,
        status=updated.status,
        created_at=updated.created_at.isoformat(),
        updated_at=updated.updated_at.isoformat() if updated.updated_at else None,
        result=None,
    )
