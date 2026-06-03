from sqlalchemy import select

from ezply.db import async_session_factory
from ezply.models import Job
from ezply.schemas import ImportJobsResponse
from ezply.scraping.base import JobSource


async def ingest_source(source: JobSource) -> ImportJobsResponse:
    jobs = await source.fetch_jobs()
    imported_count = 0
    skipped_count = 0

    async with async_session_factory() as session:
        for job in jobs:
            existing = await session.scalar(select(Job).where(Job.source_url == job.source_url))
            if existing is not None:
                skipped_count += 1
                continue

            session.add(
                Job(
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    seniority=job.seniority,
                    source=job.source,
                    source_url=job.source_url,
                    description=job.description,
                    posted_at=job.posted_at,
                )
            )
            imported_count += 1

        await session.commit()

    return ImportJobsResponse(source_name=source.name, imported_count=imported_count, skipped_count=skipped_count)
