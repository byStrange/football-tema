from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from config import config

engine = create_async_engine(config.DATABASE_URL, echo=False, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables() -> None:
    from db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
