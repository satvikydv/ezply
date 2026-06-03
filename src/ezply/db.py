from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ezply.models import Base
from ezply.settings import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def get_session() -> AsyncSession:
    return async_session_factory()
