from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ezply.models import Base
from ezply.settings import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with engine.begin() as connection:
        result = await connection.execute(
            text("PRAGMA table_info('jobs')")
        )
        columns = {row[1] for row in result.fetchall()}
        if "posted_at" not in columns:
            await connection.execute(
                text("ALTER TABLE jobs ADD COLUMN posted_at DATETIME")
            )


def get_session() -> AsyncSession:
    return async_session_factory()
