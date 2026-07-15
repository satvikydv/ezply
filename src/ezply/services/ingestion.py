import hashlib
from sqlalchemy import select

from ezply.db import async_session_factory
from ezply.models import RawJob, Company
from ezply.scraping.base import JobSource


def generate_job_hash(company: str, title: str, url: str) -> str:
    """Generate a stable hash to deduplicate jobs."""
    data = f"{company}:{title}:{url}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


async def ingest_source(source: JobSource) -> dict:
    jobs = await source.fetch_jobs()
    imported_count = 0
    skipped_count = 0

    async with async_session_factory() as session:
        # Ensure company exists, otherwise create a dummy one for now (or fail)
        company_rec = await session.scalar(select(Company).where(Company.name == source.name))
        if not company_rec:
            # We assume source.name acts as the company name/ats_slug for now
            company_rec = Company(name=source.name, ats_type="unknown", ats_slug=source.name)
            session.add(company_rec)
            await session.commit()
            await session.refresh(company_rec)

        for job in jobs:
            j_hash = generate_job_hash(job.company, job.title, job.source_url)
            
            existing = await session.scalar(select(RawJob).where(RawJob.job_hash == j_hash))
            if existing is not None:
                skipped_count += 1
                continue

            session.add(
                RawJob(
                    company_id=company_rec.id,
                    external_id=job.source_url, # Fallback to URL as external ID
                    title=job.title,
                    location=job.location,
                    department=None, # Department missing in JobRecord
                    url=job.source_url,
                    description_raw=job.description,
                    posted_at=job.posted_at,
                    job_hash=j_hash
                )
            )
            imported_count += 1

        await session.commit()

    return {"source_name": source.name, "imported_count": imported_count, "skipped_count": skipped_count}
