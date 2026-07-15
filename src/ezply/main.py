from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func

from ezply.db import async_session_factory, init_db
from ezply.models import Application, RawJob, ScoredJob

app = FastAPI(title="Ezply API", version="0.2.0")

# Allow CORS for local dev frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup() -> None:
    await init_db()

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/api/metrics")
async def get_metrics() -> dict:
    async with async_session_factory() as session:
        # Total jobs
        total_raw = await session.scalar(select(func.count(RawJob.id)))
        
        # Total scored
        total_scored = await session.scalar(select(func.count(ScoredJob.id)))
        
        # Total applied
        total_applied = await session.scalar(select(func.count(Application.id)).where(Application.status == "applied"))

        return {
            "total_jobs_ingested": total_raw or 0,
            "total_jobs_scored": total_scored or 0,
            "total_jobs_applied": total_applied or 0,
        }

@app.get("/api/jobs/high_fit")
async def get_high_fit_jobs() -> list[dict]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScoredJob, RawJob)
            .join(RawJob, ScoredJob.raw_job_id == RawJob.id)
            .where(ScoredJob.fit_score >= 70)
            .order_by(ScoredJob.fit_score.desc())
            .limit(50)
        )
        
        jobs = []
        for scored, raw in result.all():
            jobs.append({
                "id": raw.id,
                "title": raw.title,
                "url": raw.url,
                "company_id": raw.company_id,
                "fit_score": scored.fit_score,
                "reasoning": scored.reasoning
            })
        return jobs
