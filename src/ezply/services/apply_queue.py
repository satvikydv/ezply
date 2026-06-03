from typing import Any, Dict, List

from sqlalchemy import select

from ezply.db import async_session_factory
from ezply.models import ApplicationAttempt


async def create_attempt(job_id: int) -> ApplicationAttempt:
    async with async_session_factory() as session:
        attempt = ApplicationAttempt(job_id=job_id, status="pending")
        session.add(attempt)
        await session.commit()
        await session.refresh(attempt)
        return attempt


async def list_attempts(limit: int = 100) -> List[ApplicationAttempt]:
    async with async_session_factory() as session:
        result = await session.execute(select(ApplicationAttempt).order_by(ApplicationAttempt.id.desc()).limit(limit))
        return result.scalars().all()


async def get_attempt(attempt_id: int) -> ApplicationAttempt | None:
    async with async_session_factory() as session:
        return await session.get(ApplicationAttempt, attempt_id)


async def update_attempt_result(attempt_id: int, status: str, result_text: str | None) -> ApplicationAttempt:
    async with async_session_factory() as session:
        attempt = await session.get(ApplicationAttempt, attempt_id)
        attempt.status = status
        attempt.result = result_text
        await session.commit()
        await session.refresh(attempt)
        return attempt
